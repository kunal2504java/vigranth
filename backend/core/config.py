"""
Application configuration loaded from environment variables.
Uses pydantic-settings for validation and type coercion.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    # -- App --
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    FRONTEND_URL: str = "http://localhost:3000"
    WEBHOOK_BASE_URL: str = "http://localhost:8000"

    # -- Database --
    DATABASE_URL: str = "postgresql+asyncpg://app:secret@localhost:5432/unifyinbox"
    DATABASE_URL_SYNC: str = "postgresql://app:secret@localhost:5432/unifyinbox"

    # -- Redis --
    REDIS_URL: str = "redis://localhost:6379/0"

    # -- ChromaDB --
    CHROMA_URL: str = "http://localhost:8001"

    # -- Anthropic AI --
    ANTHROPIC_API_KEY: str = ""

    # -- JWT Auth --
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_HOURS: int = 24

    # -- Encryption (AES-256 for OAuth tokens at rest) --
    ENCRYPTION_KEY: str = "0" * 64  # 32-byte hex; override in .env

    # -- Gmail OAuth2 --
    GMAIL_CLIENT_ID: str = ""
    GMAIL_CLIENT_SECRET: str = ""
    GMAIL_REDIRECT_URI: str = "http://localhost:8000/auth/gmail/callback"

    # -- Slack OAuth2 --
    SLACK_CLIENT_ID: str = ""
    SLACK_CLIENT_SECRET: str = ""
    SLACK_REDIRECT_URI: str = "http://localhost:8000/auth/slack/callback"

    # -- Telegram --
    TELEGRAM_BOT_TOKEN: str = ""

    # -- Discord --
    DISCORD_BOT_TOKEN: str = ""
    DISCORD_CLIENT_ID: str = ""
    DISCORD_CLIENT_SECRET: str = ""
    DISCORD_REDIRECT_URI: str = "http://localhost:8000/auth/discord/callback"

    # -- Rate Limits --
    RATE_LIMIT_STANDARD: int = 100  # req/min
    RATE_LIMIT_AI_ACTIONS: int = 10  # req/min

    # -- Sync --
    PLATFORM_SYNC_INTERVAL_SECONDS: int = 120
    SNOOZE_CHECK_INTERVAL_SECONDS: int = 60
    SCORE_DECAY_INTERVAL_SECONDS: int = 3600

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
