import asyncio
import json
import markdown
import os
import re
import sqlite3
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import websockets
from websockets.exceptions import WebSocketException

from fastapi import Depends, FastAPI, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import auth
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


_canvas_connections: set[WebSocket] = set()
_canvas_elements: list[dict] = []


def _canvas_state_path() -> Path:
    return BASE_DIR.parent / "data" / "canvas_state.json"


def _load_canvas_state() -> list[dict]:
    p = _canvas_state_path()
    try:
        if p.exists():
            with open(p) as f:
                data = json.load(f)
            return data.get("elements", []) if isinstance(data, dict) else []
    except Exception:
        pass
    return []


def _save_canvas_state() -> None:
    p = _canvas_state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump({"elements": _canvas_elements}, f)


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _xml_escape(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _canvas_bounds(elements: list[dict]) -> tuple[float, float, float, float]:
    """Bounding box across all elements. Falls back to a default frame when empty."""
    xs: list[float] = []
    ys: list[float] = []
    for el in elements:
        t = el.get("type")
        if t == "path":
            nums = [float(n) for n in _NUM_RE.findall(el.get("d", ""))]
            # path data is a flat stream of x,y pairs once commands are stripped
            xs.extend(nums[0::2])
            ys.extend(nums[1::2])
        elif t == "text":
            xs.append(float(el.get("x", 0)))
            ys.append(float(el.get("y", 0)))
        elif t == "image":
            x, y = float(el.get("x", 0)), float(el.get("y", 0))
            xs.extend([x, x + float(el.get("w", 0))])
            ys.extend([y, y + float(el.get("h", 0))])
    if not xs or not ys:
        return (0.0, 0.0, 1280.0, 800.0)
    pad = 40.0
    minx, miny = min(xs) - pad, min(ys) - pad
    w = max(xs) - min(xs) + pad * 2
    h = max(ys) - min(ys) + pad * 2
    return (minx, miny, max(w, 1.0), max(h, 1.0))


def _canvas_to_svg() -> str:
    """Compose the current board into a standalone dark-background SVG.

    This is the snapshot Skippy rasterizes (chrome --headless) so he can
    actually see what Daniel drew, since he cannot watch the live websocket.
    """
    elements = _canvas_elements
    minx, miny, w, h = _canvas_bounds(elements)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{minx:.1f} {miny:.1f} {w:.1f} {h:.1f}" '
        f'width="{w:.0f}" height="{h:.0f}">',
        f'<rect x="{minx:.1f}" y="{miny:.1f}" width="{w:.1f}" height="{h:.1f}" fill="#090912"/>',
    ]
    for el in elements:
        t = el.get("type")
        color = _xml_escape(el.get("color", "#c9a84c"))
        if t == "path":
            parts.append(
                f'<path d="{_xml_escape(el.get("d", ""))}" stroke="{color}" '
                f'stroke-width="{el.get("sw", 2)}" fill="none" '
                f'stroke-linecap="round" stroke-linejoin="round"/>'
            )
        elif t == "text":
            parts.append(
                f'<text x="{el.get("x", 0)}" y="{el.get("y", 0)}" fill="{color}" '
                f'font-family="monospace" font-size="14">{_xml_escape(el.get("content", ""))}</text>'
            )
        elif t == "image":
            parts.append(
                f'<image x="{el.get("x", 0)}" y="{el.get("y", 0)}" '
                f'width="{el.get("w", 200)}" height="{el.get("h", 150)}" '
                f'href="{_xml_escape(el.get("src", ""))}" preserveAspectRatio="xMidYMid meet"/>'
            )
    parts.append("</svg>")
    return "".join(parts)


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    init_auth_db()
    global _canvas_elements
    _canvas_elements = _load_canvas_state()
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
    return os.getenv("GATEWAY_API_URL") or "http://hive-comms:8424"


def _lucent_base_url() -> str:
    return os.getenv("LUCENT_API_URL") or "http://hive-lucent:8424"


def _lucent_bearer_token() -> str:
    return os.getenv("LUCENT_BEARER_TOKEN", "")


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


