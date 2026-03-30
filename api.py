"""FastAPI endpoints עבור יצירת עיתון אישי."""

from pathlib import Path

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from main import create_newspaper_data

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/newspaper")
def get_newspaper():
    """מחזיר JSON של עיתון אישי שנוצר דינמית."""
    try:
        result = create_newspaper_data()
    except Exception as exc:
        return {"error": f"Server failed to generate newspaper: {exc}"}

    if not result:
        return {"error": "Could not generate newspaper data"}

    newspaper_data, _ = result
    return newspaper_data


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """מציג עיתון אישי בעיצוב HTML/Tailwind עם Jinja2."""
    try:
        result = create_newspaper_data()
    except Exception as exc:
        return HTMLResponse(f"<h1>Server Error</h1><p>{exc}</p>", status_code=500)

    if not result:
        return HTMLResponse("<h1>No data available</h1>", status_code=500)

    newspaper_data, selected_articles = result
    articles = newspaper_data.get("articles", [])

    # שילוב URL/תמונה מהכתבות המקוריות + תאימות לשדה commentary בתבנית.
    enriched_articles = []
    for idx, article in enumerate(articles):
        source_article = selected_articles[idx] if idx < len(selected_articles) else {}
        enriched = dict(article)
        enriched["url"] = source_article.get("url", "")
        enriched["image"] = source_article.get("image", "")
        if "commentary" not in enriched:
            enriched["commentary"] = enriched.get("personal_note", "")
        enriched_articles.append(enriched)

    context = {
        "request": request,
        "title": newspaper_data.get("title", "The Weekly Chronicle"),
        "intro": newspaper_data.get("intro", ""),
        "articles": enriched_articles,
    }
    return templates.TemplateResponse("index.html", context)
