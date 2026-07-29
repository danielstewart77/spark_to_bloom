import json
import markdown
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from auth import (
    clear_session_cookie,
    get_current_user_from_request,
    init_auth_db,
    require_auth,
    set_session_cookie,
    verify_user_credentials,
)
from config import BASE_DIR


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
templates = Jinja2Templates(directory=BASE_DIR / "templates")

HIVE_INIT_ALLOWED_FILES = {
    "hive-init.py": "text/x-python",
    "hive-init.sh": "text/x-shellscript",
}


def _request_host(request: Request) -> str:
    return request.headers.get("host", "").split(":", 1)[0].lower()


def _hive_init_host() -> str:
    return os.getenv("HIVE_INIT_HOST", "gethivemind.sparktobloom.com").lower()


def _hive_init_repo_dir() -> Path:
    return Path(os.getenv("HIVE_INIT_REPO_DIR", "/mnt/dev/hive-init")).resolve()


def _hive_init_asset_path(filename: str) -> Path:
    if filename not in HIVE_INIT_ALLOWED_FILES:
        raise HTTPException(status_code=404, detail="Installer asset not found")

    repo_dir = _hive_init_repo_dir()
    asset_path = (repo_dir / filename).resolve()
    if asset_path.parent != repo_dir or not asset_path.is_file():
        raise HTTPException(status_code=404, detail="Installer asset not found")
    return asset_path


def _serve_hive_init_asset(filename: str) -> FileResponse:
    asset_path = _hive_init_asset_path(filename)
    return FileResponse(
        asset_path,
        media_type=HIVE_INIT_ALLOWED_FILES[filename],
        filename=filename,
    )


def _render_hive_init_home(request: Request) -> HTMLResponse:
    base_url = f"{request.url.scheme}://{request.headers.get('host', _hive_init_host())}"
    body = f"""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <title>Get Hive Mind</title>
        <style>
          body {{
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            max-width: 48rem;
            margin: 4rem auto;
            padding: 0 1.25rem;
            line-height: 1.6;
          }}
          code {{
            background: #f3f3f3;
            padding: 0.1rem 0.3rem;
          }}
        </style>
      </head>
      <body>
        <h1>Get Hive Mind</h1>
        <p>Standalone Phase 1 installer for Hive Mind.</p>
        <p>Download targets:</p>
        <ul>
          <li><a href="{base_url}/hive-init.py">hive-init.py</a></li>
          <li><a href="{base_url}/hive-init.sh">hive-init.sh</a></li>
        </ul>
        <p>Quick start:</p>
        <pre><code>curl -fsSL {base_url}/hive-init.sh | bash</code></pre>
      </body>
    </html>
    """
    return HTMLResponse(body)


def _asset_versions() -> dict[str, int]:
    """Cache-busting stamp for every first-party static file.

    Enumerated rather than enumerated-by-hand: a hardcoded list silently
    stops covering the next asset someone adds, which is how a stale
    terminal-routing.js once outlived the terminal.html that called into
    it. Only the top level of static/ — vendor/ is pinned third-party and
    images are content-addressed by name.
    """
    static_dir = BASE_DIR / "static"
    return {
        path.name: int(path.stat().st_mtime_ns)
        for path in static_dir.iterdir()
        if path.is_file()
    }


def _render_template(request: Request, template_name: str, **context) -> HTMLResponse:
    context.setdefault("current_user", get_current_user_from_request(request))
    context.setdefault("asset_versions", _asset_versions())
    context["request"] = request
    return templates.TemplateResponse(request, template_name, context)


def _render_markdown(md_path: Path) -> str:
    if not md_path.exists():
        return ""
    with open(md_path, "r", encoding="utf-8") as handle:
        md_content = handle.read()
    # Pull mermaid fences out before codehilite gets them; emit raw HTML divs
    # that Mermaid.js can pick up directly without any JS transformation.
    md_content = re.sub(
        r"```mermaid\n(.*?)\n```",
        lambda m: f'<div class="mermaid">\n{m.group(1)}\n</div>',
        md_content,
        flags=re.DOTALL,
    )
    return markdown.markdown(
        md_content,
        extensions=["fenced_code", "codehilite", "toc", "tables"],
    )


def _safe_next_path(next_path: str | None, fallback: str = "/") -> str:
    if next_path and next_path.startswith("/") and not next_path.startswith("//"):
        return next_path
    return fallback


def _login_redirect_for(request: Request) -> RedirectResponse:
    next_path = urllib.parse.quote(request.url.path, safe="/")
    return RedirectResponse(url=f"/login?next={next_path}", status_code=303)