async def _proxy_session_events(session_id: str):
    url = f"{_gateway_base_url().rstrip('/')}/sessions/{session_id}/events"
    headers = {"Accept": "text/event-stream", **_gateway_headers()}
    timeout = httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line.startswith("data: "):
                        continue
                    yield f"{line}\n\n"
    except httpx.HTTPStatusError as exc:
        payload = {"type": "system", "content": f"upstream_error: {exc.response.status_code}"}
        yield f"data: {json.dumps(payload)}\n\n"
    except httpx.RequestError as exc:
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


@app.get("/pullrequests", response_class=HTMLResponse)
async def pullrequests(request: Request):
    return _render_template(request, "pullrequests.html")


@app.get("/downloads/{filename}")
async def download_hive_init_asset(filename: str):
    return _serve_hive_init_asset(filename)


@app.get("/canvas", response_class=HTMLResponse)
async def canvas(request: Request):
    return _render_template(request, "canvas.html")


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
    return get_graph_data(_lucent_base_url(), limit=limit, bearer_token=_lucent_bearer_token())


@app.get("/graph/public-data")
async def graph_public_data(limit: int = 400, user: dict = Depends(require_auth)):
    del user
    data = get_graph_data(_lucent_base_url(), limit=limit, bearer_token=_lucent_bearer_token())
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
    return _render_template(request, "terminal.html")


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


@app.get("/api/terminal/sessions")
async def api_terminal_sessions(user: dict = Depends(require_auth)):
    """Flat, mind-labeled session list — the /terminal session picker.

    Each row is "drop into this conversation," not "pick a mind": mind name,
    short mind_id, age, and status, sorted most-recently-active first.
    """
    del user
    try:
        minds = await _gateway_json("/broker/minds")
        if not isinstance(minds, list):
            minds = []
    except Exception:
        minds = []
    mind_names = {m.get("id"): m.get("name", "mind") for m in minds if isinstance(m, dict)}

    try:
        sessions = await _gateway_json("/sessions")
        if not isinstance(sessions, list):
            sessions = []
    except Exception:
        sessions = []

    now = int(time.time())
    rows = []
    for s in sessions:
        if not isinstance(s, dict) or s.get("owner_type") == "scheduler":
            continue
        mind_id = s.get("mind_id") or ""
        rows.append({
            "id": s.get("id"),
            "mind_id": mind_id,
            "mind_name": mind_names.get(mind_id, mind_id or "mind"),
            "short_id": (s.get("id") or "")[:8],
            "status": s.get("status"),
            "last_active": s.get("last_active"),
            "age": _relative_age(now, s.get("last_active")),
            "summary": (s.get("summary") or "").strip(),
            # Lineage, so a tile whose session rotated can identify its
            # actual replacement instead of adopting whichever sibling
            # session happens to be live on the same mind.
            "rotated_from": s.get("rotated_from") or "",
        })
    rows.sort(key=lambda r: -float(r.get("last_active") or 0))
    return rows


@app.post("/api/terminal/sessions")
async def api_terminal_create_session(request: Request, user: dict = Depends(require_auth)):
    """The "new session against mind X" affordance for when nothing relevant is live."""
    del user
    body = await request.json()
    mind_id = (body.get("mind_id") or "").strip()
    if not mind_id:
        raise HTTPException(status_code=400, detail="mind_id is required")
    return await _create_gateway_session(mind_id)


