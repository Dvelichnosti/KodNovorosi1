from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "BizBoard API"
    app_version: str = "1.0.0"
    env: str = "dev"
    debug: bool = True
    secret_key: str = "dev-secret-change-me"
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://bizboard:bizboard@localhost:5432/bizboard"
    database_echo: bool = False
    redis_url: str = "redis://localhost:6379/0"

    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    mfa_token_ttl_minutes: int = 10
    login_session_ttl_minutes: int = 10
    invitation_ttl_hours: int = 72

    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_webhook_secret: str = ""

    cors_origins: str = "*"
    media_root: str = "media"
    media_url: str = "/media"
    max_upload_mb: int = 20

    default_listing_ttl_days: int = 30
    private_active_listing_limit: int = 3
    promotions_self_service: bool = False

    totp_issuer: str = "BizBoard"

    superadmin_telegram_id: int | None = None
    superadmin_phone: str | None = None

    login_start_rate_limit: int = 10
    login_start_rate_window: int = 60
    login_poll_rate_limit: int = 60
    login_poll_rate_window: int = 60
    complaint_rate_limit: int = 5
    complaint_rate_window: int = 3600
    upload_rate_limit: int = 30
    upload_rate_window: int = 3600

    auto_create_tables: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        raw = (self.cors_origins or "").strip()
        if not raw or raw == "*":
            return ["*"]
        return [item.strip() for item in raw.split(",") if item.strip()]

    @property
    def media_path(self) -> Path:
        return Path(self.media_root).resolve()

    @property
    def is_production(self) -> bool:
        return self.env.lower() in {"prod", "production"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