@app.middleware("http")
async def hive_init_host_router(request: Request, call_next):
    if _request_host(request) != _hive_init_host():
        return await call_next(request)

    if request.url.path in {"", "/"}:
        return _render_hive_init_home(request)
    if request.url.path == "/health":
        return PlainTextResponse("ok")
    if request.url.path.startswith("/"):
        filename = request.url.path[1:]
        if filename in HIVE_INIT_ALLOWED_FILES:
            return _serve_hive_init_asset(filename)
    return PlainTextResponse("Not Found", status_code=404)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return _render_template(request, "home.html")


@app.get("/hive-mind", response_class=HTMLResponse)
async def hive_mind(request: Request):
    return _render_template(request, "hive_mind.html")


@app.get("/pullrequests", response_class=HTMLResponse)
async def pullrequests(request: Request):
    return _render_template(request, "pullrequests.html")


@app.get("/downloads/{filename}")
async def download_hive_init_asset(filename: str):
    return _serve_hive_init_asset(filename)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    current_user = get_current_user_from_request(request)
    if current_user:
        return RedirectResponse(url=_safe_next_path(next), status_code=303)
    return _render_template(request, "login.html", next_path=_safe_next_path(next))


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
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


def _event_triage_base_url() -> str:
    return os.getenv("EVENT_TRIAGE_URL", "http://host.docker.internal:8430").rstrip("/")


def _event_triage_headers() -> dict:
    token = os.getenv("EVENT_TRIAGE_BEARER_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="event_triage bearer token not configured")
    return {"Authorization": f"Bearer {token}"}


async def _event_triage_get(path: str, params: dict | None = None) -> list:
    base = _event_triage_base_url()
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{base}{path}", params=params, headers=_event_triage_headers())
        resp.raise_for_status()
        return resp.json()


@app.get("/events", response_class=HTMLResponse)
async def events_page(request: Request, limit: int = 100):
    if not get_current_user_from_request(request):
        return _login_redirect_for(request)
    safe_limit = max(1, min(int(limit), 500))
    try:
        raw_events = await _event_triage_get("/events", {"limit": safe_limit})
        raw_classes = await _event_triage_get("/event_classes")
    except (httpx.HTTPError, HTTPException) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else f"event_triage API unreachable: {exc}"
        return _render_template(
            request, "events.html", events=[], error=detail, limit=safe_limit
        )

    classes_by_id = {c["id"]: c for c in raw_classes}
    events = []
    for r in raw_events:
        payload = r.get("payload") or {}
        meta = payload.get("classify_meta") or {}
        repeat = payload.get("repeat_analysis") or {}
        cls = classes_by_id.get(r["event_class_id"], {})
        events.append({
            "id": r["id"],
            "occurred_at": r["occurred_at"],
            "source": r["source"],
            "status": r["status"],
            "summary": r.get("summary") or "",
            "action_log": r.get("action_log") or "",
            "class_slug": cls.get("slug", ""),
            "class_label": cls.get("label", ""),
            "bucket": cls.get("bucket", ""),
            "rule_id": r.get("response_rule_id"),
            "reasoning": meta.get("reasoning", ""),
            "path": meta.get("path", ""),
            "hints": meta.get("hints", []) or [],
            "count": payload.get("count"),
            "excerpt": payload.get("excerpt", ""),
            "repeat_headline": repeat.get("headline", ""),
            "repeat_recommendation": repeat.get("recommended_action", ""),
            "repeat_causes": repeat.get("likely_causes", []) or [],
            "repeat_checks": repeat.get("next_checks", []) or [],
        })
    return _render_template(
        request, "events.html", events=events, error=None, limit=safe_limit
    )


@app.get("/response_rules", response_class=HTMLResponse)
async def response_rules_page(request: Request):
    if not get_current_user_from_request(request):
        return _login_redirect_for(request)
    try:
        raw_rules = await _event_triage_get("/response_rules")
        raw_classes = await _event_triage_get("/event_classes")
    except (httpx.HTTPError, HTTPException) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else f"event_triage API unreachable: {exc}"
        return _render_template(
            request, "response_rules.html", rules=[], error=detail
        )

    classes_by_id = {c["id"]: c for c in raw_classes}
    rules = []
    for r in sorted(raw_rules, key=lambda x: (classes_by_id.get(x["event_class_id"], {}).get("slug", ""), x["id"])):
        cls = classes_by_id.get(r["event_class_id"], {})
        rules.append({
            "id": r["id"],
            "name": r["name"],
            "condition_expr": r.get("condition_expr") or "",
            "action_kind": r["action_kind"],
            "params": r.get("action_params") or {},
            "auto_apply": bool(r.get("auto_apply")),
            "approval_state": r["approval_state"],
            "authorized_by": r.get("authorized_by") or "",
            "created_at": r["created_at"],
            "last_fired_at": r.get("last_fired_at") or "",
            "fire_count": r["fire_count"],
            "class_slug": cls.get("slug", ""),
            "bucket": cls.get("bucket", ""),
        })
    return _render_template(request, "response_rules.html", rules=rules, error=None)


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
