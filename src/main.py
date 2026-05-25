import asyncio
import json
import markdown
import os
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
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
templates = Jinja2Templates(directory=BASE_DIR / "templates")

HIVE_INIT_ALLOWED_FILES = {
    "hive-init.py": "text/x-python",
    "hive-init.sh": "text/x-shellscript",
}


def _gateway_base_url() -> str:
    return os.getenv("GATEWAY_API_URL") or os.getenv("GRAPH_API_URL") or "http://hive-comms:8424"


def _gateway_headers() -> dict:
    token = os.getenv("COMMS_BEARER_TOKEN", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


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


def _safe_next_path(next_path: str | None, fallback: str = "/terminal") -> str:
    if next_path and next_path.startswith("/") and not next_path.startswith("//"):
        return next_path
    return fallback


def _login_redirect_for(request: Request) -> RedirectResponse:
    next_path = urllib.parse.quote(request.url.path, safe="/")
    return RedirectResponse(url=f"/login?next={next_path}", status_code=303)


def _gateway_json_sync(path: str, params: dict | None = None) -> dict | list:
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    url = f"{_gateway_base_url().rstrip('/')}{path}{query}"
    headers = {"Accept": "application/json", **_gateway_headers()}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


async def _gateway_json(path: str, params: dict | None = None) -> dict | list:
    try:
        return await asyncio.to_thread(_gateway_json_sync, path, params)
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=exc.code, detail=f"Gateway request failed: {path}") from exc
    except OSError as exc:
        raise HTTPException(status_code=502, detail=f"Gateway unavailable: {exc}") from exc


def _proxy_session_events(session_id: str):
    url = f"{_gateway_base_url().rstrip('/')}/sessions/{session_id}/events"

    try:
        headers = {"Accept": "text/event-stream", **_gateway_headers()}
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                yield f"{line}\n\n"
    except urllib.error.HTTPError as exc:
        payload = {"type": "system", "content": f"upstream_error: {exc.code}"}
        yield f"data: {json.dumps(payload)}\n\n"
    except OSError as exc:
        payload = {"type": "system", "content": f"upstream_error: {exc}"}
        yield f"data: {json.dumps(payload)}\n\n"


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


@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return _render_template(request, "about.html")


@app.get("/pullrequests", response_class=HTMLResponse)
async def pullrequests(request: Request):
    return _render_template(request, "pullrequests.html")


@app.get("/downloads/{filename}")
async def download_hive_init_asset(filename: str):
    return _serve_hive_init_asset(filename)


@app.get("/linkedin", response_class=HTMLResponse)
async def linkedin(request: Request):
    html_content = _render_markdown(BASE_DIR / "templates" / "linkedin" / "ada.md")
    return _render_template(request, "linkedin.html", content=html_content)


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
async def login_page(request: Request, next: str = "/terminal"):
    current_user = get_current_user_from_request(request)
    if current_user:
        return RedirectResponse(url=_safe_next_path(next), status_code=303)
    return _render_template(request, "login.html", next_path=_safe_next_path(next))


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/terminal"),
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


@app.get("/terminal", response_class=HTMLResponse)
async def terminal(request: Request):
    if not get_current_user_from_request(request):
        return _login_redirect_for(request)
    try:
        minds = await _gateway_json("/broker/minds")
        if not isinstance(minds, list):
            minds = []
        minds = [m for m in minds if isinstance(m, dict)]
        minds.sort(key=lambda m: (0 if m.get("name") == "ada" else 1, m.get("name", "")))
    except Exception:
        minds = []
    try:
        all_sessions = await _gateway_json("/sessions")
        if not isinstance(all_sessions, list):
            all_sessions = []
    except Exception:
        all_sessions = []
    selector_minds = _build_terminal_selector(minds, all_sessions)
    return _render_template(
        request,
        "terminal.html",
        minds=minds,
        selector_minds=selector_minds,
    )


