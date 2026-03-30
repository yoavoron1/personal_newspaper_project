"""ניהול קונפיגורציה וטעינת משתני סביבה במקום מרכזי אחד."""

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


# ב-production (למשל Railway) ייטענו ערכים מהמערכת עצמה;
# מקומית ננסה לטעון מקובץ .env אם קיים, בלי לדרוש אותו.
load_dotenv(dotenv_path=".env", override=False)


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


def _get_optional_env(var_name: str) -> Optional[str]:
    """מחזיר משתנה סביבה אופציונלי לאחר ניקוי בסיסי."""
    value = os.getenv(var_name)
    if value is None:
        return None
    cleaned = value.strip().strip('"').strip("'")
    return cleaned or None


@dataclass(frozen=True)
class Settings:
    """אובייקט הגדרות מרכזי לאפליקציה."""

    openai_api_key: str
    news_api_key: str
    sender_email: Optional[str]
    sender_app_password: Optional[str]


def get_settings(require_email: bool = False) -> Settings:
    """טוען הגדרות מהסביבה, עם אפשרות לחייב הגדרות מייל רק בעת הצורך."""
    sender_email = _get_optional_env("SENDER_EMAIL")
    sender_app_password = _get_optional_env("SENDER_APP_PASSWORD")

    if sender_email:
        sender_email = sender_email.lower()
    if sender_app_password:
        sender_app_password = sender_app_password.replace(" ", "")

    if require_email and (not sender_email or not sender_app_password):
        missing = []
        if not sender_email:
            missing.append("SENDER_EMAIL")
        if not sender_app_password:
            missing.append("SENDER_APP_PASSWORD")
        raise RuntimeError("Missing required environment variable(s): " + ", ".join(missing))

    return Settings(
        openai_api_key=_get_required_env("OPENAI_API_KEY"),
        news_api_key=_get_required_env("NEWS_API_KEY"),
        sender_email=sender_email,
        sender_app_password=sender_app_password,
    )