async def _create_gateway_session(mind_id: str) -> dict:
    # client_ref is the primary key of the gateway's active_sessions binding
    # table, so it has to be unique per terminal tile. A shared constant makes
    # every open tile overwrite the same row: rotation arms the wrong session
    # and carry-forward memory lands in a different tile than it was written
    # for.
    client_ref = f"terminal-{uuid.uuid4()}"

    def _do_post():
        url = f"{_gateway_base_url().rstrip('/')}/sessions"
        data = json.dumps({
            "mind_id": mind_id,
            "model": "sonnet",
            "owner_type": "web",
            "owner_ref": "terminal",
            "client_ref": client_ref,
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


def _labels_db() -> sqlite3.Connection:
    """Terminal session labels (name + color) live next to the auth tables.

    Server-side so they follow the user across devices — localStorage kept
    them per-browser, which read as losing the session on the phone.
    """
    conn = auth._connect()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS terminal_labels (
               session_id TEXT PRIMARY KEY,
               name TEXT NOT NULL DEFAULT '',
               color TEXT NOT NULL DEFAULT '',
               updated_at INTEGER NOT NULL
           )"""
    )
    conn.commit()
    return conn


_LABEL_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")


@app.get("/api/terminal/labels")
async def api_terminal_labels(user: dict = Depends(require_auth)):
    del user
    conn = _labels_db()
    try:
        rows = conn.execute("SELECT session_id, name, color FROM terminal_labels").fetchall()
    finally:
        conn.close()
    return {r["session_id"]: {"name": r["name"], "color": r["color"]} for r in rows}


@app.put("/api/terminal/labels/{session_id}")
async def api_terminal_label_put(
    session_id: str, request: Request, user: dict = Depends(require_auth)
):
    del user
    body = await request.json()
    name = (body.get("name") or "").strip()[:40]
    color = (body.get("color") or "").strip()
    if color and not _LABEL_COLOR_RE.match(color):
        raise HTTPException(status_code=400, detail="color must be a hex value")
    conn = _labels_db()
    try:
        if not name and not color:
            conn.execute("DELETE FROM terminal_labels WHERE session_id = ?", (session_id,))
        else:
            conn.execute(
                """INSERT INTO terminal_labels (session_id, name, color, updated_at)
                   VALUES (?, ?, ?, strftime('%s','now'))
                   ON CONFLICT(session_id) DO UPDATE
                   SET name = excluded.name, color = excluded.color,
                       updated_at = excluded.updated_at""",
                (session_id, name, color),
            )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "session_id": session_id, "name": name, "color": color}


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


def _gateway_ws_url(session_id: str, cols: str = "80", rows: str = "24") -> str:
    ws_base = _gateway_base_url().rstrip("/").replace("https://", "wss://").replace("http://", "ws://")
    query = urllib.parse.urlencode({"cols": cols, "rows": rows})
    return f"{ws_base}/sessions/{session_id}/attach?{query}"


async def _pump_terminal_ws(browser_ws: WebSocket, mind_ws) -> None:
    """Bridge the browser's terminal WS and hive-comms' attach WS.

    Frame types are load-bearing on the browser→mind leg: BINARY frames
    are raw terminal bytes, TEXT frames are JSON control messages
    (resize) — so TEXT is forwarded as TEXT (websockets sends str frames
    as TEXT), never re-encoded into the byte stream. Whichever side
    closes first ends the bridge — an attached pty and a browser tab
    have no independent life of their own once either end is gone.
    """
    async def browser_to_mind() -> None:
        while True:
            msg = await browser_ws.receive()
            if msg.get("type") == "websocket.disconnect":
                return
            if msg.get("bytes"):
                await mind_ws.send(msg["bytes"])
            elif msg.get("text"):
                await mind_ws.send(msg["text"])

    async def mind_to_browser() -> None:
        async for data in mind_ws:
            if isinstance(data, str):
                data = data.encode()
            await browser_ws.send_bytes(data)

    tasks = [asyncio.ensure_future(browser_to_mind()), asyncio.ensure_future(mind_to_browser())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for task in tasks:
            task.cancel()


def _relayable_close_code(code: int | None) -> int | None:
    """The gateway close code to pass to the browser, if any.

    Every real code relays, whatever its range. The ones that matter are
    not all private-use: 4410 is "session closed", 1012 is "another window
    took the keyboard", 1008 is "the mind refused the terminal" — the last
    two are how a tile knows to stand down instead of reconnecting. An
    earlier 4000-4999 filter swallowed 1012, so an evicted desktop tile
    read the eviction as a dropped connection and reattached, which
    evicted the phone, which reattached, which evicted the desktop: a
    tug-of-war that repainted both terminals about once a second and
    cross-fed each tile the other's geometry (a 140-column repaint
    shredded into a 44-column phone).

    1005/1006 are synthetic "no close frame arrived" markers that cannot
    legally go on the wire, so they relay as nothing.
    """
    if not code or code in (1005, 1006):
        return None
    return code


@app.websocket("/api/terminal/attach/{session_id}")
async def ws_terminal_attach(websocket: WebSocket, session_id: str):
    """Reverse-proxy a browser terminal WS into hive-comms' session attach.

    True interactive terminal, not the chat-pattern SSE the /console page
    uses — see web-terminal-interface.md in the owner repo's backlog. Gated by the same
    session cookie as every other page here; unlike /ws/canvas's degrade
    -to-read-only pattern, an unauthenticated caller is rejected outright
    since this is full shell access.
    """
    user = get_current_user_from_request(websocket)
    if user is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    cols = websocket.query_params.get("cols") or "80"
    rows = websocket.query_params.get("rows") or "24"
    try:
        async with websockets.connect(
            _gateway_ws_url(session_id, cols=cols, rows=rows),
            additional_headers=_gateway_headers(),
        ) as mind_ws:
            await _pump_terminal_ws(websocket, mind_ws)
            code = _relayable_close_code(mind_ws.close_code)
            if code:
                try:
                    await websocket.close(code=code, reason=mind_ws.close_reason or "")
                except RuntimeError:
                    pass  # browser already gone
    except (OSError, WebSocketException):
        await websocket.close(code=1011, reason="terminal unreachable")


@app.get("/api/console/{session_id}/stream")
async def api_console_stream(session_id: str, user: dict = Depends(require_auth)):
    del user
    return StreamingResponse(
        _proxy_session_events(session_id),
        media_type="text/event-stream",
        headers={
            # SSE must never be buffered by intermediaries — a buffered
            # stream delivers events in delayed bursts and idle timeouts
            # sever it mid-turn.
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
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


@app.delete("/api/terminal/sessions/{session_id}")
async def api_terminal_session_delete(session_id: str, user: dict = Depends(require_auth)):
    del user

    def _do_delete():
        url = f"{_gateway_base_url().rstrip('/')}/sessions/{session_id}"
        req = urllib.request.Request(url, headers=_gateway_headers(), method="DELETE")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        return await asyncio.to_thread(_do_delete)
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=exc.code, detail="Gateway delete failed") from exc
    except OSError as exc:
        raise HTTPException(status_code=502, detail=f"Gateway unavailable: {exc}") from exc


@app.post("/api/console/{session_id}/interrupt")
async def api_console_interrupt(session_id: str, user: dict = Depends(require_auth)):
    del user

    def _do_post():
        url = f"{_gateway_base_url().rstrip('/')}/sessions/{session_id}/interrupt"
        req = urllib.request.Request(
            url, data=b"",
            headers={"Content-Type": "application/json", **_gateway_headers()},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        return await asyncio.to_thread(_do_post)
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=exc.code, detail="Gateway interrupt failed") from exc
    except OSError as exc:
        raise HTTPException(status_code=502, detail=f"Gateway unavailable: {exc}") from exc


_CANVAS_KEYS = {
    "path": ("type", "id", "color", "d", "sw"),
    "text": ("type", "id", "x", "y", "content", "color"),
    "image": ("type", "id", "x", "y", "w", "h", "src"),
}


def _apply_canvas_message(data: dict) -> bool:
    """Apply one canvas mutation to in-memory state and persist it.

    Shared by the websocket surface and the bearer-guarded /canvas/push
    endpoint so the two paths can never drift. Mutates ``data`` in place to
    fill a missing id. Returns True when a known message type was handled.
    """
    msg_type = data.get("type")
    if msg_type == "clear":
        _canvas_elements.clear()
    elif msg_type in _CANVAS_KEYS:
        data.setdefault("id", str(uuid.uuid4()))
        _canvas_elements.append({k: data[k] for k in _CANVAS_KEYS[msg_type] if k in data})
    elif msg_type == "move":
        el_id = data.get("id")
        nx, ny = data.get("x"), data.get("y")
        for el in _canvas_elements:
            if el.get("id") == el_id and el.get("type") in ("text", "image"):
                el["x"] = nx
                el["y"] = ny
                break
    elif msg_type == "delete":
        el_id = data.get("id")
        _canvas_elements[:] = [e for e in _canvas_elements if e.get("id") != el_id]
    else:
        return False
    _save_canvas_state()
    return True


async def _broadcast_canvas(data: dict, exclude: WebSocket | None = None) -> None:
    for conn in list(_canvas_connections):
        if conn is exclude:
            continue
        try:
            await conn.send_json(data)
        except Exception:
            _canvas_connections.discard(conn)


def _canvas_push_token() -> str:
    """Bearer that authorizes Skippy's /canvas/push writes.

    Prefers a dedicated CANVAS_PUSH_TOKEN; falls back to the house
    COMMS_BEARER_TOKEN, which both this container and Skippy already hold,
    so drawing works without recreating the container.
    """
    return os.getenv("CANVAS_PUSH_TOKEN") or os.getenv("COMMS_BEARER_TOKEN", "")


@app.post("/canvas/push")
async def canvas_push(request: Request):
    expected = _canvas_push_token()
    if not expected:
        raise HTTPException(status_code=503, detail="canvas push token not configured")
    if request.headers.get("Authorization", "") != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="unauthorized")
    data = await request.json()
    if not isinstance(data, dict) or not _apply_canvas_message(data):
        raise HTTPException(status_code=400, detail="unknown or malformed canvas message")
    await _broadcast_canvas(data)
    return {"ok": True, "id": data.get("id"), "type": data.get("type")}


@app.get("/canvas/render.svg")
async def canvas_render_svg():
    """Standalone SVG snapshot of the board, for Skippy to rasterize and read."""
    return Response(content=_canvas_to_svg(), media_type="image/svg+xml")


@app.post("/canvas/submit")
async def canvas_submit(request: Request):
    """Daniel's 'I'm done drawing' poke. Fires a Skippy turn via the broker."""
    if not get_current_user_from_request(request):
        raise HTTPException(status_code=401, detail="unauthorized")
    try:
        body = await request.json()
    except Exception:
        body = {}
    note = (body or {}).get("note", "") if isinstance(body, dict) else ""
    element_count = len(_canvas_elements)
    content = (
        "Daniel finished a drawing pass on the Spark to Bloom whiteboard and wants you "
        f"to look. The board currently has {element_count} element(s). Rasterize "
        "GET /canvas/render.svg and respond on Telegram with what you see."
    )
    if note:
        content += f" Daniel's note: {note}"

    target_name = os.getenv("MIND_NAME", "skippy")
    headers = _gateway_headers()
    headers["Content-Type"] = "application/json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # The broker keys minds on their UUID (mind_id), not the display
            # name, so resolve the id from the registry before dispatching.
            minds_resp = await client.get(
                f"{_gateway_base_url()}/broker/minds", headers=headers
            )
            minds_resp.raise_for_status()
            minds = minds_resp.json()
            mind_id = next(
                (m.get("id") for m in minds if m.get("name") == target_name), None
            )
            if not mind_id:
                raise HTTPException(
                    status_code=502, detail=f"mind '{target_name}' not registered in broker"
                )
            payload = {
                "conversation_id": str(uuid.uuid4()),
                "from_mind": "canvas",
                "to_mind": mind_id,
                "content": content,
                "metadata": {"request_type": "canvas_review", "triggered_by": "canvas"},
            }
            resp = await client.post(
                f"{_gateway_base_url()}/broker/messages", json=payload, headers=headers
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"could not reach Skippy: {exc}") from exc
    return {"ok": True, "dispatched_to": target_name, "element_count": element_count}


@app.websocket("/ws/canvas")
async def ws_canvas(websocket: WebSocket):
    user = get_current_user_from_request(websocket)
    can_draw = user is not None
    await websocket.accept()
    _canvas_connections.add(websocket)
    try:
        await websocket.send_json({"type": "state", "elements": _canvas_elements})
        while True:
            data = await websocket.receive_json()
            if not can_draw:
                continue
            if _apply_canvas_message(data):
                await _broadcast_canvas(data, exclude=websocket)
    except WebSocketDisconnect:
        _canvas_connections.discard(websocket)
    except Exception:
        _canvas_connections.discard(websocket)


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


def _lucent_headers() -> dict:
    token = _lucent_bearer_token()
    if not token:
        raise HTTPException(status_code=503, detail="lucent bearer token not configured")
    return {"Authorization": f"Bearer {token}"}


async def _lucent_request(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json_body: dict | None = None,
):
    url = f"{_lucent_base_url().rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.request(
            method, url, params=params, json=json_body, headers=_lucent_headers()
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()


_RULE_SOURCES = {"always-remember", "user"}


def _normalize_rule_row(row: dict, alias_index: dict) -> dict:
    raw_mind = row.get("mind_id") or ""
    entry = alias_index.get(raw_mind)
    display = entry["name"] if entry else raw_mind
    return {
        "id": row.get("id"),
        "content": row.get("content") or "",
        "mind_id": raw_mind,
        "mind_display": display,
        "tier": row.get("tier") or "",
        "source": row.get("source") or "",
        "data_class": row.get("data_class") or "",
        "tags": row.get("tags") or "",
        "created_at": row.get("created_at"),
    }


async def _broker_minds_safe() -> list[dict]:
    try:
        raw = await _gateway_json("/broker/minds")
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    return [m for m in raw if isinstance(m, dict)]


def _build_alias_index(minds: list[dict]) -> dict:
    """Map every alias (UUID and short name) to a canonical mind entry.

    Lucent rows historically stamp `mind_id` with either the UUID or the
    short name, depending on which write path created them. This index lets
    the rules dashboard treat them as the same mind for filtering and
    display.
    """
    index: dict = {}
    for m in minds:
        uuid = (m.get("id") or "").strip()
        name = (m.get("name") or "").strip()
        if not uuid and not name:
            continue
        entry = {"uuid": uuid, "name": name or uuid, "aliases": [a for a in (uuid, name) if a]}
        for alias in entry["aliases"]:
            index[alias] = entry
    index["shared"] = {"uuid": "shared", "name": "shared", "aliases": ["shared"]}
    return index


async def _fetch_rules_for_mind(
    tier: str, mind_id: str | None, alias_index: dict
) -> list[dict]:
    aliases = [None]
    if mind_id and mind_id != "all":
        entry = alias_index.get(mind_id)
        aliases = entry["aliases"] if entry else [mind_id]
    seen_ids: set = set()
    out: list[dict] = []
    for alias in aliases:
        params: dict = {"tier": tier, "limit": 100, "offset": 0}
        if alias is not None:
            params["mind_id"] = alias
        fetched = 0
        while True:
            data = await _lucent_request("GET", "/memory/list", params=params)
            entries = data.get("entries") if isinstance(data, dict) else []
            if not entries:
                break
            for e in entries:
                if e.get("source") not in _RULE_SOURCES:
                    continue
                rid = e.get("id")
                if rid in seen_ids:
                    continue
                seen_ids.add(rid)
                out.append(_normalize_rule_row(e, alias_index))
            fetched += len(entries)
            total = int(data.get("total") or 0)
            if fetched >= total or fetched >= 1000:
                break
            params["offset"] = fetched
    return out


@app.get("/rules", response_class=HTMLResponse)
async def rules_page(request: Request):
    if not get_current_user_from_request(request):
        return _login_redirect_for(request)
    minds = await _broker_minds_safe()
    alias_to_canonical: dict[str, str] = {"shared": "shared"}
    for m in minds:
        uuid = (m.get("id") or "").strip()
        name = (m.get("name") or "").strip()
        canonical = uuid or name
        if uuid:
            alias_to_canonical[uuid] = canonical
        if name:
            alias_to_canonical[name] = canonical
    return _render_template(
        request,
        "rules.html",
        minds=minds,
        alias_to_canonical_json=json.dumps(alias_to_canonical),
    )


@app.get("/api/rules")
async def api_rules_list(
    mind_id: str | None = None,
    tier: str | None = None,
    user: dict = Depends(require_auth),
):
    del user
    tiers = ["standing", "contextual"] if not tier or tier == "all" else [tier]
    minds = await _broker_minds_safe()
    alias_index = _build_alias_index(minds)
    rows: list[dict] = []
    seen_ids: set = set()
    for t in tiers:
        for row in await _fetch_rules_for_mind(t, mind_id, alias_index):
            if row["id"] in seen_ids:
                continue
            seen_ids.add(row["id"])
            rows.append(row)
    rows.sort(key=lambda r: (r["tier"] != "standing", -(r["created_at"] or 0)))
    return {"rules": rows, "count": len(rows)}


@app.post("/api/rules")
async def api_rules_create(request: Request, user: dict = Depends(require_auth)):
    del user
    body = await request.json()
    content = (body.get("content") or "").strip()
    mind_id = (body.get("mind_id") or "").strip()
    tier = (body.get("tier") or "").strip()
    data_class = (body.get("data_class") or "feedback").strip()
    tags = (body.get("tags") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")
    if not mind_id:
        raise HTTPException(status_code=400, detail="mind_id is required")
    if tier not in {"standing", "contextual"}:
        raise HTTPException(status_code=400, detail="tier must be standing or contextual")
    source = "always-remember" if tier == "standing" else "user"
    payload = {
        "content": content,
        "mind_id": mind_id,
        "tier": tier,
        "source": source,
        "data_class": data_class,
        "tags": tags,
    }
    return await _lucent_request("POST", "/memory/store", json_body=payload)


@app.put("/api/rules/{rule_id}")
async def api_rules_update(rule_id: str, request: Request, user: dict = Depends(require_auth)):
    del user
    body = await request.json()
    content = (body.get("content") or "").strip()
    tags = (body.get("tags") or "").strip()
    new_mind = (body.get("mind_id") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")
    # Intentionally never forward data_class on update: lucent's memory_update
    # rewrites `tier` from DATA_CLASS_REGISTRY whenever data_class is set,
    # which would silently demote standing rules to contextual.
    payload: dict = {"content": content, "tags": tags}
    if new_mind:
        alias_index = _build_alias_index(await _broker_minds_safe())
        entry = alias_index.get(new_mind)
        if entry:
            payload["mind_id"] = entry["uuid"] or entry["name"]
        elif new_mind == "shared":
            payload["mind_id"] = "shared"
        else:
            raise HTTPException(status_code=400, detail=f"unknown mind: {new_mind}")
    return await _lucent_request("PUT", f"/memory/{rule_id}", json_body=payload)


@app.delete("/api/rules/{rule_id}")
async def api_rules_delete(rule_id: str, user: dict = Depends(require_auth)):
    del user
    return await _lucent_request("DELETE", f"/memory/{rule_id}")


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


def _btc_ledger_base_url() -> str:
    return os.getenv("BTC_LEDGER_URL", "http://btc-ledger:8427").rstrip("/")


def _btc_ledger_headers() -> dict:
    token = os.getenv("BTC_LEDGER_API_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="btc-ledger token not configured")
    return {"Authorization": f"Bearer {token}"}


async def _btc_ledger_get(path: str, params: dict | None = None):
    url = f"{_btc_ledger_base_url()}{path}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params, headers=_btc_ledger_headers())
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc)) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"btc-ledger unreachable: {exc}") from exc


@app.get("/btc", response_class=HTMLResponse)
async def btc_dashboard(request: Request):
    if not get_current_user_from_request(request):
        return _login_redirect_for(request)
    return _render_template(request, "btc.html")


@app.get("/api/btc/stats")
async def api_btc_stats(user: dict = Depends(require_auth)):
    del user
    return await _btc_ledger_get("/stats")


@app.get("/api/btc/observations")
async def api_btc_observations(
    days: int = 90,
    user: dict = Depends(require_auth),
):
    del user
    from_ts = int(time.time()) - days * 86400
    return await _btc_ledger_get("/observations", params={"from": from_ts, "limit": 10000})


@app.get("/api/btc/alerts")
async def api_btc_alerts(
    days: int = 180,
    user: dict = Depends(require_auth),
):
    del user
    from_ts = int(time.time()) - days * 86400
    return await _btc_ledger_get("/alerts", params={"from": from_ts, "limit": 500})


@app.get("/api/btc/latest")
async def api_btc_latest(user: dict = Depends(require_auth)):
    del user
    return await _btc_ledger_get("/observations/latest")


@app.get("/api/btc/purchases")
async def api_btc_purchases(
    days: int = 3650,
    user: dict = Depends(require_auth),
):
    del user
    from_ts = int(time.time()) - days * 86400
    return await _btc_ledger_get("/purchases", params={"from": from_ts, "limit": 10000})


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
