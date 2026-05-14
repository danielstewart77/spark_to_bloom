import asyncio
from collections import deque
from datetime import UTC, datetime
import hmac
import json
import logging
import markdown
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import os
from typing import Any
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from auth import (
    clear_session_cookie,
    get_current_user_from_request,
    init_auth_db,
    require_auth,
    set_session_cookie,
    verify_user_credentials,
)
from config import BASE_DIR
from graph_data import get_graph_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    init_auth_db()
    yield


app = FastAPI(
    title="Spark to Bloom",
    description="A blog about AI, orchestration, and development thoughts",
    version="1.1.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/downloads", StaticFiles(directory=BASE_DIR / "downloads"), name="downloads")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
log = logging.getLogger("spark.console")
_FORM_RATE_LIMIT_STATE: dict[str, deque[float]] = {}
_FORM_RATE_LIMIT_LOCK = threading.Lock()


class ContactFormSubmission(BaseModel):
    form_name: str = Field(default="contact", min_length=1, max_length=120)
    fields: dict[str, Any] = Field(min_length=1)
    meta: dict[str, Any] | None = None


def _gateway_base_url() -> str:
    return os.getenv("GATEWAY_API_URL") or os.getenv("GRAPH_API_URL") or "http://server:8420"


def _form_api_key() -> str:
    return os.getenv("STB_FORM_API_KEY", "").strip()


def _form_allowed_origins() -> set[str]:
    raw = os.getenv("STB_FORM_ALLOWED_ORIGINS", "")
    return {origin.strip() for origin in raw.split(",") if origin.strip()}


def _is_form_origin_allowed(origin: str | None) -> bool:
    if not origin:
        return False

    allowed = _form_allowed_origins()
    if not allowed:
        return True
    return origin in allowed


def _form_submissions_path() -> Path:
    raw = os.getenv(
        "STB_FORM_SUBMISSIONS_PATH",
        str(BASE_DIR.parent / "data" / "form_submissions.jsonl"),
    )
    return Path(raw)


def _hive_tools_url() -> str:
    return os.getenv("HIVE_TOOLS_URL", "http://hive-tools:9421").rstrip("/")


def _hive_tools_token() -> str:
    return os.getenv("HIVE_TOOLS_TOKEN", "").strip()


def _form_notify_email() -> str:
    return os.getenv("STB_FORM_NOTIFY_EMAIL", "kjdreamhomes@gmail.com").strip()


def _form_spam_model() -> str:
    return os.getenv("STB_FORM_SPAM_MODEL", "gpt-oss:20b-32k").strip()


def _form_honeypot_field() -> str:
    return os.getenv("STB_FORM_HONEYPOT_FIELD", "company").strip()


def _form_rate_limit_count() -> int:
    return int(os.getenv("STB_FORM_RATE_LIMIT_COUNT", "5"))


def _form_rate_limit_window_seconds() -> int:
    return int(os.getenv("STB_FORM_RATE_LIMIT_WINDOW_SECONDS", "600"))


def _form_max_content_length() -> int:
    return int(os.getenv("STB_FORM_MAX_CONTENT_LENGTH", "16384"))


def _render_template(request: Request, template_name: str, **context) -> HTMLResponse:
    context.setdefault("current_user", get_current_user_from_request(request))
    static_dir = BASE_DIR / "static"
    context.setdefault(
        "asset_versions",
        {
            "style.css": int((static_dir / "style.css").stat().st_mtime_ns),
            "scripts.js": int((static_dir / "scripts.js").stat().st_mtime_ns),
        },
    )
    context["request"] = request
    return templates.TemplateResponse(request, template_name, context)


def _render_markdown(md_path: Path) -> str:
    if not md_path.exists():
        return ""
    with open(md_path, "r", encoding="utf-8") as handle:
        md_content = handle.read()
    return markdown.markdown(
        md_content,
        extensions=["fenced_code", "codehilite", "toc", "tables"],
    )


def _safe_next_path(next_path: str | None, fallback: str = "/console") -> str:
    if next_path and next_path.startswith("/") and not next_path.startswith("//"):
        return next_path
    return fallback


