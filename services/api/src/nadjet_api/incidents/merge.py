"""Duplicate-candidate merge rules (FR-INC-002, E-06, E-14). Pure."""

from datetime import datetime

from nadjet_shared.events import AiStatus, VerifierResult

MERGE_WINDOW_S = 60.0
MERGE_RADIUS_M = 50.0

_AI_RANK = {
    AiStatus.INSUFFICIENT_EVIDENCE: 0,
    AiStatus.POSSIBLE: 1,
    AiStatus.PROBABLE: 2,
    AiStatus.CONFIRMED: 3,
}


def should_merge(last_event_time: datetime, event_time: datetime, distance_m: float) -> bool:
    """Merge when the candidate is within 60 s and 50 m of the open incident."""
    return (
        abs((event_time - last_event_time).total_seconds()) <= MERGE_WINDOW_S
        and distance_m <= MERGE_RADIUS_M
    )


def merge_signals(current: dict[str, float], incoming: dict[str, float]) -> dict[str, float]:
    """Keep the strongest value seen for every signal."""
    merged = dict(current)
    for name, value in incoming.items():
        merged[name] = max(value, merged.get(name, value))
    return merged


def best_ai_status(a: AiStatus, b: AiStatus) -> AiStatus:
    return a if _AI_RANK[a] >= _AI_RANK[b] else b


def best_verifier(a: VerifierResult, b: VerifierResult) -> VerifierResult:
    """Prefer an available verifier result, then the higher yes-probability."""
    if a.available != b.available:
        return a if a.available else b
    return a if (a.yes_probability or 0.0) >= (b.yes_probability or 0.0) else b
