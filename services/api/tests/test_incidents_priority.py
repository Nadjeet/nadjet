"""Unit: explainable priority table (FR-INC-003/004/008, D-15; docs/04 section 6)."""

import pytest

from nadjet_api.incidents.priority import TriageTag, compute_priority
from nadjet_shared.events import AiStatus, Finding, VerifierResult, Witness

NO_AI = VerifierResult(available=False)
AI_RAISE = VerifierResult(
    available=True,
    model="Qwen/Qwen3-VL-8B-Instruct-FP8",
    collision_visible="yes",
    yes_probability=0.93,
    priority_raise=1,
    findings=[Finding(statement="vehicle on its side", basis="observed", frame_ids=[12])],
)
PROBABLE = AiStatus.PROBABLE


def prio(signals: dict[str, float], **kwargs: object) -> int:
    kwargs.setdefault("verifier", NO_AI)
    kwargs.setdefault("ai_status", PROBABLE)
    return compute_priority(signals, **kwargs).priority  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("signals", "expected"),
    [
        ({"bus_involved": 1}, 1),
        ({"person_on_road": 1}, 1),
        ({"flames": 1}, 1),
        ({"vehicle_count": 3}, 2),
        ({"vehicle_count": 5}, 2),
        ({"overturned": 1}, 2),
        ({"smoke": 1}, 2),
        ({"stopped_in_lane": 1}, 3),
        ({"vehicle_count": 2}, 3),
        ({"stopped_off_lane": 1}, 4),
        ({"vehicle_count": 2, "overturned": 1}, 2),  # highest minimum wins
        ({"vehicle_count": 3, "flames": 1}, 1),
    ],
)
def test_rule_minimums(signals: dict[str, float], expected: int) -> None:
    assert prio(signals) == expected


def test_FR_INC_003_missing_evidence_is_p2_to_assess() -> None:
    result = compute_priority({}, NO_AI, AiStatus.INSUFFICIENT_EVIDENCE)
    assert (result.priority, result.to_assess) == (2, True)
    assert "insufficient_evidence" in result.flags


def test_no_rule_fired_is_to_assess_even_with_ai_status() -> None:
    result = compute_priority({}, NO_AI, PROBABLE)
    assert (result.priority, result.to_assess) == (2, True)


def test_insufficient_evidence_pulls_a_p3_up_to_p2() -> None:
    result = compute_priority({"stopped_in_lane": 1}, NO_AI, AiStatus.INSUFFICIENT_EVIDENCE)
    assert (result.priority, result.to_assess) == (2, True)


def test_no_ai_involved_does_not_force_to_assess() -> None:
    result = compute_priority({"vehicle_count": 2}, NO_AI, None)
    assert (result.priority, result.to_assess) == (3, False)
    assert "ai_unavailable" not in result.flags


def test_trapped_is_p1_with_extrication() -> None:
    result = compute_priority({"stopped_off_lane": 1}, NO_AI, PROBABLE, Witness(trapped=True))
    assert result.priority == 1
    assert result.needs_extrication is True


def test_bus_flags_mass_casualty() -> None:
    result = compute_priority({"bus_involved": 1}, NO_AI, PROBABLE)
    assert (result.priority, result.mass_casualty) == (1, True)


def test_five_triaged_victims_flag_mass_casualty() -> None:
    four = compute_priority({"vehicle_count": 2}, NO_AI, PROBABLE, None, [TriageTag.GREEN] * 4)
    five = compute_priority({"vehicle_count": 2}, NO_AI, PROBABLE, None, [TriageTag.GREEN] * 5)
    assert (four.mass_casualty, five.mass_casualty) == (False, True)


def test_ai_raises_by_one_level_and_cites_the_model() -> None:
    result = compute_priority({"vehicle_count": 2}, AI_RAISE, PROBABLE)
    assert result.priority == 2
    raise_reason = next(r for r in result.reasons if r.rule == "ai_raise")
    assert raise_reason.source == "Qwen/Qwen3-VL-8B-Instruct-FP8"
    assert "vehicle on its side" in raise_reason.detail


def test_ai_raise_is_capped_at_one_level_even_with_night() -> None:
    result = compute_priority({"stopped_off_lane": 1, "night": 1, "highway": 1}, AI_RAISE, PROBABLE)
    assert result.priority == 3  # P4 + one level, not two


def test_ai_raise_without_a_cited_finding_is_ignored() -> None:
    uncited = AI_RAISE.model_copy(update={"findings": []})
    assert prio({"vehicle_count": 2}, verifier=uncited) == 3


def test_ai_raise_ignored_when_verifier_unavailable() -> None:
    unavailable = AI_RAISE.model_copy(update={"available": False})
    assert prio({"vehicle_count": 2}, verifier=unavailable) == 3


def test_ai_never_lowers_below_the_rule_minimum() -> None:
    says_no = VerifierResult(
        available=True, model="m", collision_visible="no", yes_probability=0.01
    )
    result = compute_priority({"flames": 1}, says_no, AiStatus.POSSIBLE)
    assert result.priority == 1
    assert "ai_contradicts_rule" in result.flags


def test_priority_never_goes_above_p1() -> None:
    assert prio({"bus_involved": 1, "night": 1}, verifier=AI_RAISE) == 1


@pytest.mark.parametrize("signal", ["night", "highway"])
def test_night_or_highway_adds_one_level(signal: str) -> None:
    assert prio({"vehicle_count": 2, signal: 1}) == 2


def test_FR_INC_004_triage_overrides_the_ai_raise() -> None:
    without = compute_priority({"vehicle_count": 2}, AI_RAISE, PROBABLE)
    with_green = compute_priority({"vehicle_count": 2}, AI_RAISE, PROBABLE, None, [TriageTag.GREEN])
    assert (without.priority, with_green.priority) == (2, 3)
    assert not any(r.rule in ("ai_raise", "context") for r in with_green.reasons)


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ([TriageTag.RED], 1),
        ([TriageTag.GREEN, TriageTag.YELLOW], 2),
        ([TriageTag.GREEN], 3),
        ([TriageTag.BLACK], 3),
        ([TriageTag.GREEN, TriageTag.RED], 1),
    ],
)
def test_triage_sets_the_priority(tags: list[TriageTag], expected: int) -> None:
    result = compute_priority({"vehicle_count": 2}, NO_AI, None, None, tags)
    assert result.priority == min(expected, 3)  # rule minimum P3 still applies


def test_every_reason_names_its_source() -> None:
    result = compute_priority({"flames": 1, "vehicle_count": 3}, AI_RAISE, PROBABLE)
    assert all(r.source for r in result.reasons)
