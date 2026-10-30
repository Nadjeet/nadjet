"""Vision configuration (``NADJET_*`` environment variables, see ``.env.example``).

All AI inference goes to the vLLM server on the team's NVIDIA Brev instance. Locally it is
reached through ``brev port-forward`` (``make brev-forward``), so the default endpoint is
loopback. Any other host must be an explicitly allowed Brev host; there is no other provider.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class VisionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NADJET_", env_file=".env", extra="ignore")

    brev_instance: str = Field(default="nadjet-gpu", description="Brev instance running vLLM")
    vlm_base_url: HttpUrl = Field(
        default=HttpUrl("http://127.0.0.1:18000/v1"),
        description="vLLM OpenAI-compatible endpoint (port-forwarded from Brev)",
    )
    vlm_model: str = Field(default="Qwen/Qwen3-VL-8B-Instruct-FP8")
    vlm_allowed_hosts: list[str] = Field(
        default_factory=list,
        description="Extra hostnames of Brev instances allowed besides loopback",
    )
    vlm_timeout_s: float = Field(default=15.0, gt=0, description="PRD FR-VIS-009 timeout")
    rtsp_base: str = Field(
        default="rtsp://127.0.0.1:8554",
        description="RTSP base URL; cameras are read from <base>/<camera-id>",
    )
    api_url: HttpUrl = Field(
        default=HttpUrl("http://127.0.0.1:8080"), description="Coordination API base URL"
    )
    ingest_token: SecretStr | None = Field(
        default=None, description="Service token for /internal/* (never logged)"
    )
    cameras_file: Path = Field(default=Path("data/cameras.yaml"), description="Camera catalogue")
    models_lock: Path = Field(
        default=Path("models.lock.yaml"), description="Pinned weights (TD-25)"
    )
    weights_dir: Path = Field(default=Path("weights"), description="Downloaded, verified weights")
    detector_model: str = Field(
        default="rf-detr-medium", description="Entry id in models.lock.yaml"
    )
    detector_threshold: float = Field(default=0.4, gt=0, lt=1, description="Min confidence")
    sample_fps: float = Field(default=5.0, gt=0, le=30, description="Analysed frames per second")
    evidence_buffer_s: float = Field(
        default=15.0, gt=0, description="Encoded packet ring (FR-VIS-006)"
    )
    annotate: bool = Field(default=True, description="Publish <camera>_ai annotated stream")
    annotated_encoder: str = Field(default="h264_nvenc", description="ffmpeg video encoder (TD-07)")
    metrics_port: int | None = Field(default=None, description="Serve /metrics on this port")
    metrics_port_base: int = Field(default=9100, description="--all: camera i serves base + i")
    health_push_s: float = Field(default=5.0, gt=0, description="Health report interval")
    stall_s: float = Field(default=10.0, gt=0, description="No frame for this long = camera fault")


@lru_cache
def get_settings() -> VisionSettings:
    return VisionSettings()
