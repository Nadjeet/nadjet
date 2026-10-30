"""AI status rules (PRD FR-VIS-007, doc 11 §6). Pure logic: the AI alone never confirms."""

from dataclasses import dataclass

from nadjet_shared import AiStatus, VerifierResult


@dataclass(frozen=True)
class StatusThresholds:
    confirmed: float = 0.8
    probable: float = 0.5


def classify(
    *,
    rule_fired: bool,
    verifier: VerifierResult,
    consecutive_sweep_hits: int = 0,
    thresholds: StatusThresholds = StatusThresholds(),  # noqa: B008  (frozen, immutable)
) -> AiStatus:
    """Map a rule trigger (or its absence) and a verifier result to an AI status.

    ``consecutive_sweep_hits`` counts consecutive AI-sweep windows (including this one) in
    which the verifier saw a collision; it only matters when no rule fired.
    """
    verdict = verifier.collision_visible if verifier.available else None
    p_yes = verifier.yes_probability

    if not rule_fired:
        # Sweep-only detections are never above "probable".
        if verdict == "yes" and consecutive_sweep_hits >= 2:
            return AiStatus.PROBABLE
        return AiStatus.POSSIBLE

    if verdict is None:
        return AiStatus.PROBABLE  # verifier unavailable: rule signals only
    if verdict == "cannot_judge":
        return AiStatus.INSUFFICIENT_EVIDENCE
    if verdict == "no":
        return AiStatus.POSSIBLE
    if p_yes is None:
        return AiStatus.PROBABLE  # "yes" without a usable probability is never confirmed
    if p_yes >= thresholds.confirmed:
        return AiStatus.CONFIRMED
    if p_yes >= thresholds.probable:
        return AiStatus.PROBABLE
    return AiStatus.POSSIBLE
