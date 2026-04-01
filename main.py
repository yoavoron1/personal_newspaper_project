"""קובץ אורקסטרציה ראשי ליצירת עיתון אישי ושליחת מייל."""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests as http_requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from config import get_settings
from services.ai_service import AIService
from services.email_service import build_email_html, send_email
from services.news_service import fetch_articles_with_tavily

RAILWAY_URL = "https://personalnewspaperproject-production.up.railway.app"

print(f"Sending request with API_KEY: {os.getenv('API_KEY', '')[:3]}...")

CACHE_FILE = Path(__file__).resolve().parent / "newspaper_cache.json"


def save_newspaper_cache(newspaper_data: Dict, selected_articles: List[Dict]) -> None:
    """שומר את נתוני העיתון לקובץ cache לשימוש האתר."""
    try:
        CACHE_FILE.write_text(
            json.dumps(
                {"newspaper_data": newspaper_data, "selected_articles": selected_articles},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nNewspaper data cached to {CACHE_FILE}")
    except Exception as exc:
        print(f"\n[WARNING] Could not save cache: {exc}")


def push_to_railway(newspaper_data: Dict, selected_articles: List[Dict]) -> None:
    """שולח את נתוני העיתון לשרת Railway כדי לעדכן את האתר."""
    api_key = os.getenv("API_KEY", "")
    if not api_key:
        print("\n[WARNING] API_KEY not set — skipping Railway push.")
        return

    print(f"Sending request with API_KEY: {api_key[:3]}...")
    payload = {"newspaper_data": newspaper_data, "selected_articles": selected_articles}
    try:
        response = http_requests.post(
            f"{RAILWAY_URL}/update-news?api_key={api_key}",
            json=payload,
            timeout=30,
        )
        if response.status_code == 200:
            print(f"\nRailway site updated successfully! ({RAILWAY_URL})")
        else:
            print(f"\n[WARNING] Railway push returned {response.status_code}: {response.text}")
    except Exception as exc:
        print(f"\n[WARNING] Could not push to Railway: {exc}")


USER_NAME = "רחל מינץ"
USER_TEXT = """
תחומי העניין שלי הם:
ספרים חדשים רבי מכר
חדשות אומנות מהעולם: תערוכות חדשות, אומנים חדשים
תגליות באסטרונומיה ומסעות בחלל
מקומות נופש אקסלוסיביים בעולם
התפתחות טכנולוגית בAi
טרנדים באופנה ובעיצוב
סרטים חדשים איכותיים
סדרות חדשות איכותיות
לונג'ביטי
"""
USER_PROFILE = {
    "age": 77,
    "background": "מדעי החיים, חינוך ומחשבים",
    "occupation": "פיתוח תוכניות לימודים במדעים לילדים",
    "interests": ["תרבות", "קריאת ספרים", "טבע", "מוזיקה קלאסית", "קולנוע"],
    "family": "אמא ל-2 וסבתא ל-5 נכדים"
}
FAMILY_INFO = """
ספרי לי על עצמך: אני בת 77, השכלתי היא מדעי החיים, חינוך ומחשבים, פרשתי בגיל 70 אבל עדיין עובדת בפיתוח תוכניות לימודים במדעים לילדים. אני אוהבת תרבות, קריאת ספרים, טבע, מוזיקה (בעיקר קלסית), אוהבת ג'נרים שונים של קולנוע. אמא לבן ובת וסבתא לחמישה נכדים.
"""
WRITING_STYLE = "הייתי רוצה שכל כתבה שאקבל תהייה קצרה אבל תהייה לה האפשרות להתארך אם תעניין אותי. הרבה חומרים חזותיים. עדיפה עלי השפה האנגלית עם מילון."
USER_EMAIL = "yoavoron1@gmail.com"

TAVILY_TOPICS = [
    "AI technology breakthroughs 2026",
    "astronomy space exploration discoveries 2026",
    "longevity anti-aging research 2026",
]


def create_newspaper_data() -> Optional[Tuple[Dict, List[Dict]]]:
    """מייצר את נתוני העיתון באמצעות Tavily + GPT-4o (ללא שליחת מייל)."""
    settings = get_settings()

    if not settings.tavily_api_key:
        print("\n[ERROR] TAVILY_API_KEY is not set.")
        return None
    if not settings.openai_api_key:
        print("\n[ERROR] OPENAI_API_KEY is not set.")
        return None

    ai_service = AIService(settings.openai_api_key)

    print("=== STEP 1: Fetching articles via Tavily Advanced Search ===")
    tavily_results = fetch_articles_with_tavily(
        topics=TAVILY_TOPICS,
        tavily_api_key=settings.tavily_api_key,
        max_results_per_topic=5,
    )

    if not tavily_results:
        print("\n[ERROR] No results from Tavily.")
        return None

    print(f"\nTotal Tavily results: {len(tavily_results)}")

    print("\n=== STEP 2: Writing newspaper with GPT-4o ===")
    newspaper_data = ai_service.write_newspaper_from_tavily(
        user_name=USER_NAME,
        user_text_input=USER_TEXT,
        family_info_input=FAMILY_INFO,
        writing_style_input=WRITING_STYLE,
        tavily_results=tavily_results,
    )

    if not newspaper_data:
        print("\n[ERROR] Failed to write newspaper.")
        return None

    selected_articles = newspaper_data.get("articles", [])
    return newspaper_data, selected_articles


def main() -> Optional[Dict]:
    """מריץ את הזרימה המלאה: יצירה ושליחת מייל."""
    try:
        settings = get_settings(require_email=True)
        result = create_newspaper_data()
    except Exception as exc:
        print(f"\n[ERROR] Failed during setup/generation: {exc}")
        return None

    if not result:
        return None

    newspaper_data, selected_articles = result
    save_newspaper_cache(newspaper_data, selected_articles)
    push_to_railway(newspaper_data, selected_articles)

    email_html_content = build_email_html(newspaper_data, selected_articles)

    sent = send_email(
        to_email=USER_EMAIL,
        sender_email=settings.sender_email,
        app_password=settings.sender_app_password,
        html_content=email_html_content,
    )
    if sent:
        print("\nEmail sent successfully!")
    else:
        print("\nEmail sending failed.")

    return newspaper_data


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("Personal Weekly Newspaper")
    print("=" * 70)
    main()
