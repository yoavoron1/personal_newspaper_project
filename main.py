"""News generation pipeline — fully PostgreSQL-driven.

Flow:
  DB (latest user) → GPT-4o-mini (topics) → Tavily (articles)
  → GPT-4o (newspaper) → DB (save) → Railway (push) → Email (optional)
"""

import os
from typing import Dict, List, Optional

import requests as http_requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from config import get_settings
from models import Article, SessionLocal, User, create_tables
from services.ai_service import AIService
from services.email_service import build_email_html, send_email
from services.news_service import fetch_articles_with_tavily
from utils.json_utils import safe_json_loads

RAILWAY_URL = "https://personalnewspaperproject-production.up.railway.app"


# ── Step 0: DB bootstrap ──────────────────────────────────────────────────────

def ensure_db() -> bool:
    """Create tables if they don't exist. Returns False on connection failure."""
    try:
        create_tables()
        print("[DB] Schema ready ✓")
        return True
    except Exception as exc:
        print(f"[FATAL] Cannot reach PostgreSQL: {exc}")
        print("  ↳ Make sure DATABASE_URL in .env points to the Railway public proxy URL.")
        return False


# ── Step 1: Fetch user ────────────────────────────────────────────────────────

def get_latest_user() -> Optional[User]:
    """Return the most recently registered user, or None."""
    db = SessionLocal()
    try:
        user = db.query(User).order_by(User.created_at.desc()).first()
        if not user:
            print("[DB] No users found. Please register first at /register")
            return None
        print(f"[DB] Generating newspaper for: {user.full_name} ({user.email})")
        return user
    except Exception as exc:
        print(f"[DB] Could not fetch user: {exc}")
        return None
    finally:
        db.close()


def build_profile(user: User) -> Dict[str, str]:
    """Assemble the user's questionnaire answers into a clean profile dict."""
    return {
        "name":       user.full_name,
        "occupation": (user.occupation     or "").strip(),
        "interests":  (user.interests_text or "").strip(),
        "bio":        (user.bio            or "").strip(),
    }


# ── Step 2: Generate personalised Tavily topics ───────────────────────────────

def generate_topics(profile: Dict[str, str], ai: AIService) -> List[str]:
    """Use GPT-4o-mini to derive 5 focused English news-search queries from the profile."""
    prompt = f"""You are a news research assistant.

Based on this user's profile, generate exactly 5 specific English search queries
for a news aggregator. Queries must target *recent, real-world* events and trends.

Return ONLY valid JSON: {{"topics": ["query 1", "query 2", "query 3", "query 4", "query 5"]}}

User profile:
  Name:       {profile['name']}
  Occupation: {profile['occupation'] or '(not provided)'}
  Interests:  {profile['interests'] or '(not provided)'}
  Bio:        {profile['bio'] or '(not provided)'}

Rules:
- All queries in English, 4-8 words each
- Cover different facets of the user's interests — no two queries on the same sub-topic
- Include the year 2026 in at least 3 queries
- Be specific: prefer "Israeli shekel exchange rate 2026" over "finance news"
"""
    try:
        response = ai.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=250,
        )
        data = safe_json_loads(response.choices[0].message.content)
        topics = [t for t in (data or {}).get("topics", []) if isinstance(t, str) and t.strip()]
        if topics:
            print(f"[AI] Personalised topics generated ({len(topics)}):")
            for t in topics:
                print(f"   • {t}")
            return topics[:5]
    except Exception as exc:
        print(f"[AI] Topic generation failed: {exc} — using profile-based fallback.")

    # Fallback: construct basic queries from the profile text
    interests_snippet = (profile["interests"] or profile["occupation"] or "world news")[:60]
    occupation_snippet = (profile["occupation"] or "technology")[:40]
    return [
        f"{interests_snippet} 2026",
        f"{occupation_snippet} industry trends 2026",
        "global economy financial markets 2026",
        "science technology innovation 2026",
        "culture arts events 2026",
    ]


# ── Step 3: Build writing style from profile ──────────────────────────────────

def build_writing_style(profile: Dict[str, str]) -> str:
    parts = ["Deep, analytical Hebrew — rich, precise language with cultural and economic context."]
    if profile["occupation"]:
        parts.append(f"The reader works in: {profile['occupation']}.")
    if profile["bio"]:
        parts.append(f"Personal context: {profile['bio']}.")
    parts.append("Write for an educated reader who wants depth and insight, not just headlines.")
    return " ".join(parts)


# ── Step 5: Save articles to DB ───────────────────────────────────────────────

