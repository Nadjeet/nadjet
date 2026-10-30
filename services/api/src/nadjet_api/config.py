"""API configuration, read from ``NADJET_*`` environment variables (see ``.env.example``)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NADJET_", env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    database_url: PostgresDsn = Field(
        default=PostgresDsn("postgresql+asyncpg://nadjet:nadjet@localhost:5432/nadjet"),
        description="SQLAlchemy async URL (asyncpg driver)",
    )
    redis_url: RedisDsn = Field(default=RedisDsn("redis://localhost:6379/0"))
    cors_origins: list[str] = Field(default=["http://localhost:5173"])
    readiness_timeout_s: float = Field(default=2.0, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
