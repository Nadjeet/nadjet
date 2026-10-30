"""Event contracts exchanged between the vision workers and the API (PRD FR-VIS-006/007)."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Probability = Annotated[float, Field(ge=0.0, le=1.0)]


class TriggerType(StrEnum):
    """Rule triggers (PRD FR-VIS-004) plus the AI sweep (FR-VIS-015)."""

    COLLISION_CANDIDATE = "collision_candidate"
    HARD_STOP = "hard_stop"
    STALLED_VEHICLE = "stalled_vehicle"
    PEDESTRIAN_ON_ROAD = "pedestrian_on_road"
    AI_SWEEP = "ai_sweep"


class CandidateSource(StrEnum):
    CAMERA = "camera"
    CITIZEN = "citizen"
    OPERATOR = "operator"


class AiStatus(StrEnum):
    """Graded AI status (PRD FR-VIS-007). The AI alone never yields ``confirmed``."""

    CONFIRMED = "confirmed"
    PROBABLE = "probable"
    POSSIBLE = "possible"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class VerifierResult(BaseModel):
    """Outcome of one call to the AI verifier (or of a failed call)."""

    model_config = ConfigDict(extra="forbid")

    available: bool = Field(description="False when the verifier timed out or was unreachable")
    model: str | None = Field(default=None, description="Model id that produced the answer")
    collision_visible: str | None = Field(
        default=None, pattern="^(yes|no|cannot_judge)$", description="Verifier verdict"
    )
    yes_probability: Probability | None = Field(
        default=None, description="Probability of the 'yes' answer token (logprobs)"
    )
    description_fr: str | None = None
    description_ar: str | None = None


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clip_path: str
    keyframe_paths: list[str] = Field(default_factory=list)
    sha256: dict[str, str] = Field(default_factory=dict, description="file path -> SHA-256")


class IncidentCandidate(BaseModel):
    """Published by a vision worker for every trigger or sweep detection (FR-VIS-006)."""

    model_config = ConfigDict(extra="forbid")

    camera_id: str = Field(min_length=1)
    trigger: TriggerType
    event_time: datetime = Field(description="Best estimate of the impact time")
    detected_at: datetime
    track_ids: list[int] = Field(default_factory=list)
    signals: dict[str, float] = Field(
        default_factory=dict, description="Named rule signals and their measured values"
    )
    verifier: VerifierResult
    ai_status: AiStatus
    evidence: Evidence | None = None
