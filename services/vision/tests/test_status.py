import pytest

from nadjet_shared import AiStatus, VerifierResult
from nadjet_vision.status import classify


def verdict(answer: str | None, p_yes: float | None = None) -> VerifierResult:
    if answer is None:
        return VerifierResult(available=False)
    return VerifierResult(available=True, collision_visible=answer, yes_probability=p_yes)


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (verdict("yes", 0.92), AiStatus.CONFIRMED),
        (verdict("yes", 0.8), AiStatus.CONFIRMED),
        (verdict("yes", 0.65), AiStatus.PROBABLE),
        (verdict("yes", 0.3), AiStatus.POSSIBLE),
        (verdict("yes", None), AiStatus.PROBABLE),
        (verdict(None), AiStatus.PROBABLE),
        (verdict("no", 0.1), AiStatus.POSSIBLE),
        (verdict("cannot_judge"), AiStatus.INSUFFICIENT_EVIDENCE),
    ],
)
def test_rule_fired_status_table(result: VerifierResult, expected: AiStatus) -> None:
    assert classify(rule_fired=True, verifier=result) is expected


def test_ai_alone_never_confirms_even_when_certain() -> None:
    status = classify(rule_fired=False, verifier=verdict("yes", 0.99), consecutive_sweep_hits=5)
    assert status is AiStatus.PROBABLE


def test_single_sweep_hit_is_only_possible() -> None:
    status = classify(rule_fired=False, verifier=verdict("yes", 0.99), consecutive_sweep_hits=1)
    assert status is AiStatus.POSSIBLE


def test_sweep_without_collision_is_possible_at_most() -> None:
    status = classify(rule_fired=False, verifier=verdict("no"), consecutive_sweep_hits=3)
    assert status is AiStatus.POSSIBLE
