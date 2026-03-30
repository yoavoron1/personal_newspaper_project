"""ניהול קונפיגורציה וטעינת משתני סביבה בצורה עמידה ל-production."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    """אובייקט הגדרות מרכזי לאפליקציה ללא שדות חובה קשיחים."""

    openai_api_key: str
    news_api_key: str
    sender_email: str
    sender_app_password: str

    class Config:
        env_file = ".env"
        extra = "ignore"


def get_settings(require_email: bool = False) -> Settings:
    """טוען הגדרות מהסביבה/מערכת עם ברירת מחדל ריקה לכל משתנה."""
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip().strip('"').strip("'"),
        news_api_key=os.getenv("NEWS_API_KEY", "").strip().strip('"').strip("'"),
        sender_email=os.getenv("SENDER_EMAIL", "").strip().strip('"').strip("'").lower(),
        sender_app_password=os.getenv("SENDER_APP_PASSWORD", "").strip().strip('"').strip("'").replace(" ", ""),
    )
