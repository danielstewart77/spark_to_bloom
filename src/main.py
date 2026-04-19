import asyncio
import json
import markdown
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
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


def _gateway_base_url() -> str:
    import os

    return os.getenv("GATEWAY_API_URL") or os.getenv("GRAPH_API_URL") or "http://server:8420"


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


def _proxy_session_events(session_id: str):
    url = f"{_gateway_base_url().rstrip('/')}/sessions/{session_id}/events"

    try:
        request = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
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


@app.get("/canvas", response_class=HTMLResponse)
async def canvas(request: Request):
    html_content = _render_markdown(BASE_DIR / "templates" / "canvas.md")
    return _render_template(request, "canvas.html", content=html_content)


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
