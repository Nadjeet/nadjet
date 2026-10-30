"""API configuration, read from ``NADJET_*`` environment variables (see ``.env.example``)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_JWT_SECRET_LENGTH = 32
SIGNING_SEED_HEX_LENGTH = 64
DEV_SIGNING_SEED = "0" * 63 + "1"  # insecure fixed Ed25519 seed for development/test
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
    ingest_token: SecretStr | None = Field(
        default=None, description="Service token for /internal/*; endpoints return 503 when unset"
    )
    evidence_dir: Path = Field(default=Path("evidence"), description="Local evidence store root")
    evidence_max_mb: int = Field(default=100, gt=0)
    signing_key: SecretStr | None = Field(
        default=None,
        description="Ed25519 seed (64 hex chars) signing incident chain heads; "
        "generate with `nadjet-api gen-signing-key`; required in production",
    )
    candidate_claim_idle_ms: int = Field(
        default=30_000, ge=0, description="Re-claim stream entries pending longer than this"
    )

    @model_validator(mode="after")
    def _require_jwt_secret_in_production(self) -> "Settings":
        if self.env == "production":
            secret = self.jwt_secret.get_secret_value() if self.jwt_secret else ""
            if len(secret) < MIN_JWT_SECRET_LENGTH or secret == DEV_JWT_SECRET:
                raise ValueError(
                    f"NADJET_JWT_SECRET must be set to a unique value of at least "
                    f"{MIN_JWT_SECRET_LENGTH} characters in production"
                )
            seed = self.signing_key.get_secret_value() if self.signing_key else ""
            if len(seed) != SIGNING_SEED_HEX_LENGTH or seed == DEV_SIGNING_SEED:
                raise ValueError("NADJET_SIGNING_KEY must be a unique 64-hex-char Ed25519 seed")
        return self

    @property
    def signing_seed(self) -> str:
        """Ed25519 seed (hex); a fixed insecure seed outside production when none is set."""
        return self.signing_key.get_secret_value() if self.signing_key else DEV_SIGNING_SEED

    @property
    def jwt_key(self) -> str:
        """The JWT signing key; a fixed insecure key outside production when none is set."""
        return self.jwt_secret.get_secret_value() if self.jwt_secret else DEV_JWT_SECRET


@lru_cache
def get_settings() -> Settings:
    return Settings()