def _build_terminal_selector(minds: list[dict], sessions: list[dict]) -> list[dict]:
    now = int(time.time())
    cutoff = now - 86400
    by_mind: dict[str, list[dict]] = {}
    for session in sessions:
        if not isinstance(session, dict):
            continue
        if session.get("status") not in ("running", "idle"):
            continue
        if int(session.get("last_active", 0)) < cutoff:
            continue
        mind_id = session.get("mind_id") or ""
        if not mind_id:
            continue
        by_mind.setdefault(mind_id, []).append(session)
    enriched: list[dict] = []
    for mind in minds:
        mind_id = mind.get("id") or ""
        mind_name = mind.get("name") or "mind"
        mind_sessions = by_mind.get(mind_id, [])
        mind_sessions.sort(key=lambda s: -float(s.get("last_active", 0)))
        enriched.append({
            "id": mind_id,
            "name": mind_name,
            "sessions": [
                {
                    "id": s.get("id"),
                    "short_id": (s.get("id") or "")[:8],
                    "status": s.get("status"),
                    "last_active": s.get("last_active"),
                    "age": _relative_age(now, s.get("last_active")),
                    "summary": (s.get("summary") or "").strip(),
                }
                for s in mind_sessions
            ],
        })
    return enriched


def _relative_age(now: int, last_active) -> str:
    try:
        seconds = max(0, int(now - float(last_active or 0)))
    except (TypeError, ValueError):
        return ""
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


@app.get("/api/terminal/selector")
async def api_terminal_selector(user: dict = Depends(require_auth)):
    del user
    try:
        minds = await _gateway_json("/broker/minds")
        if not isinstance(minds, list):
            minds = []
        minds = [m for m in minds if isinstance(m, dict)]
        minds.sort(key=lambda m: (0 if m.get("name") == "ada" else 1, m.get("name", "")))
    except Exception:
        minds = []
    try:
        all_sessions = await _gateway_json("/sessions")
        if not isinstance(all_sessions, list):
            all_sessions = []
    except Exception:
        all_sessions = []
    return _build_terminal_selector(minds, all_sessions)


def _voice_api_url() -> str:
    return os.environ.get("VOICE_API_URL", "http://hive-mind-voice:8422").rstrip("/")


@app.post("/api/terminal/tts")
async def api_terminal_tts(request: Request, user: dict = Depends(require_auth)):
    """Proxy text to the voice server's /tts endpoint and pipe back OGG audio.

    Only called when the user has the speaker toggle on, so the GPU isn't
    loaded for silent turns.
    """
    del user
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    voice_id = (body.get("voice_id") or "default").strip() or "default"
    payload = json.dumps({"text": text, "voice_id": voice_id}).encode()
    url = f"{_voice_api_url()}/tts"

    def _do_post():
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read(), resp.headers.get("content-type", "audio/ogg")

    try:
        audio, ctype = await asyncio.to_thread(_do_post)
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=exc.code, detail="voice server rejected request") from exc
    except OSError as exc:
        raise HTTPException(status_code=502, detail=f"voice server unavailable: {exc}") from exc
    return Response(content=audio, media_type=ctype)


@app.get("/api/terminal/active")
async def api_terminal_active(
    mind_id: str,
    exclude: str = "",
    user: dict = Depends(require_auth),
):
    """Return the most-recent live session for the given mind without auto-creating.

    Used by the browser to seamlessly reattach when a session rotates out from
    under it. Excludes the dying session via ``exclude=<session_id>`` so the
    browser doesn't immediately reattach to the corpse during the rotation
    window. Returns 204 when no live successor exists yet.
    """
    del user
    try:
        sessions = await _gateway_json("/sessions")
    except Exception:
        sessions = []
    if not isinstance(sessions, list):
        sessions = []
    now = int(time.time())
    cutoff = now - 86400
    live = [
        s for s in sessions
        if isinstance(s, dict)
        and s.get("mind_id") == mind_id
        and s.get("id") != exclude
        and int(s.get("last_active", 0)) >= cutoff
        and s.get("status") in ("running", "idle")
    ]
    if not live:
        return Response(status_code=204)
    live.sort(key=lambda s: -float(s.get("last_active", 0)))
    return live[0]


@app.get("/api/terminal/session")
async def api_terminal_get_session(mind_id: str, user: dict = Depends(require_auth)):
    del user
    sessions = await _gateway_json("/sessions")
    if not isinstance(sessions, list):
        sessions = []
    now = int(time.time())
    cutoff = now - 86400
    active = [
        s for s in sessions
        if s.get("mind_id") == mind_id
        and int(s.get("last_active", 0)) >= cutoff
        and s.get("status") in ("running", "idle")
    ]
    active.sort(key=lambda s: -float(s.get("last_active", 0)))
    if active:
        return active[0]
    return await _create_gateway_session(mind_id)


