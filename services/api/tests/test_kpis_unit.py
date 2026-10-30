"""Unit: response-time durations and aggregates from a fixed timeline (FR-KPI-001/002, US-11)."""

from datetime import UTC, datetime, timedelta

import pytest

from nadjet_api.kpis import compute

T0 = datetime(2026, 10, 30, 12, 0, 0, tzinfo=UTC)


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def status(to: str, seconds: float) -> tuple[str, dict[str, object], datetime]:
    return ("status_changed", {"to": to}, at(seconds))


def test_FR_KPI_001_durations_of_a_complete_timeline() -> None:
    events = [
        ("created", {}, at(4)),
        status("verified", 34),
        status("dispatched", 94),
        status("acknowledged", 124),
        status("en_route", 150),
        status("on_scene", 694),
        status("transporting", 1000),
        status("at_hospital", 1294),
    ]
    reached = compute.milestones(T0, events)
    assert compute.durations(reached) == {
        "detection_s": 4,  # event -> created
        "verification_s": 30,  # created -> verified
        "acknowledge_s": 30,  # dispatched -> acknowledged
        "scene_s": 600,  # dispatched -> on scene
        "hospital_s": 1200,  # dispatched -> at hospital
    }


def test_durations_are_none_for_milestones_not_reached() -> None:
    events = [("created", {}, at(5)), status("verified", 20), status("dispatched", 50)]
    result = compute.durations(compute.milestones(T0, events))
    assert result["detection_s"] == 5
    assert result["verification_s"] == 15
    assert result["acknowledge_s"] is None
    assert result["scene_s"] is None


def test_first_event_wins_and_order_of_arrival_does_not_matter() -> None:
    events = [status("dispatched", 100), ("created", {}, at(2)), status("dispatched", 900)]
    assert compute.milestones(T0, events)["dispatched"] == at(100)


def test_a_clock_going_backwards_gives_none_not_a_negative_duration() -> None:
    events = [("created", {}, at(-3))]
    assert compute.durations(compute.milestones(T0, events))["detection_s"] is None


def test_other_event_kinds_do_not_count_as_milestones() -> None:
    events = [("casualty_added", {"to": "verified"}, at(1))]
    assert "verified" not in compute.milestones(T0, events)


@pytest.mark.parametrize(
    ("values", "median", "p90"),
    [
        ([], None, None),
        ([7], 7, 7),
        ([10, 20, 30, 40], 25, 37),  # linear interpolation: p90 rank 2.7 -> 30 + 0.7 * 10
        ([40, 10, 30, 20, 50], 30, 46),  # rank 3.6 -> 40 + 0.6 * 10
    ],
)
def test_median_and_p90_match_hand_computed_values(
    values: list[float], median: float | None, p90: float | None
) -> None:
    stats = compute.stats(values)
    assert stats.n == len(values)
    assert stats.median_s == median
    assert stats.p90_s == (pytest.approx(p90) if p90 is not None else None)


def test_FR_KPI_002_aggregate_skips_missing_values_per_metric() -> None:
    rows: list[dict[str, float | None]] = [
        {"detection_s": 2, "scene_s": 600},
        {"detection_s": 4, "scene_s": None},
        {"detection_s": 6, "scene_s": 1200},
    ]
    result = compute.aggregate(rows)
    assert (result["detection_s"].n, result["detection_s"].median_s) == (3, 4)
    assert (result["scene_s"].n, result["scene_s"].median_s) == (2, 900)
    assert result["hospital_s"] == compute.Stats(0, None, None)


def test_group_by_puts_an_item_in_every_bucket_it_belongs_to() -> None:
    groups = compute.group_by(
        [("a", ["police", "samu"]), ("b", ["samu"]), ("c", [])], lambda item: item[1]
    )
    assert {k: [i[0] for i in v] for k, v in groups.items()} == {
        "police": ["a"],
        "samu": ["a", "b"],
    }


def test_false_alarm_rate() -> None:
    assert compute.false_alarm_rate(1, 4) == 0.25
    assert compute.false_alarm_rate(0, 0) is None


@pytest.mark.parametrize(
    ("period", "key"),
    [("day", "2026-10-30"), ("week", "2026-W44"), ("month", "2026-10")],
)
def test_period_keys(period: str, key: str) -> None:
    assert compute.period_key(T0, period) == key
