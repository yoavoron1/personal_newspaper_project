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


def enrich_articles(newspaper_data: Dict, selected_articles: List[Dict]) -> List[Dict]:
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


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    result = load_cached_newspaper()
    if not result:
        return templates.TemplateResponse("index.html", {
            "request": request,
            "title": "העיתון האישי שלך",
            "intro": "",
            "articles": [],
            "coming_soon": True,
        })
    newspaper_data, selected_articles = result
    return templates.TemplateResponse("index.html", {
        "request": request,
        "title": newspaper_data.get("title", "The Weekly Chronicle"),
        "intro": newspaper_data.get("intro", ""),
        "articles": enrich_articles(newspaper_data, selected_articles),
        "coming_soon": False,
    })
