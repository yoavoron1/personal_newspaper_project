"""ניהול קונפיגורציה וטעינת משתני סביבה במקום מרכזי אחד."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _get_required_env(var_name: str) -> str:
    """מחזיר משתנה סביבה חובה או זורק שגיאה ברורה."""
    value = os.getenv(var_name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {var_name}")
    # ניקוי רווחים/מרכאות כדי למנוע כשלי אימות מיותרים.
    cleaned = value.strip().strip('"').strip("'")
    if not cleaned:
        raise RuntimeError(f"Environment variable is empty after cleanup: {var_name}")
    return cleaned


@dataclass(frozen=True)
class Settings:
    """אובייקט הגדרות מרכזי לאפליקציה."""

    openai_api_key: str
    news_api_key: str
    sender_email: str
    sender_app_password: str


def get_settings() -> Settings:
    """טוען ומחזיר את כל ההגדרות מהסביבה."""
    sender_email = _get_required_env("SENDER_EMAIL").lower()
    sender_app_password = _get_required_env("SENDER_APP_PASSWORD").replace(" ", "")
    return Settings(
        openai_api_key=_get_required_env("OPENAI_API_KEY"),
        news_api_key=_get_required_env("NEWS_API_KEY"),
        sender_email=sender_email,
        sender_app_password=sender_app_password,
    )
