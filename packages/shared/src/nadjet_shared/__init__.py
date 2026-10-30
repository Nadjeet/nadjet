"""Shared contracts for Nadjet services.

The Pydantic models here are the single source of truth for events exchanged between
services. Their JSON Schemas are exported to ``contracts/events/`` (``make gen``) so that
non-Python consumers can use them; CI fails if the exported files drift.
"""

from nadjet_shared.events import (
    AiStatus,
    CandidateSource,
    Evidence,
    GeoLocation,
    IncidentCandidate,
    TriggerType,
    VerifierResult,
    Witness,
)

__all__ = [
    "AiStatus",
    "CandidateSource",
    "Evidence",
    "GeoLocation",
    "IncidentCandidate",
    "TriggerType",
    "VerifierResult",
    "Witness",
]
