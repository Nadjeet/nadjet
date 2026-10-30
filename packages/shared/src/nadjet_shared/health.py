"""Camera health report pushed by each vision worker every 5 s (PRD FR-CAM-005, doc 11 §9)."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

FaultReason = Literal["stall", "disconnect"]


class StageLatencyMs(BaseModel):
    """Median per-stage latency over the last window; ``None`` before the first frame."""

    model_config = ConfigDict(extra="forbid")

    decode: float | None = Field(default=None, ge=0)
    detect: float | None = Field(default=None, ge=0)
    track: float | None = Field(default=None, ge=0)
    annotate: float | None = Field(default=None, ge=0)


class CameraHealthReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera_id: str = Field(min_length=1, max_length=63)
    at: AwareDatetime
    connected: bool
    fps: float = Field(ge=0, description="Analysed frames per second")
    queue_depth: int = Field(ge=0)
    last_frame_at: AwareDatetime | None = None
    latency_ms: StageLatencyMs = Field(default_factory=StageLatencyMs)
    camera_moving: bool = Field(default=False, description="Global camera motion (FR-VIS-011)")
    fault: bool = False
    fault_reason: FaultReason | None = None
    detector: str | None = Field(
        default=None, description="Detector model id (source of AI values)"
    )

    @model_validator(mode="after")
    def _fault_has_reason(self) -> "CameraHealthReport":
        if self.fault != (self.fault_reason is not None):
            raise ValueError("fault_reason is set if and only if fault is true")
        return self
