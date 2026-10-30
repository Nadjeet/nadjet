"""Unit: pre-alert arithmetic and the facility live event (FR-HSP-001, FR-INC-008, E-10)."""

import json
from datetime import UTC, datetime

from nadjet_api.auth.roles import Agency, Scope
from nadjet_api.hospital.board import expected_arrival, victim_counts
from nadjet_api.incidents.events import frame, visible_to


def test_FR_HSP_001_victims_are_counted_per_tag_and_in_total() -> None:
    counts = victim_counts(["red", "red", "yellow", "black", "red"])
    assert counts == {"red": 3, "yellow": 1, "green": 0, "black": 1, "total": 5}


def test_no_victims_is_all_zero() -> None:
    assert victim_counts([]) == {"red": 0, "yellow": 0, "green": 0, "black": 0, "total": 0}


def test_an_unknown_tag_still_counts_in_the_total() -> None:
    assert victim_counts(["red", "blue"])["total"] == 2


def test_FR_HSP_001_arrival_is_dispatch_time_plus_the_road_eta() -> None:
    sent = datetime(2026, 10, 30, 12, 0, 0, tzinfo=UTC)
    assert expected_arrival(sent, 754.4) == datetime(2026, 10, 30, 12, 12, 34, 400000, tzinfo=UTC)


FACILITY_EVENT: dict[str, object] = {
    "type": "facility.updated",
    "facility_id": "h-1",
    "ready_state": "divert",
    "agencies": [],
    "facilities": ["h-1"],
}


def test_the_facility_event_reaches_operators_and_that_hospital_only() -> None:
    assert visible_to(Scope(unrestricted=True), FACILITY_EVENT)
    assert visible_to(Scope(facility_id="h-1"), FACILITY_EVENT)
    assert not visible_to(Scope(facility_id="h-2"), FACILITY_EVENT)
    assert not visible_to(Scope(agency=Agency.CIVIL_PROTECTION), FACILITY_EVENT)


def test_the_facility_event_frame_carries_the_new_state() -> None:
    lines = frame(FACILITY_EVENT).split("\n")
    assert lines[0] == "event: facility.updated"
    assert json.loads(lines[1].removeprefix("data: ")) == {
        "facility_id": "h-1",
        "ready_state": "divert",
    }
