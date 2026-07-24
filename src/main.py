import json
import markdown
import os
import re
import uuid
import urllib.error
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from fastapi import Depends, FastAPI, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response
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
