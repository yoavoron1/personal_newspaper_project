"""FastAPI endpoints for The Personal Times."""

# Load .env BEFORE models are imported so DATABASE_URL is visible to models.py
from dotenv import load_dotenv
load_dotenv()

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, Form, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from werkzeug.security import check_password_hash, generate_password_hash

from models import Article, SessionLocal, User, create_tables

BASE_DIR = Path(__file__).resolve().parent
CACHE_FILE = BASE_DIR / "newspaper_cache.json"

COOKIE_NAME = "user_id"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30   # 30 days


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: connect to PostgreSQL and create tables. Raises on failure."""
    db_url = os.getenv("DATABASE_URL", "")
    masked = db_url[:25] + "…" if len(db_url) > 25 else db_url
    print(f"[startup] Connecting to database: {masked}")
    try:
        create_tables()
        print("[startup] PostgreSQL tables ready ✓")
    except Exception as exc:
        print(f"\n[FATAL] Cannot connect to PostgreSQL:\n  {exc}\n")
        print("  ↳ Check that DATABASE_URL in .env points to the Railway PUBLIC proxy URL,")
        print("    not the internal postgres.railway.internal address.\n")
        raise  # re-raise so uvicorn exits with a non-zero code
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Cookie auth helpers ───────────────────────────────────────────────────────

def get_current_user_id(request: Request) -> Optional[int]:
    """Return the logged-in user's id from the `user_id` cookie, or None."""
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _set_login_cookie(response: Response, user_id: int) -> None:
    """Set the signed-in cookie. HttpOnly + SameSite=lax for basic safety."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=str(user_id),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False,   # flip to True when serving over HTTPS
        path="/",
    )


def _clear_login_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


# ── Data helpers ──────────────────────────────────────────────────────────────

def load_cached_newspaper() -> Optional[Tuple[Dict, List[Dict]]]:
    """Read newspaper_cache.json (kept for /update-news write-back compatibility)."""
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return data["newspaper_data"], data["selected_articles"]
    except Exception:
        return None


def load_articles_from_db(user_id: int) -> Optional[Tuple[str, List[Dict]]]:
    """Fetch a specific user's articles from PostgreSQL.

    Returns (user_full_name, enriched_articles). If the user exists but has no
    articles yet, returns (name, []). If the user doesn't exist at all, returns None.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None

        db_arts = (
            db.query(Article)
            .filter(Article.user_id == user.id)
            .order_by(Article.timestamp.desc())
            .limit(8)
            .all()
        )
        if not db_arts:
            return user.full_name, []

        articles: List[Dict] = []
        for idx, art in enumerate(db_arts):
            content = art.content or ""
            first_para = content.split("\n\n")[0].strip()
            articles.append({
                "id":             idx,
                "title":          art.title or "",
                "short_summary":  first_para[:500],
                "long_summary":   content,
                "image":          art.image_url or "",
                "image_keywords": "",
                "source_name":    art.source or "",
                "source":         art.source or "",
                "topic":          "",
                "why_it_matters": "",
                "personal_impact":"",
                "url":            "",
                "country_origin": "",
                "bullets":        [],
                "commentary":     "",
            })

        return user.full_name, articles

    except Exception as exc:
        print(f"[DB] Error loading articles: {exc}")
        return None
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
#   ROUTES
# ══════════════════════════════════════════════════════════════════════════════

# ── Landing ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    """Public landing page. Sign In / Register CTAs."""
    return templates.TemplateResponse(
        request=request,
        name="landing.html",
        context={},
    )


# ── Dashboard (logged-in newspaper view) ──────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    result = load_articles_from_db(user_id)

    # Cookie points to a user that no longer exists — clear and bounce home
    if result is None:
        resp = RedirectResponse(url="/", status_code=303)
        _clear_login_cookie(resp)
        return resp

    user_name, articles = result
    if not articles:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "title":       "העיתון האישי שלך",
                "intro":       "",
                "articles":    [],
                "coming_soon": True,
            },
        )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title":       "העיתון האישי",
            "intro":       f"שלום {user_name} — הנה הגיליון האישי שלך",
            "articles":    articles,
            "coming_soon": False,
        },
    )