def save_articles_to_db(user_id: int, newspaper_data: Dict) -> int:
    """Delete this user's old articles, then insert the newly generated ones.
    Returns the count of saved articles."""
    articles = newspaper_data.get("articles", [])
    if not articles:
        print("[DB] No articles to save.")
        return 0

    db = SessionLocal()
    try:
        deleted = db.query(Article).filter(Article.user_id == user_id).delete()
        print(f"[DB] Removed {deleted} old article(s)")

        for art in articles:
            db.add(Article(
                user_id=user_id,
                title=(art.get("title") or "")[:500],
                content=art.get("long_summary") or art.get("short_summary") or "",
                image_url=(art.get("image") or "")[:1000],
                source=(art.get("source_name") or "")[:255],
            ))

        db.commit()
        print(f"[DB] Saved {len(articles)} new article(s) for user_id={user_id}")
        return len(articles)
    except Exception as exc:
        db.rollback()
        print(f"[DB] Error saving articles: {exc}")
        return 0
    finally:
        db.close()


# ── Step 6: Push live to Railway web app ──────────────────────────────────────

def push_to_railway(newspaper_data: Dict, selected_articles: List[Dict]) -> None:
    """POST the newspaper data to the Railway API so the website updates instantly."""
    api_key = os.getenv("API_KEY", "")
    if not api_key:
        print("[Railway] API_KEY not set — skipping push.")
        return
    try:
        response = http_requests.post(
            f"{RAILWAY_URL}/update-news?api_key={api_key}",
            json={"newspaper_data": newspaper_data, "selected_articles": selected_articles},
            timeout=30,
        )
        if response.status_code == 200:
            print(f"[Railway] Website updated ✓  ({RAILWAY_URL})")
        else:
            print(f"[Railway] Push failed — {response.status_code}: {response.text[:200]}")
    except Exception as exc:
        print(f"[Railway] Could not reach server: {exc}")


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_pipeline() -> bool:
    """
    Orchestrates the full newspaper generation flow.
    Returns True on success, False on any fatal error.
    """
    settings = get_settings()

    if not settings.tavily_api_key:
        print("[ERROR] TAVILY_API_KEY is not set.")
        return False
    if not settings.openai_api_key:
        print("[ERROR] OPENAI_API_KEY is not set.")
        return False

    # ── 0. DB ────────────────────────────────────────────────────────────────
    if not ensure_db():
        return False

    # ── 1. User ──────────────────────────────────────────────────────────────
    user = get_latest_user()
    if not user:
        return False
    profile = build_profile(user)

    ai = AIService(settings.openai_api_key)

    # ── 2. Topics ────────────────────────────────────────────────────────────
    print("\n=== STEP 1: Generating personalised search topics ===")
    topics = generate_topics(profile, ai)

    # ── 3. Tavily ────────────────────────────────────────────────────────────
    print("\n=== STEP 2: Fetching articles via Tavily ===")
    tavily_results = fetch_articles_with_tavily(
        topics=topics,
        tavily_api_key=settings.tavily_api_key,
        max_results_per_topic=3,
    )
    if not tavily_results:
        print("[ERROR] No results from Tavily.")
        return False
    print(f"Candidate pool: {len(tavily_results)} articles")

    # ── 4. GPT-4o write ──────────────────────────────────────────────────────
    print("\n=== STEP 3: Writing newspaper with GPT-4o ===")
    newspaper_data = ai.write_newspaper_from_tavily(
        user_name=profile["name"],
        user_text_input=profile["interests"],
        family_info_input=profile["bio"],
        writing_style_input=build_writing_style(profile),
        tavily_results=tavily_results,
    )
    if not newspaper_data:
        print("[ERROR] GPT-4o failed to write the newspaper.")
        return False

    selected_articles = newspaper_data.get("articles", [])
    print(f"Articles written: {len(selected_articles)}")

    # ── 5. Save to DB ────────────────────────────────────────────────────────
    print("\n=== STEP 4: Saving to PostgreSQL ===")
    save_articles_to_db(user.id, newspaper_data)

    # ── 6. Push to Railway ───────────────────────────────────────────────────
    print("\n=== STEP 5: Pushing to Railway website ===")
    push_to_railway(newspaper_data, selected_articles)

    # ── 7. Email (optional) ──────────────────────────────────────────────────
    print("\n=== STEP 6: Sending email ===")
    try:
        email_settings = get_settings(require_email=True)
        html = build_email_html(newspaper_data, selected_articles)
        sent = send_email(
            to_email=user.email,
            sender_email=email_settings.sender_email,
            app_password=email_settings.sender_app_password,
            html_content=html,
        )
        print("Email sent ✓" if sent else "[WARNING] Email sending failed.")
    except Exception as exc:
        print(f"[WARNING] Email step skipped: {exc}")

    return True


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  Personal Newspaper — AI-Driven Pipeline")
    print("=" * 70)
    ok = run_pipeline()
    print("\n" + ("✓ Pipeline completed successfully." if ok else "✗ Pipeline failed — see errors above."))
