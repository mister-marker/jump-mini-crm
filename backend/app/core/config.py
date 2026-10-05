"""Environment-only configuration; paths do not depend on the working directory."""

from functools import lru_cache
from pathlib import Path
from uuid import UUID

from pydantic import Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    supabase_url: HttpUrl
    supabase_service_role_key: SecretStr
    telegram_bot_token: SecretStr
    jwt_secret: SecretStr
    jwt_issuer: str = "jump-crm"
    jwt_audience: str = "jump-crm-api"
    jwt_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    telegram_auth_max_age_seconds: int = Field(default=300, ge=30, le=86400)
    telegram_clock_skew_seconds: int = Field(default=30, ge=0, le=60)
    pin_login_enabled: bool = False
    browser_pin: SecretStr
    demo_manager_id: UUID = UUID("00000000-0000-4000-8000-000000000026")
    webhook_secret: SecretStr
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @field_validator("jwt_secret")
    @classmethod
    def strong_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode()) < 32:
            raise ValueError("Secret must contain at least 32 bytes")
        if "replace" in value.get_secret_value().lower():
            raise ValueError("Replace example secrets before starting the application")
        return value

    @field_validator(
        "supabase_service_role_key", "telegram_bot_token", "browser_pin", "webhook_secret"
    )
    @classmethod
    def nonempty_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("Secret must not be empty")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
