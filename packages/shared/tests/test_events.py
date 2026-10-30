from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from nadjet_shared import (
    AiStatus,
    CandidateSource,
    GeoLocation,
    IncidentCandidate,
    TriggerType,
    VerifierResult,
)
from nadjet_shared.export_schemas import export, main

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


def make_candidate(**overrides: object) -> IncidentCandidate:
    data: dict[str, object] = {
        "camera_id": "cam-a1-pk42",
        "location": GeoLocation(lat=36.648, lon=3.329, road="A1"),
        "trigger": TriggerType.COLLISION_CANDIDATE,
        "event_time": NOW,
        "detected_at": NOW,
        "verifier": VerifierResult(available=False),
        "ai_status": AiStatus.PROBABLE,
    }
    data.update(overrides)
    return IncidentCandidate.model_validate(data)


def test_candidate_round_trips_through_json() -> None:
    candidate = make_candidate(track_ids=[3, 7], signals={"stop_seconds": 3.4})
    assert IncidentCandidate.model_validate_json(candidate.model_dump_json()) == candidate


def test_candidate_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        make_candidate(unexpected="value")


def test_candidate_requires_camera_id() -> None:
    with pytest.raises(ValidationError):
        make_candidate(camera_id="")


def test_citizen_candidate_needs_no_camera_and_defaults_to_no_ai() -> None:
    candidate = IncidentCandidate(
        source=CandidateSource.CITIZEN,
        location=GeoLocation(lat=36.7, lon=3.1),
        trigger=TriggerType.CITIZEN_REPORT,
        event_time=NOW,
        detected_at=NOW,
    )
    assert candidate.verifier.available is False
    assert candidate.ai_status is AiStatus.INSUFFICIENT_EVIDENCE


def test_location_is_required() -> None:
    with pytest.raises(ValidationError):
        IncidentCandidate.model_validate(
            {"trigger": "hard_stop", "event_time": NOW, "detected_at": NOW, "camera_id": "c"}
        )


def test_verifier_raise_is_at_most_one_level() -> None:
    with pytest.raises(ValidationError):
        VerifierResult(available=True, priority_raise=2)


@pytest.mark.parametrize("value", [-0.1, 1.5])
def test_yes_probability_must_be_a_probability(value: float) -> None:
    with pytest.raises(ValidationError):
        VerifierResult(available=True, yes_probability=value)


def test_verdict_values_are_restricted() -> None:
    with pytest.raises(ValidationError):
        VerifierResult(available=True, collision_visible="maybe")


def test_export_writes_then_reports_no_drift(tmp_path: Path) -> None:
    assert sorted(export(tmp_path, check=False)) == [
        "camera.health.schema.json",
        "incident.candidate.schema.json",
    ]
    assert export(tmp_path, check=True) == []


def test_check_mode_fails_on_drift_without_writing(tmp_path: Path) -> None:
    (tmp_path / "incident.candidate.schema.json").write_text("{}\n")
    assert main(["--check", "--out", str(tmp_path)]) == 1
    assert (tmp_path / "incident.candidate.schema.json").read_text() == "{}\n"


def test_committed_schemas_are_up_to_date() -> None:
    assert main(["--check"]) == 0


def test_candidate_rejects_naive_timestamps() -> None:
    """Naive times would break merge arithmetic and be stored in the DB session's zone."""
    with pytest.raises(ValidationError):
        make_candidate(event_time=datetime(2026, 10, 30, 12, 0))
