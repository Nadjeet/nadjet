"""Contracts of the public "try it yourself" sandbox (PRD FR-CIT-002..005, doc 10 §5).

Uploaded clips and phone cameras are analysed on the same Brev pipeline as the real cameras, but
their results live only in these models: a sandbox incident is a field of a job result, never a
row of the incident queue, so it cannot reach the operator queue, the KPIs or an evaluation.
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from nadjet_shared.events import AiStatus, VerifierResult

JobStatus = Literal["queued", "processing", "done", "failed", "rejected"]
SessionStatus = Literal["active", "ended"]


class Box(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x1: float
    y1: float
    x2: float
    y2: float
    label: str
    track_id: int | None = None


class TimelineEntry(BaseModel):
    """One event of the analysed clip, in clip seconds, with the source of the value."""

    model_config = ConfigDict(extra="forbid")

    t: float = Field(ge=0)
    kind: Literal["trigger", "ai_scan", "ai_refine"]
    label: str
    source: str = Field(description="Rule name or model id (FR-VIS-021)")
    detail: str | None = None


class SandboxIncident(BaseModel):
    """What an operator would have been shown, kept inside the sandbox."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["collision", "possible_incident"]
    ai_status: AiStatus
    event_time_s: float = Field(ge=0)
    trigger: str | None = Field(default=None, description="Rule trigger near the moment, if any")
    vehicles: list[Box] = Field(default_factory=list, description="Detector boxes at the moment")
    description_fr: str | None = None
    description_ar: str | None = None


class TryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_s: float = Field(ge=0)
    frames_analysed: int = Field(ge=0)
    ai_available: bool = Field(description="False: only the rule-based analysis is shown")
    scan: VerifierResult | None = Field(default=None, description="Pass 1: whole clip, 1-2 fps")
    refine: VerifierResult | None = Field(default=None, description="Pass 2: around the moment")
    scan_t_s: float | None = None
    event_t_s: float | None = Field(default=None, description="Refined, damped and capped")
    timeline: list[TimelineEntry] = Field(default_factory=list)
    sandbox_incident: SandboxIncident | None = None
    models: dict[str, str] = Field(default_factory=dict)


class TryProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str = Field(max_length=32)
    progress: float = Field(ge=0, le=1)


class TryJobFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: str = Field(max_length=300)
    rejected: bool = Field(default=False, description="Not a usable video: nothing was analysed")


class TryJobOut(BaseModel):
    id: str
    status: JobStatus
    stage: str
    progress: float
    error: str | None
    result: TryResult | None
    has_video: bool
    expires_at: AwareDatetime


class TryJobClaim(BaseModel):
    id: str
    filename: str


class SessionEvent(BaseModel):
    """One AI check or trigger of a live phone session (sandbox, shown on the try page)."""

    model_config = ConfigDict(extra="forbid")

    at: AwareDatetime
    kind: Literal["ai_check", "trigger"]
    label: str
    source: str
    ai_status: AiStatus | None = None
    verifier: VerifierResult | None = None


class TrySessionOut(BaseModel):
    id: str
    status: SessionStatus
    path: str = Field(description="Video server path the phone publishes to")
    whip_url: str
    whep_url: str
    publish_token: str | None = Field(
        default=None,
        description="Bearer token for the WHIP publish, limited to this path (only on creation)",
    )
    expires_at: AwareDatetime
    events: list[SessionEvent]


class TrySessionRef(BaseModel):
    id: str
    path: str


class TryAiReport(BaseModel):
    """What the try-it worker tells the API about the Brev AI (the page says "AI unavailable")."""

    model_config = ConfigDict(extra="forbid")

    ai_available: bool


class TryStatus(BaseModel):
    ai_available: bool = Field(description="Brev verifier reachable (reported by the worker)")
    max_seconds: int
    max_mb: int
    ttl_s: int