def _filter_console_sessions(sessions: dict | list) -> list[dict]:
    if not isinstance(sessions, list):
        return []

    now = int(time.time())
    cutoff = now - 86400

    filtered = [
        session for session in sessions
        if int(session.get("last_active", 0)) >= cutoff
    ]
    order = {"running": 0, "idle": 1, "closed": 2}
    filtered.sort(
        key=lambda session: (
            order.get(session.get("status", "closed"), 9),
            -float(session.get("last_active", 0)),
        )
    )
    return filtered


def _login_redirect_for(request: Request) -> RedirectResponse:
    next_path = urllib.parse.quote(request.url.path, safe="/")
    return RedirectResponse(url=f"/login?next={next_path}", status_code=303)


def _gateway_json_sync(path: str, params: dict | None = None) -> dict | list:
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    url = f"{_gateway_base_url().rstrip('/')}{path}{query}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


async def _gateway_json(path: str, params: dict | None = None) -> dict | list:
    try:
        return await asyncio.to_thread(_gateway_json_sync, path, params)
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=exc.code, detail=f"Gateway request failed: {path}") from exc
    except OSError as exc:
        raise HTTPException(status_code=502, detail=f"Gateway unavailable: {exc}") from exc


def _require_form_api_key(request: Request) -> None:
    expected = _form_api_key()
    if not expected:
        raise HTTPException(status_code=503, detail="Form intake is not configured")

    provided = request.headers.get("x-api-key", "")
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")


def _require_form_origin(request: Request) -> None:
    allowed = _form_allowed_origins()
    if not allowed:
        return

    origin = request.headers.get("origin")
    if origin not in allowed:
        raise HTTPException(status_code=403, detail="Origin not allowed")


def _append_form_submission(record: dict[str, Any]) -> None:
    submissions_path = _form_submissions_path()
    submissions_path.parent.mkdir(parents=True, exist_ok=True)
    with open(submissions_path, "a", encoding="utf-8") as handle:
        json.dump(record, handle)
        handle.write("\n")


