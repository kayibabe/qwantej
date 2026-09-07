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
    # Defaults to the containerised dev database (docker-compose.yml), which
    # publishes on host port 5433 to avoid colliding with a native Postgres.
    database_url: str = (
        "postgresql+psycopg://qwantej:password@localhost:5433/qwantej"
    )
    secret_key: str = "change-me"

    api_football_key: str = ""
    api_football_base_url: str = "https://v3.football.api-sports.io"
    api_football_timeout_seconds: float = 30.0
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


@lru_cache
def get_settings() -> Settings:
    """Settings are cached — the process reads its environment once."""
    return Settings()
