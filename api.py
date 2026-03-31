"""FastAPI endpoints עבור יצירת עיתון אישי."""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Load .env only when running locally — Railway injects variables directly into the environment
if not os.getenv("RAILWAY_ENVIRONMENT"):
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent / ".env")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
CACHE_FILE = BASE_DIR / "newspaper_cache.json"

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

print(f"Server received API_KEY starting with: {os.getenv('API_KEY', '')[:3]}...")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_cached_newspaper() -> Optional[Tuple[Dict, List[Dict]]]:
    """טוען את נתוני העיתון האחרון מהקובץ השמור."""
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return data["newspaper_data"], data["selected_articles"]
    except Exception:
        return None


def enrich_articles(newspaper_data: Dict, selected_articles: List[Dict]) -> List[Dict]:
    """מוסיף URL ותמונה מהמאמרים המקוריים."""
    enriched = []
    for idx, article in enumerate(newspaper_data.get("articles", [])):
        source = selected_articles[idx] if idx < len(selected_articles) else {}
        item = dict(article)
        item["url"] = source.get("url", "")
        item["image"] = source.get("image", "")
        if "commentary" not in item:
            item["commentary"] = item.get("personal_note", "")
        enriched.append(item)
    return enriched


@app.get("/debug-key")
def debug_key():
    """נקודת קצה זמנית לאבחון — מראה אם API_KEY טעון בצד השרת."""
    key = os.getenv("API_KEY", "")
    return {
        "api_key_set": bool(key),
        "api_key_preview": key[:3] + "..." if key else "NOT SET",
        "api_key_length": len(key),
    }


@app.get("/newspaper")
def get_newspaper():
    """מחזיר JSON של העיתון השמור."""
    result = load_cached_newspaper()
    if not result:
        return {"error": "No newspaper data yet. Run main.py to generate."}
    newspaper_data, _ = result
    return newspaper_data


@app.post("/update-news")
async def update_news(request: Request, api_key: str = Query(None)):
    """מקבל נתוני עיתון חדשים מהסקריפט המקומי ושומר אותם."""
    expected_key = os.getenv("API_KEY", "")
    print(f"Received api_key starts with: {api_key[:3] if api_key else 'NONE'}... | expected starts with: {expected_key[:3] if expected_key else 'NONE'}...")

    if not expected_key or api_key != expected_key:
        raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing API key")

    try:
        body = await request.json()
        if "newspaper_data" not in body or "selected_articles" not in body:
            raise HTTPException(status_code=422, detail="Missing newspaper_data or selected_articles")
        CACHE_FILE.write_text(
            json.dumps(body, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("[update-news] Cache updated successfully.")
        return JSONResponse({"status": "ok", "message": "Newspaper data updated"})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to save data: {exc}")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """מציג את העיתון האחרון שנוצר, או הודעת המתנה ידידותית."""
    result = load_cached_newspaper()

    if not result:
        context = {
            "request": request,
            "title": "העיתון האישי שלך",
            "intro": "",
            "articles": [],
            "coming_soon": True,
        }
        return templates.TemplateResponse("index.html", context)

    newspaper_data, selected_articles = result
    context = {
        "request": request,
        "title": newspaper_data.get("title", "The Weekly Chronicle"),
        "intro": newspaper_data.get("intro", ""),
        "articles": enrich_articles(newspaper_data, selected_articles),
        "coming_soon": False,
    }
    return templates.TemplateResponse("index.html", context)
