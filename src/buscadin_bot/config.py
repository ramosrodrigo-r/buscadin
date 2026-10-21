"""Validated application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the collector and Telegram worker."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    telegram_bot_token: SecretStr | None = None
    telegram_admin_chat_id: int | None = None
    telegram_admin_user_id: int | None = None
    database_url: str = "sqlite+aiosqlite:///./data/buscadin.db"
    collect_interval_hours: float = 12.0
    max_notifications_per_run: int = 20
    log_level: str = "INFO"
    http_timeout_seconds: float = 20.0
    http_max_retries: int = 3
    himalayas_api_url: str = "https://himalayas.app/jobs/api"
    himalayas_api_key: SecretStr | None = None

    def require_telegram(self) -> tuple[str, int, int | None]:
        """Return Telegram credentials or fail with a useful configuration error."""

        missing: list[str] = []
        if self.telegram_bot_token is None or not self.telegram_bot_token.get_secret_value():
            missing.append("TELEGRAM_BOT_TOKEN")
        if self.telegram_admin_chat_id is None:
            missing.append("TELEGRAM_ADMIN_CHAT_ID")
        if missing:
            raise ValueError(f"Telegram configuration is incomplete: {', '.join(missing)}")
        return (
            self.telegram_bot_token.get_secret_value(),
            self.telegram_admin_chat_id,
            self.telegram_admin_user_id,
        )

    def ensure_sqlite_directory(self) -> None:
        """Create the local data directory when using a file-backed SQLite URL."""

        prefix = "sqlite+aiosqlite:///"
        if not self.database_url.startswith(prefix):
            return
        database_path = self.database_url.removeprefix(prefix)
        if database_path in {":memory:", ""} or database_path.startswith("file:"):
            return
        Path(database_path).expanduser().parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once per process; tests can instantiate ``Settings`` directly."""

    return Settings()
