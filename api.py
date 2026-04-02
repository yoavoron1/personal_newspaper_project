"""FastAPI endpoints עבור יצירת עיתון אישי."""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
CACHE_FILE = BASE_DIR / "newspaper_cache.json"

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_cached_newspaper() -> Optional[Tuple[Dict, List[Dict]]]:
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return data["newspaper_data"], data["selected_articles"]
    except Exception:
        return None


def _build_unsplash_url(article: Dict, width: int = 800, height: int = 600) -> str:
    """Builds a dynamic Unsplash URL from image_keywords or topic."""
    raw = (article.get("image_keywords") or article.get("topic") or "news world").strip()
    words = [w.strip(".,;:") for w in raw.split() if w.strip()][:4]
    slug = quote(",".join(words), safe=",")
    return f"https://source.unsplash.com/featured/{width}x{height}/?{slug}"


def enrich_articles(newspaper_data: Dict, selected_articles: List[Dict]) -> List[Dict]:
    enriched = []
    for idx, article in enumerate(newspaper_data.get("articles", [])):
        source = selected_articles[idx] if idx < len(selected_articles) else {}
        item = dict(article)
        item["id"] = idx
        # New Tavily flow: fields already embedded; old NewsAPI flow: fall back to source
        item["url"] = item.get("url") or source.get("url", "")
        item["source_name"] = item.get("source_name") or source.get("source_name", "")
        item["country_origin"] = item.get("country_origin") or source.get("country_origin", "")
        # Resolve image: Tavily direct → source image → dynamic Unsplash keyword URL
        img = item.get("image") or source.get("image", "")
        item["image"] = img if img else _build_unsplash_url(item)
        # short_summary (new): paragraph text for homepage cards
        item.setdefault("short_summary", "")
        # bullets (legacy): keep for old-cache backward compatibility
        if "bullets" not in item:
            summary = item.get("summary") or item.get("details") or ""
            item["bullets"] = [summary] if summary else []
        # Normalise commentary field for old-format articles
        if "commentary" not in item:
            item["commentary"] = item.get("personal_note", "")
        # Ensure deep-dive fields exist
        item.setdefault("long_summary", "")
        item.setdefault("personal_impact", "")
        enriched.append(item)
    return enriched


@app.post("/update-news")
async def update_news(request: Request, api_key: str = Query(None)):
    expected = os.getenv("API_KEY", "")
    print(f"[update-news] received={api_key[:3] if api_key else 'NONE'} expected={expected[:3] if expected else 'NONE'}")
    if expected and api_key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
    body = await request.json()
    CACHE_FILE.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[update-news] Cache updated successfully.")
    return JSONResponse({"status": "ok"})


@app.get("/article/{article_id}", response_class=HTMLResponse)
def article_page(request: Request, article_id: int):
    result = load_cached_newspaper()
    if not result:
        raise HTTPException(status_code=404, detail="No newspaper data available")
    newspaper_data, selected_articles = result
    articles = enrich_articles(newspaper_data, selected_articles)
    if article_id < 0 or article_id >= len(articles):
        raise HTTPException(status_code=404, detail="Article not found")
    return templates.TemplateResponse(
        request=request,
        name="article.html",
        context={
            "article": articles[article_id],
            "newspaper_title": newspaper_data.get("title", "העיתון האישי"),
            "article_id": article_id,
            "total_articles": len(articles),
        },
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    result = load_cached_newspaper()
    if not result:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "title": "העיתון האישי שלך",
                "intro": "",
                "articles": [],
                "coming_soon": True,
            },
        )
    newspaper_data, selected_articles = result
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title": newspaper_data.get("title", "The Weekly Chronicle"),
            "intro": newspaper_data.get("intro", ""),
            "articles": enrich_articles(newspaper_data, selected_articles),
            "coming_soon": False,
        },
    )
