"""Evaluation results file (PRD SC-004, SC-005, FR-KPI-003, doc 04 §5).

Written by ``eval/run_eval.py`` to ``eval/results/<date>-<git-sha>.json`` and served by
``GET /evaluation/latest``. Every number carries its bootstrap 95 % interval when it has one;
what was not run is listed with its reason, never filled with a target.
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

ClipKind = Literal["crash", "stalled", "negative"]
AlertSource = Literal["rule", "sweep"]


class Interval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low: float
    high: float


class Metric(BaseModel):
    """A value and its bootstrap 95 % interval; ``None`` when it is undefined (no events)."""

    model_config = ConfigDict(extra="forbid")

    value: float | None = None
    ci: Interval | None = None


class EventMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ground_truth: int = Field(ge=0, description="Annotated events scored")
    alerts: int = Field(ge=0, description="Alerts counted in this configuration")
    true_positives: int = Field(ge=0)
    false_positives: int = Field(ge=0)
    false_negatives: int = Field(ge=0)
    camera_hours: float = Field(ge=0, description="Negative footage the false alarms are over")
    precision: Metric
    recall: Metric
    f1: Metric
    median_delay_s: Metric = Field(description="Alert time minus annotated impact (crash clips)")
    mean_peak_error_s: Metric = Field(description="Detected impact time minus annotated impact")
    false_alarms_per_camera_hour: Metric


class AblationRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    metrics: EventMetrics | None = None
    not_run_reason: str | None = Field(default=None, description="Why there is no metrics")


class AiQuality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verifications: int = Field(ge=0, description="Verifier and sweep calls that were answered")
    valid_first_try: Metric
    dropped_citation_share: Metric = Field(description="Findings dropped for invalid frame ids")
    cannot_judge_share: Metric
    unavailable: int = Field(ge=0, description="Calls with no answer (timeout, server down)")


class Percentiles(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=0)
    p50: float | None = None
    p95: float | None = None


class AlertRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: AlertSource
    trigger: str
    t_fire: float = Field(description="Stream seconds when the alert was raised")
    t_peak: float = Field(description="Stream seconds of the estimated impact")
    ai_status: str
    collision_visible: str | None = None
    verifier_available: bool = False


class ClipSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: ClipKind
    duration_s: float = Field(ge=0)
    impact_s: float | None = None
    alerts: list[AlertRecord] = Field(default_factory=list)


class SkippedClip(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    reason: str


class EvaluationResults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    generated_at: AwareDatetime
    git_sha: str
    dirty: bool = Field(description="Uncommitted changes when the run started")
    seed: int
    bootstrap_samples: int = Field(gt=0)
    window_before_s: float
    window_after_s: float
    models: dict[str, str] = Field(description="Role -> model id used (source of every AI value)")
    clips: list[ClipSummary]
    skipped_clips: list[SkippedClip] = Field(default_factory=list)
    camera_hours: float = Field(ge=0)
    meets_camera_hour_target: bool = Field(description="At least one camera-hour of negatives")
    ablation: list[AblationRow]
    ai_quality: AiQuality | None = None
    latency_ms: dict[str, Percentiles] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
