"""Application settings, loaded from environment variables / .env.

See .env.example for the full list of recognised variables and
DEVELOPMENT.md for the rule that every new required variable must be added
there too.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = (
        "postgresql+psycopg://qwantej:password@localhost:5432/qwantej"
    )
    secret_key: str = "change-me"

    api_football_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


@lru_cache
def get_settings() -> Settings:
    """Settings are cached — the process reads its environment once."""
    return Settings()
