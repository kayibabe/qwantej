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

    # Security — empty string disables API key auth (dev only).
    api_key: str = ""

    # Comma-separated list of allowed CORS origins (e.g. the qwantej-frontend
    # Railway service's URL) — required in production, where the default is
    # "allow nothing".
    cors_origins: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        """True only for the explicit ``development`` value.

        Every relaxed-security default (open CORS, no API key required, docs
        exposed) is gated on this rather than on ``environment != "production"``,
        so an unset/typo'd/unexpected ENVIRONMENT value (e.g. "staging", "",
        "prod") fails closed instead of silently inheriting dev-mode laxity.
        """
        return self.environment == "development"

    # Logging
    log_level: str = "INFO"
    log_format: str = "plain"  # "json" in production

    # Data sources
    api_football_key: str = ""
    api_football_base_url: str = "https://v3.football.api-sports.io"
    api_football_timeout_seconds: float = 30.0
    # Opt-in broad research collection. The signal pipeline still requires
    # Competition.validated before it can create a public prediction.
    ingest_all_leagues: bool = False
    # When enabled, the scheduler runs the approved-league paper-ticket path.
    # It remains paper-only; live stakes and ticket locking are not implemented.
    paper_ticket_pipeline_enabled: bool = False

    # Notifications
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_timeout_seconds: float = 10.0

    # Backups
    backup_dir: str = "backups"
    backup_keep_count: int = 7


@lru_cache
def get_settings() -> Settings:
    """Settings are cached — the process reads its environment once."""
    return Settings()
