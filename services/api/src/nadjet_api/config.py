"""API configuration, read from ``NADJET_*`` environment variables (see ``.env.example``)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_JWT_SECRET_LENGTH = 32
DEV_JWT_SECRET = "nadjet-insecure-development-secret-do-not-use"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NADJET_", env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    database_url: PostgresDsn = Field(
        default=PostgresDsn("postgresql+asyncpg://nadjet:nadjet@localhost:55432/nadjet"),
        description="SQLAlchemy async URL (asyncpg driver)",
    )
    redis_url: RedisDsn = Field(default=RedisDsn("redis://localhost:56379/0"))
    cors_origins: list[str] = Field(default=["http://localhost:5173"])
    readiness_timeout_s: float = Field(default=2.0, gt=0)
    jwt_secret: SecretStr | None = Field(
        default=None,
        description="HS256 signing key; required (>= 32 chars) outside development/test",
    )
    access_token_ttl_minutes: int = Field(default=30, gt=0)

    @model_validator(mode="after")
    def _require_jwt_secret_in_production(self) -> "Settings":
        if self.env == "production":
            secret = self.jwt_secret.get_secret_value() if self.jwt_secret else ""
            if len(secret) < MIN_JWT_SECRET_LENGTH or secret == DEV_JWT_SECRET:
                raise ValueError(
                    f"NADJET_JWT_SECRET must be set to a unique value of at least "
                    f"{MIN_JWT_SECRET_LENGTH} characters in production"
                )
        return self

    @property
    def signing_key(self) -> str:
        """The JWT signing key; a fixed insecure key outside production when none is set."""
        return self.jwt_secret.get_secret_value() if self.jwt_secret else DEV_JWT_SECRET


@lru_cache
def get_settings() -> Settings:
    return Settings()
