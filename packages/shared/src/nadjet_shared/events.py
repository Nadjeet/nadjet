"""Event contracts exchanged between the vision workers and the API (PRD FR-VIS-006/007)."""

from enum import StrEnum
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Probability = Annotated[float, Field(ge=0.0, le=1.0)]


class TriggerType(StrEnum):
    """Rule triggers (PRD FR-VIS-004) plus the AI sweep (FR-VIS-015)."""

    COLLISION_CANDIDATE = "collision_candidate"
    HARD_STOP = "hard_stop"
    STALLED_VEHICLE = "stalled_vehicle"
    PEDESTRIAN_ON_ROAD = "pedestrian_on_road"
    AI_SWEEP = "ai_sweep"
    CITIZEN_REPORT = "citizen_report"
    OPERATOR_REPORT = "operator_report"


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
    priority_raise: int = Field(
        default=0, ge=0, le=1, description="Levels the verifier asks to raise priority (max 1)"
    )
    findings: list[str] = Field(
        default_factory=list, description="Cited findings; a raise without one is ignored"
    )


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clip_path: str
    keyframe_paths: list[str] = Field(default_factory=list)
    sha256: dict[str, str] = Field(default_factory=dict, description="file path -> SHA-256")


class GeoLocation(BaseModel):
    """Where the event happened (FR-INC-001)."""

    model_config = ConfigDict(extra="forbid")

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    road: str | None = None
    pk_km: float | None = None
    wilaya: str | None = None


class Witness(BaseModel):
    """Answers from a citizen or responder on scene (FR-CIT-006)."""

    model_config = ConfigDict(extra="forbid")

    people_reported: int | None = Field(default=None, ge=0)
    trapped: bool = False


class IncidentCandidate(BaseModel):
    """A candidate incident from a camera, a citizen or an operator (FR-VIS-006, FR-INC-001)."""

    model_config = ConfigDict(extra="forbid")

    source: CandidateSource = CandidateSource.CAMERA
    camera_id: str | None = Field(default=None, min_length=1)
    location: GeoLocation
    witness: Witness | None = None
    trigger: TriggerType
    event_time: AwareDatetime = Field(description="Best estimate of the impact time")
    detected_at: AwareDatetime
    track_ids: list[int] = Field(default_factory=list)
    signals: dict[str, float] = Field(
        default_factory=dict, description="Named rule signals and their measured values"
    )
    verifier: VerifierResult = Field(default_factory=lambda: VerifierResult(available=False))
    ai_status: AiStatus = AiStatus.INSUFFICIENT_EVIDENCE
    evidence: Evidence | None = None

    @model_validator(mode="after")
    def _camera_source_needs_camera_id(self) -> "IncidentCandidate":
        if self.source is CandidateSource.CAMERA and self.camera_id is None:
            raise ValueError("camera_id is required when source is camera")
        return self
