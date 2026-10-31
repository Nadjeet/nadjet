"""Shared contracts for Nadjet services.

The Pydantic models here are the single source of truth for events exchanged between
services. Their JSON Schemas are exported to ``contracts/events/`` (``make gen``) so that
non-Python consumers can use them; CI fails if the exported files drift.
"""

from nadjet_shared.events import (
    AiStatus,
    CandidateSource,
    Evidence,
    Finding,
    GeoLocation,
    IncidentCandidate,
    TriggerType,
    VerifierResult,
    Witness,
)
from nadjet_shared.health import CameraHealthReport, FaultReason, StageLatencyMs

__all__ = [
    "AiStatus",
    "CameraHealthReport",
    "CandidateSource",
    "Evidence",
    "FaultReason",
    "Finding",
    "GeoLocation",
    "IncidentCandidate",
    "StageLatencyMs",
    "TriggerType",
    "VerifierResult",
    "Witness",
]
