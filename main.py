"""קובץ אורקסטרציה ראשי ליצירת עיתון אישי ושליחת מייל."""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests as http_requests
from dotenv import load_dotenv

load_dotenv()

from config import get_settings
from services.ai_service import AIService
from services.email_service import build_email_html, send_email
from services.news_service import deduplicate_articles, fetch_articles_for_keyword

RAILWAY_URL = "https://web-production-85103.up.railway.app"

_api_key = os.getenv("API_KEY", "")
print(f"[main.py] API_KEY starts with: '{_api_key[:3]}' (len={len(_api_key)})")

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

    payload = {"newspaper_data": newspaper_data, "selected_articles": selected_articles}
    try:
        response = http_requests.post(
            f"{RAILWAY_URL}/update-news",
            json=payload,
            headers={"x-api-key": api_key},
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
FAMILY_INFO = """
ספרי לי על עצמך: אני בת 77, השכלתי היא מדעי החיים, חינוך ומחשבים, פרשתי בגיל 70 אבל עדיין עובדת בפיתוח תוכניות לימודים במדעים לילדים. אני אוהבת תרבות, קריאת ספרים, טבע, מוזיקה (בעיקר קלסית), אוהבת ג'נרים שונים של קולנוע. אמא לבן ובת וסבתא לחמישה נכדים.
"""
WRITING_STYLE = "הייתי רוצה שכל כתבה שאקבל תהייה קצרה אבל תהייה לה האפשרות להתארך אם תעניין אותי. הרבה חומרים חזותיים. עדיפה עלי השפה האנגלית עם מילון."
USER_EMAIL = "yoavoron1@gmail.com"


def create_newspaper_data() -> Optional[Tuple[Dict, List[Dict]]]:
    """מייצר את נתוני העיתון בלבד (ללא שליחת מייל)."""
    settings = get_settings()
    ai_service = AIService(settings.openai_api_key)

    print("=== STEP 1: Extracting keywords ===")
    keywords = ai_service.extract_keywords(USER_TEXT)
    if not keywords:
        print("\n[ERROR] No keywords extracted.")
        return None

    print("\n=== STEP 2: Fetching articles ===")
    all_articles: List[Dict] = []
    for keyword in keywords:
        keyword_articles = fetch_articles_for_keyword(
            keyword=keyword,
            news_key=settings.news_api_key,
            days_back=7,
            max_articles=3,
        )
        print(f"Keyword: {keyword} -> {len(keyword_articles)} articles")
        all_articles.extend(keyword_articles)

    unique_articles = deduplicate_articles(all_articles)
    if not unique_articles:
        print("\n[ERROR] No articles found.")
        return None

    print("\n=== STEP 3: Filtering trash articles ===")
    filtered_articles = ai_service.filter_trash_articles(unique_articles)
    if not filtered_articles:
        print("\n[ERROR] No non-trash articles found.")
        return None

    print("\n=== STEP 4: Ranking and writing newspaper ===")
    selected_articles = ai_service.select_best_articles(
        user_text_input=USER_TEXT,
        family_info_input=FAMILY_INFO,
        articles=filtered_articles,
        top_n=4,
    )

    newspaper_data = ai_service.write_newspaper(
        user_name=USER_NAME,
        user_text_input=USER_TEXT,
        family_info_input=FAMILY_INFO,
        writing_style_input=WRITING_STYLE,
        selected_articles=selected_articles,
    )
    if not newspaper_data:
        print("\n[ERROR] Failed to write newspaper.")
        return None

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
