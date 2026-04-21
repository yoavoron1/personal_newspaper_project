"""SQLAlchemy models for the personal newspaper platform."""

import os
import sys
from datetime import datetime

from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, String, Text, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

# ── Database URL (PostgreSQL only — no SQLite fallback) ───────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    print(
        "\n[FATAL] DATABASE_URL is not set.\n"
        "Add it to your .env file using the Railway external proxy URL:\n"
        "  DATABASE_URL=postgresql+psycopg://postgres:<password>@<host>.railway.app:<port>/railway\n"
        "Find it in: Railway dashboard → your Postgres service → Connect → Public URL\n",
        file=sys.stderr,
    )
    sys.exit(1)

# Normalise legacy postgres:// shorthand (older Railway / Heroku configs)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)

if not DATABASE_URL.startswith("postgresql"):
    print(
        f"\n[FATAL] DATABASE_URL must be a PostgreSQL URL.\n"
        f"Got: {DATABASE_URL[:40]}...\n",
        file=sys.stderr,
    )
    sys.exit(1)

# ── Engine ─────────────────────────────────────────────────────────────────────
engine = create_engine(
    DATABASE_URL,
    connect_args={
        "connect_timeout": 10,   # fail fast instead of hanging
        "sslmode": "require",    # required for Railway external connections
    },
    pool_pre_ping=True,          # discard stale connections automatically
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Base ───────────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Models ─────────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    email         = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name     = Column(String(255), nullable=False)
    # Questionnaire — three rich free-text fields used to personalise the newspaper
    occupation    = Column(Text, nullable=True)   # professional background + context
    interests_text = Column(Text, nullable=True)  # detailed topic interests
    bio           = Column(Text, nullable=True)   # reading style, life context, preferences
    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)

    articles = relationship("Article", back_populates="user", cascade="all, delete-orphan")


class Article(Base):
    __tablename__ = "articles"

    id        = Column(Integer, primary_key=True, index=True)
    user_id   = Column(Integer, ForeignKey("users.id"), nullable=False)
    title     = Column(String(500), nullable=False)
    content   = Column(Text, nullable=True)
    image_url = Column(String(1000), nullable=True)
    source    = Column(String(255), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="articles")


def create_tables() -> None:
    """Create all tables if they don't already exist."""
    Base.metadata.create_all(bind=engine)