def _request_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _enforce_form_content_length(request: Request) -> None:
    raw = request.headers.get("content-length", "").strip()
    if not raw:
        return

    try:
        content_length = int(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid content length")

    if content_length > _form_max_content_length():
        raise HTTPException(status_code=413, detail="Payload too large")


def _enforce_form_rate_limit(request: Request) -> None:
    client_ip = _request_client_ip(request)
    now = time.time()
    window = _form_rate_limit_window_seconds()
    limit = _form_rate_limit_count()

    with _FORM_RATE_LIMIT_LOCK:
        entries = _FORM_RATE_LIMIT_STATE.setdefault(client_ip, deque())
        while entries and now - entries[0] > window:
            entries.popleft()

        if len(entries) >= limit:
            raise HTTPException(status_code=429, detail="Too many submissions")

        entries.append(now)


def _hive_tools_request_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    token = _hive_tools_token()
    if not token:
        raise RuntimeError("HIVE_TOOLS_TOKEN is not configured")

    url = f"{_hive_tools_url()}{path}"
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _classify_submission_spam(record: dict[str, Any]) -> dict[str, Any]:
    fields = dict(record.get("fields", {}))
    honeypot_field = _form_honeypot_field()
    honeypot_value = str(fields.get(honeypot_field, "")).strip()
    if honeypot_value:
        return {
            "verdict": "spam",
            "confidence": 1.0,
            "reason": f"Honeypot field '{honeypot_field}' was populated",
            "source": "honeypot",
        }

    payload = {
        "model": _form_spam_model(),
        "system": (
            "You classify real estate web form submissions for spam. "
            "Return only structured data that matches the schema. "
            "Verdict meanings: ham = legitimate lead, spam = unwanted/abusive, "
            "uncertain = cannot confidently decide."
        ),
        "prompt": json.dumps(
            {
                "context": {
                    "site": "KJ Dream Homes",
                    "forms": ["buyer-intake", "seller-intake", "investor-intake"],
                    "target": "real estate leads for Xiaolan",
                },
                "submission": {
                    "form_name": record.get("form_name"),
                    "fields": fields,
                    "meta": record.get("meta", {}),
                    "origin": record.get("origin"),
                },
            },
            ensure_ascii=True,
        ),
        "schema": {
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": ["ham", "spam", "uncertain"],
                },
                "confidence": {
                    "type": "number",
                },
                "reason": {
                    "type": "string",
                },
            },
            "required": ["verdict", "confidence", "reason"],
            "additionalProperties": False,
        },
    }

    try:
        result = _hive_tools_request_json("/ollama/structured", payload)
    except Exception as exc:
        return {
            "verdict": "uncertain",
            "confidence": 0.0,
            "reason": f"Classifier unavailable: {exc}",
            "source": "ollama_error",
        }

    verdict = str(result.get("verdict", "uncertain")).strip().lower()
    if verdict not in {"ham", "spam", "uncertain"}:
        verdict = "uncertain"

    try:
        confidence = float(result.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    reason = str(result.get("reason", "No reason provided")).strip()
    if result.get("_error"):
        verdict = "uncertain"
        reason = f"Ollama schema error: {result.get('_error')}"
        confidence = 0.0

    return {
        "verdict": verdict,
        "confidence": confidence,
        "reason": reason,
        "source": "ollama",
    }


def _format_submission_email(record: dict[str, Any]) -> dict[str, str]:
    fields = record.get("fields", {})
    full_name = " ".join(
        part for part in [fields.get("first_name", ""), fields.get("last_name", "")] if part
    ).strip()
    lead_name = full_name or fields.get("email") or "Unknown lead"

    lines = [
        f"KJ Dream Homes form submission: {record.get('form_name')}",
        "",
        f"Received at: {record.get('received_at')}",
        f"Origin: {record.get('origin')}",
        f"Page URL: {record.get('meta', {}).get('page_url', '')}",
        "",
        "Fields:",
    ]
    for key, value in fields.items():
        if key == _form_honeypot_field():
            continue
        label = key.replace("_", " ").title()
        lines.append(f"- {label}: {value}")

    lines.extend(
        [
            "",
            "---",
            "Sent on behalf of Daniel by Nagatha.",
        ]
    )

    return {
        "to": _form_notify_email(),
        "subject": f"KJ Dream Homes lead: {record.get('form_name')} - {lead_name}",
        "body": "\n".join(lines),
    }


def _send_submission_email(record: dict[str, Any]) -> dict[str, Any]:
    payload = _format_submission_email(record)
    return _hive_tools_request_json("/gmail/send", payload)


@app.middleware("http")
async def form_cors_middleware(request: Request, call_next):
    origin = request.headers.get("origin")
    is_form_request = request.url.path == "/api/forms/kj-dream-homes/contact"

    if not is_form_request or not origin:
        return await call_next(request)

    if not _is_form_origin_allowed(origin):
        return JSONResponse(status_code=403, content={"detail": "Origin not allowed"})

    if request.method == "OPTIONS":
        response = Response(status_code=204)
    else:
        response = await call_next(request)

    requested_headers = request.headers.get("access-control-request-headers")
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = requested_headers or "Content-Type, X-API-Key"
    response.headers["Access-Control-Max-Age"] = "600"
    response.headers["Vary"] = "Origin"
    return response


def _proxy_session_events(session_id: str):
    url = f"{_gateway_base_url().rstrip('/')}/sessions/{session_id}/events"

    try:
        log.info("console stream connect session=%s upstream=%s", session_id, url)
        yield f"data: {json.dumps({'type': 'system', 'content': 'proxy_connected'})}\n\n"
        request = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
        with urllib.request.urlopen(request) as response:
            log.info("console stream upstream_open session=%s", session_id)
            yield f"data: {json.dumps({'type': 'system', 'content': 'upstream_connected'})}\n\n"
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                # Forward data lines and SSE keepalive comments (: ping etc)
                # so the browser connection stays alive during idle sessions
                if line.startswith("data: ") or line.startswith(":"):
                    yield f"{line}\n\n"
    except urllib.error.HTTPError as exc:
        log.warning("console stream http_error session=%s error=%s", session_id, exc)
        payload = {"type": "system", "content": f"upstream_error: {exc.code}"}
        yield f"data: {json.dumps(payload)}\n\n"
    except OSError as exc:
        log.warning("console stream os_error session=%s error=%s", session_id, exc)
        payload = {"type": "system", "content": f"upstream_error: {exc}"}
        yield f"data: {json.dumps(payload)}\n\n"


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return _render_template(request, "home.html")


@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return _render_template(request, "about.html")


@app.get("/pullrequests", response_class=HTMLResponse)
async def pullrequests(request: Request):
    return _render_template(request, "pullrequests.html")


@app.get("/linkedin", response_class=HTMLResponse)
async def linkedin(request: Request):
    html_content = _render_markdown(BASE_DIR / "templates" / "linkedin" / "ada.md")
    return _render_template(request, "linkedin.html", content=html_content)


@app.get("/backlog", response_class=HTMLResponse)
async def backlog_page(request: Request):
    backlog_dir = BASE_DIR / "backlog"
    items = []
    if backlog_dir.exists():
        for f in sorted(backlog_dir.glob("*.md"), key=lambda p: p.stem):
            slug = f.stem
            label = slug.replace("-", " ").title()
            items.append(f"- [{label}](/canvas?doc={slug})")
    md_content = "# Backlog\n\n" + "\n".join(items)
    html_content = markdown.markdown(md_content, extensions=["fenced_code", "codehilite", "toc", "tables"])
    return _render_template(request, "page.html", content=html_content)


@app.get("/plans", response_class=HTMLResponse)
async def plans_page(request: Request):
    plans_dir = BASE_DIR / "plans"
    items = []
    if plans_dir.exists():
        for f in sorted(plans_dir.glob("*.md"), key=lambda p: p.stem):
            slug = f.stem
            label = slug.replace("-", " ").title()
            items.append(f"- [{label}](/canvas?dir=plans&doc={slug})")
    md_content = "# Plans\n\n" + "\n".join(items)
    html_content = markdown.markdown(md_content, extensions=["fenced_code", "codehilite", "toc", "tables"])
    return _render_template(request, "page.html", content=html_content)


@app.get("/canvas", response_class=HTMLResponse)
async def canvas(request: Request, doc: str | None = None, dir: str = "backlog"):
    backlog_dir = BASE_DIR / "backlog"
    plans_dir = BASE_DIR / "plans"

    def _scan_dir(d: Path) -> list:
        items = []
        if d.exists():
            for f in sorted(d.glob("*.md"), key=lambda p: p.stem):
                slug = f.stem
                label = slug.replace("-", " ").title()
                items.append({"slug": slug, "label": label})
        return items

    backlog_items = _scan_dir(backlog_dir)
    plans_items = _scan_dir(plans_dir)

    active_doc = None
    active_dir = dir if dir in ("backlog", "plans") else "backlog"
    source_dir = plans_dir if active_dir == "plans" else backlog_dir

    if doc:
        doc_path = source_dir / f"{doc}.md"
        try:
            resolved = doc_path.resolve()
            if (
                str(resolved).startswith(str(source_dir.resolve()))
                and resolved.exists()
                and resolved.is_file()
            ):
                html_content = _render_markdown(resolved)
                active_doc = doc
            else:
                html_content = _render_markdown(BASE_DIR / "templates" / "canvas.md")
        except (OSError, ValueError):
            html_content = _render_markdown(BASE_DIR / "templates" / "canvas.md")
    else:
        html_content = _render_markdown(BASE_DIR / "templates" / "canvas.md")

    return _render_template(
        request, "canvas.html",
        content=html_content,
        backlog_items=backlog_items,
        plans_items=plans_items,
        active_doc=active_doc,
        active_dir=active_dir,
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/console"):
    current_user = get_current_user_from_request(request)
    if current_user:
        return RedirectResponse(url=_safe_next_path(next), status_code=303)
    return _render_template(request, "login.html", next_path=_safe_next_path(next))


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/console"),
):
    user = verify_user_credentials(username, password)
    if not user:
        return _render_template(
            request,
            "login.html",
            error="Invalid username or password.",
            next_path=_safe_next_path(next),
        )

    response = RedirectResponse(url=_safe_next_path(next), status_code=303)
    set_session_cookie(response, user)
    return response


@app.post("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    clear_session_cookie(response)
    return response


@app.get("/console", response_class=HTMLResponse)
async def console(request: Request):
    if not get_current_user_from_request(request):
        return _login_redirect_for(request)
    try:
        sessions = _filter_console_sessions(await _gateway_json("/sessions"))
    except Exception:
        sessions = []
    return _render_template(request, "console.html", initial_sessions=sessions)


@app.get("/graph/data")
async def graph_data(limit: int = 400, user: dict = Depends(require_auth)):
    del user
    return get_graph_data(_gateway_base_url(), limit=limit)


@app.get("/graph/public-data")
async def graph_public_data(limit: int = 400, user: dict = Depends(require_auth)):
    del user
    data = get_graph_data(_gateway_base_url(), limit=limit)
    public_nodes = [n for n in data.get("nodes", []) if n.get("type") != "Person"]
    public_ids = {n["id"] for n in public_nodes}
    public_edges = [
        e for e in data.get("edges", [])
        if e.get("source") in public_ids and e.get("target") in public_ids
    ]
    return {"nodes": public_nodes, "edges": public_edges}


@app.get("/graph", response_class=HTMLResponse)
async def graph(request: Request):
    if not get_current_user_from_request(request):
        return _login_redirect_for(request)
    return _render_template(request, "graph.html")


@app.get("/api/minds")
async def api_minds(user: dict = Depends(require_auth)):
    del user
    return await _gateway_json("/broker/minds")


@app.get("/api/console/sessions")
async def api_console_sessions(user: dict = Depends(require_auth)):
    del user
    return _filter_console_sessions(await _gateway_json("/sessions"))


@app.get("/api/console/{session_id}/stream")
async def api_console_stream(session_id: str, user: dict = Depends(require_auth)):
    del user
    return StreamingResponse(
        _proxy_session_events(session_id),
        media_type="text/event-stream",
    )


@app.post("/api/forms/kj-dream-homes/contact", status_code=202)
async def submit_kj_dream_homes_contact(payload: ContactFormSubmission, request: Request):
    _require_form_api_key(request)
    _require_form_origin(request)
    _enforce_form_content_length(request)
    _enforce_form_rate_limit(request)

    received_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    submission_id = uuid.uuid4().hex
    record = {
        "id": submission_id,
        "site": "kj-dream-homes",
        "form_name": payload.form_name,
        "fields": payload.fields,
        "meta": payload.meta or {},
        "origin": request.headers.get("origin"),
        "client_ip": _request_client_ip(request),
        "user_agent": request.headers.get("user-agent"),
        "received_at": received_at,
    }

    spam_check = await asyncio.to_thread(_classify_submission_spam, record)
    record["spam_check"] = spam_check

    if spam_check["verdict"] == "ham":
        try:
            await asyncio.to_thread(_send_submission_email, record)
            record["delivery"] = {"status": "sent", "reason": "passed spam checks"}
        except Exception as exc:
            record["delivery"] = {"status": "email_failed", "reason": str(exc)}
    elif spam_check["verdict"] == "spam":
        record["delivery"] = {"status": "skipped_spam", "reason": spam_check["reason"]}
    else:
        record["delivery"] = {"status": "held_uncertain", "reason": spam_check["reason"]}

    await asyncio.to_thread(_append_form_submission, record)
    log.info(
        "form submission accepted site=kj-dream-homes id=%s form=%s origin=%s verdict=%s delivery=%s",
        submission_id,
        payload.form_name,
        request.headers.get("origin"),
        spam_check["verdict"],
        record["delivery"]["status"],
    )
    return {
        "status": "accepted",
        "submission_id": submission_id,
        "received_at": received_at,
    }


@app.get("/pages/{subpath:path}", response_class=HTMLResponse)
async def page(request: Request, subpath: str):
    md_path = BASE_DIR / "templates" / "pages" / subpath

    try:
        md_path = md_path.resolve()
        if not str(md_path).startswith(str(BASE_DIR / "templates" / "pages")):
            raise HTTPException(status_code=404, detail="Page not found")
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Page not found") from exc

    if not md_path.exists() or not md_path.is_file():
        raise HTTPException(status_code=404, detail="Page not found")

    try:
        html_content = _render_markdown(md_path)
        return _render_template(request, "page.html", content=html_content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error reading page: {exc}") from exc


@app.get("/pr/{subpath:path}", response_class=HTMLResponse)
async def blog_article(request: Request, subpath: str):
    md_path = BASE_DIR / "templates" / "pr" / subpath

    try:
        md_path = md_path.resolve()
        if not str(md_path).startswith(str(BASE_DIR / "templates" / "pr")):
            raise HTTPException(status_code=404, detail="Article not found")
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Article not found") from exc

    if not md_path.exists() or not md_path.is_file():
        raise HTTPException(status_code=404, detail="Article not found")

    try:
        html_content = _render_markdown(md_path)
        return _render_template(request, "pr.html", content=html_content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error reading article: {exc}") from exc


@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "Spark to Bloom is running"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=5000,
        reload=False,
        log_level="info",
    )
