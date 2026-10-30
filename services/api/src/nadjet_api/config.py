"""API configuration, read from ``NADJET_*`` environment variables (see ``.env.example``)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, field_validator, model_validator
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
    rtsp_url_template: str = Field(
        default="rtsp://localhost:8554/{path}", description="Camera RTSP URL; {path} = stream path"
    )
    whep_url_template: str = Field(
        default="http://localhost:8889/{path}/whep",
        description="Camera WebRTC WHEP URL for the browser; {path} = stream path",
    )

    hls_url_template: str = Field(
        default="http://localhost:8888/{path}/index.m3u8",
        description="Camera LL-HLS URL (WebRTC fallback); {path} = stream path",
    )

    @field_validator("rtsp_url_template", "whep_url_template", "hls_url_template")
    @classmethod
    def _url_template_has_only_path(cls, value: str) -> str:
        """Fail at startup, not with a 500 on every GET /cameras."""
        try:
            rendered = value.format(path="probe")
        except (KeyError, IndexError, ValueError) as exc:
            raise ValueError(f"URL template may only use {{path}}: {exc!r}") from exc
        if "probe" not in rendered:
            raise ValueError("URL template must contain {path}")
        return value

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
    evaluation_dir: Path = Field(
        # Anchored on the repository, not the API's working directory (`services/api` in tests).
        default=Path(__file__).resolve().parents[4] / "eval" / "results",
        description="Evaluation results written by `make eval`",
    )
    try_dir: Path = Field(
        default=Path("try-sandbox"), description="Isolated store of public uploads (FR-CIT-004)"
    )
    try_max_mb: int = Field(default=100, gt=0, description="Max upload size (FR-CIT-002)")
    try_max_seconds: int = Field(default=60, gt=0, description="Max clip length (FR-CIT-002)")
    try_ttl_s: int = Field(default=3600, gt=0, description="Uploads and results live this long")
    try_jobs_per_minute: int = Field(default=5, gt=0, description="Uploads per IP per minute")
    try_sessions_per_minute: int = Field(default=5, gt=0, description="Live sessions per IP")
    try_session_idle_s: int = Field(default=30, gt=0, description="No ping for this long: ended")
    try_job_timeout_s: int = Field(default=300, gt=0, description="Worker silent: job failed")
    try_purge_interval_s: float = Field(default=60.0, gt=0)
    try_max_open_jobs: int = Field(
        default=20, gt=0, description="Queued or running uploads at once (disk and GPU guard)"
    )
    try_max_live_sessions: int = Field(
        default=3, gt=0, description="Phone sessions at once (operator wall and GPU guard)"
    )
    try_events_max_s: float = Field(
        default=120.0, gt=0, description="Life of one progress stream; the browser reconnects"
    )
    try_events_per_minute: int = Field(default=30, gt=0, description="Progress streams per IP")
    whip_url_template: str = Field(
        default="http://localhost:8889/{path}/whip", description="WHIP URL; {path} = stream path"
    )
    live_demo_lat: float = Field(default=36.7538, description="Where a live demo camera sits")
    live_demo_lon: float = Field(default=3.0588)
    osrm_url: str = Field(default="http://localhost:55000", description="Self-hosted OSRM base URL")
    routing_timeout_s: float = Field(default=5.0, gt=0)
    routing_urban_multiplier: float = Field(
        default=1.3,
        ge=1.0,
        description="Factor applied to OSRM free-flow durations (no live traffic); see docs/11",
    )
    map_tiles_path: Path = Field(
        default=Path("data/map/algeria.pmtiles"), description="PMTiles file served at /tiles"
    )

    # --- Citizen reports (FR-CIT-004) ---
    public_report_rate_limit: int = Field(
        default=5, gt=0, description="Citizen reports allowed per client IP per window"
    )
    public_report_window_s: int = Field(default=600, gt=0)
    public_photo_max_mb: int = Field(default=10, gt=0)

    # --- Notifications (FR-NTF, TD-13/14) ---
    sms_gateway_url: str | None = Field(
        default=None, description="capcom6 SMS Gateway server base URL; SMS disabled when unset"
    )
    sms_gateway_user: str = Field(default="", description="Gateway API username (from the app)")
    sms_gateway_password: SecretStr | None = None
    sms_webhook_secret: SecretStr | None = Field(
        default=None,
        description="Signing key of the gateway webhooks; /sms/* return 503 when unset",
    )
    sms_webhook_tolerance_s: int = Field(default=300, gt=0)
    vapid_private_key: SecretStr | None = Field(
        default=None, description="Web Push VAPID private key; `nadjet-api gen-vapid`"
    )
    vapid_public_key: str | None = None
    vapid_subject: str = "mailto:ops@nadjet.example"
    telegram_bot_token: SecretStr | None = Field(
        default=None, description="Optional Telegram Bot API token"
    )
    notify_retry_base_s: int = Field(
        default=30, gt=0, description="Resend when not delivered after this long, doubling"
    )
    notify_max_retries: int = Field(default=3, ge=0)

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