@app.post("/api/terminal/session")
async def api_terminal_create_session(request: Request, user: dict = Depends(require_auth)):
    del user
    body = await request.json()
    mind_id = (body.get("mind_id") or "").strip()
    if not mind_id:
        raise HTTPException(status_code=400, detail="mind_id is required")
    return await _create_gateway_session(mind_id)


async def _create_gateway_session(mind_id: str) -> dict:
    def _do_post():
        url = f"{_gateway_base_url().rstrip('/')}/sessions"
        data = json.dumps({
            "mind_id": mind_id,
            "model": "sonnet",
            "owner_type": "web",
            "owner_ref": "terminal",
            "client_ref": "terminal",
        }).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json", **_gateway_headers()},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        return await asyncio.to_thread(_do_post)
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=exc.code, detail="Failed to create session") from exc
    except OSError as exc:
        raise HTTPException(status_code=502, detail=f"Gateway unavailable: {exc}") from exc


@app.get("/api/minds")
async def api_minds(user: dict = Depends(require_auth)):
    del user
    return await _gateway_json("/broker/minds")


_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MEMORY_ROW_LIMIT_DEFAULT = 200
_MEMORY_ROW_LIMIT_MAX = 1000


def _lucent_db_path() -> str:
    return os.getenv("LUCENT_DB_PATH", "/data/lucent.db")


def _open_lucent_readonly() -> sqlite3.Connection:
    path = _lucent_db_path()
    if not os.path.exists(path):
        raise HTTPException(status_code=503, detail="lucent database not mounted")
    uri = f"file:{path}?mode=ro&immutable=0"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _memory_cell_for_json(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<BLOB {len(bytes(value))} bytes>"
    return value


def _list_lucent_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


@app.get("/memory", response_class=HTMLResponse)
async def memory_page(request: Request):
    if not get_current_user_from_request(request):
        return _login_redirect_for(request)
    return _render_template(request, "memory.html")


@app.get("/api/memory/tables")
async def api_memory_tables(user: dict = Depends(require_auth)):
    del user
    conn = _open_lucent_readonly()
    try:
        tables = _list_lucent_tables(conn)
        results = []
        for name in tables:
            count_row = conn.execute(f'SELECT COUNT(*) AS c FROM "{name}"').fetchone()
            results.append({"name": name, "row_count": int(count_row["c"])})
    finally:
        conn.close()
    return {"tables": results}


@app.get("/api/memory/rows")
async def api_memory_rows(
    table: str,
    limit: int = _MEMORY_ROW_LIMIT_DEFAULT,
    offset: int = 0,
    user: dict = Depends(require_auth),
):
    del user
    if not _TABLE_NAME_RE.match(table):
        raise HTTPException(status_code=404, detail="table not found")
    safe_limit = max(1, min(int(limit), _MEMORY_ROW_LIMIT_MAX))
    safe_offset = max(0, int(offset))
    conn = _open_lucent_readonly()
    try:
        if table not in _list_lucent_tables(conn):
            raise HTTPException(status_code=404, detail="table not found")
        columns = [
            r["name"]
            for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        ]
        total = int(conn.execute(f'SELECT COUNT(*) AS c FROM "{table}"').fetchone()["c"])
        rows = [
            {col: _memory_cell_for_json(row[col]) for col in columns}
            for row in conn.execute(
                f'SELECT * FROM "{table}" LIMIT ? OFFSET ?',
                (safe_limit, safe_offset),
            ).fetchall()
        ]
    finally:
        conn.close()
    return {
        "table": table,
        "columns": columns,
        "rows": rows,
        "total": total,
        "limit": safe_limit,
        "offset": safe_offset,
    }


@app.get("/api/console/{session_id}/stream")
async def api_console_stream(session_id: str, user: dict = Depends(require_auth)):
    del user
    return StreamingResponse(
        _proxy_session_events(session_id),
        media_type="text/event-stream",
    )


async def _drain_gateway_message(session_id: str, text: str) -> None:
    url = f"{_gateway_base_url().rstrip('/')}/sessions/{session_id}/message"

    def _do_post():
        data = json.dumps({"content": text}).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json", **_gateway_headers()},
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
        except Exception:
            pass

    await asyncio.to_thread(_do_post)


@app.post("/api/console/{session_id}/message")
async def api_console_send_message(
    session_id: str, request: Request, user: dict = Depends(require_auth)
):
    del user
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    asyncio.create_task(_drain_gateway_message(session_id, text))
    return {"status": "sent"}


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