# ── Article detail ────────────────────────────────────────────────────────────

@app.get("/article/{article_id}", response_class=HTMLResponse)
def article_page(request: Request, article_id: int):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    result = load_articles_from_db(user_id)
    if not result or not result[1]:
        raise HTTPException(status_code=404, detail="No newspaper data available")
    _, articles = result
    if article_id < 0 or article_id >= len(articles):
        raise HTTPException(status_code=404, detail="Article not found")
    return templates.TemplateResponse(
        request=request,
        name="article.html",
        context={
            "article":         articles[article_id],
            "newspaper_title": "The Personal Times",
            "article_id":      article_id,
            "total_articles":  len(articles),
        },
    )


# ── Login / Logout ────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if get_current_user_id(request):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": ""},
    )


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    email:    str = Form(...),
    password: str = Form(...),
):
    email = email.strip().lower()
    if not email or not password:
        return templates.TemplateResponse(
            request=request, name="login.html",
            context={"error": "Please enter both email and password."},
            status_code=400,
        )

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user or not check_password_hash(user.password_hash, password):
            return templates.TemplateResponse(
                request=request, name="login.html",
                context={"error": "Invalid email or password."},
                status_code=401,
            )
        user_id = user.id
        user_email = user.email
    finally:
        db.close()

    resp = RedirectResponse(url="/dashboard", status_code=303)
    _set_login_cookie(resp, user_id)
    print(f"[login] {user_email} signed in (user_id={user_id})")
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse(url="/", status_code=303)
    _clear_login_cookie(resp)
    return resp


# ── Registration ──────────────────────────────────────────────────────────────

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    if get_current_user_id(request):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={"error": ""},
    )


@app.post("/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    full_name: str = Form(...),
    email:     str = Form(...),
    password:  str = Form(...),
):
    # Checkbox list `interests` is not declared as a named param because
    # FastAPI/Form can't repeat a key cleanly — read from raw form instead.
    form = await request.form()
    selected_interests = form.getlist("interests")
    interests_csv = ", ".join(i.strip() for i in selected_interests if i.strip())

    full_name = full_name.strip()
    email     = email.strip().lower()
    password  = password or ""

    if not full_name or not email or not password:
        return templates.TemplateResponse(
            request=request, name="register.html",
            context={"error": "Please fill in all required fields."},
            status_code=400,
        )
    if len(password) < 8:
        return templates.TemplateResponse(
            request=request, name="register.html",
            context={"error": "Password must be at least 8 characters."},
            status_code=400,
        )

    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == email).first():
            return templates.TemplateResponse(
                request=request, name="register.html",
                context={"error": "That email is already registered."},
                status_code=409,
            )

        new_user = User(
            email=email,
            password_hash=generate_password_hash(password),
            full_name=full_name,
            # Legacy rich-profile columns stay empty for the new short form.
            occupation="",
            # `interests_text` stores the comma-joined checkbox selection,
            # consumed by main.py when generating personalized articles.
            interests_text=interests_csv,
            bio="",
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        new_user_id = new_user.id
        print(f"[register] New subscriber: {email} | interests={interests_csv or '(none)'}")
    except Exception as exc:
        db.rollback()
        print(f"[register] DB error: {exc}")
        return templates.TemplateResponse(
            request=request, name="register.html",
            context={"error": "Something went wrong saving your details. Please try again."},
            status_code=500,
        )
    finally:
        db.close()

    # Auto-login and send them to their dashboard
    resp = RedirectResponse(url="/dashboard", status_code=303)
    _set_login_cookie(resp, new_user_id)
    return resp


# ── Cache update endpoint (used by main.py pipeline) ──────────────────────────

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


# ══════════════════════════════════════════════════════════════════════════════
#   Entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
