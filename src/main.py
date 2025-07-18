import os
import markdown
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Initialize FastAPI app
app = FastAPI(
    title="Spark to Bloom",
    description="A blog about AI, orchestration, and development thoughts",
    version="1.0.0"
)

# Get the directory where this script is located
BASE_DIR = Path(__file__).resolve().parent

# Mount static files
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Initialize Jinja2 templates
templates = Jinja2Templates(directory=BASE_DIR / "templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page"""
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """About page"""
    return templates.TemplateResponse("about.html", {"request": request})

@app.get("/pullrequests", response_class=HTMLResponse)
async def pullrequests(request: Request):
    """Pull requests page"""
    return templates.TemplateResponse("pullrequests.html", {"request": request})

@app.get("/pages/{subpath:path}", response_class=HTMLResponse)
async def page(request: Request, subpath: str):
    """Render markdown pages from templates/pages/"""
    md_path = BASE_DIR / "templates" / "pages" / subpath
    
    # Security check - ensure the path is within the templates/pages directory
    try:
        md_path = md_path.resolve()
        if not str(md_path).startswith(str(BASE_DIR / "templates" / "pages")):
            raise HTTPException(status_code=404, detail="Page not found")
    except (OSError, ValueError):
        raise HTTPException(status_code=404, detail="Page not found")
    
    # Check if file exists
    if not md_path.exists() or not md_path.is_file():
        raise HTTPException(status_code=404, detail="Page not found")
    
    try:
        # Read and convert markdown
        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        html_content = markdown.markdown(
            md_content, 
            extensions=['fenced_code', 'codehilite', 'toc']
        )
        
        return templates.TemplateResponse(
            "page.html", 
            {"request": request, "content": html_content}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading page: {str(e)}")

@app.get("/pr/{subpath:path}", response_class=HTMLResponse)
async def blog_article(request: Request, subpath: str):
    """Render markdown blog articles from templates/pr/"""
    md_path = BASE_DIR / "templates" / "pr" / subpath
    
    # Security check - ensure the path is within the templates/pr directory
    try:
        md_path = md_path.resolve()
        if not str(md_path).startswith(str(BASE_DIR / "templates" / "pr")):
            raise HTTPException(status_code=404, detail="Article not found")
    except (OSError, ValueError):
        raise HTTPException(status_code=404, detail="Article not found")
    
    # Check if file exists
    if not md_path.exists() or not md_path.is_file():
        raise HTTPException(status_code=404, detail="Article not found")
    
    try:
        # Read and convert markdown
        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        html_content = markdown.markdown(
            md_content, 
            extensions=['fenced_code', 'codehilite', 'toc']
        )
        
        return templates.TemplateResponse(
            "pr.html", 
            {"request": request, "content": html_content}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading article: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message": "Spark to Bloom is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=5000,
        reload=False,
        log_level="info"
    )
