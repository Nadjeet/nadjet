from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from nadjet_shared import AiStatus, IncidentCandidate, TriggerType, VerifierResult
from nadjet_shared.export_schemas import export, main

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


def make_candidate(**overrides: object) -> IncidentCandidate:
    data: dict[str, object] = {
        "camera_id": "cam-a1-pk42",
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


@pytest.mark.parametrize("value", [-0.1, 1.5])
def test_yes_probability_must_be_a_probability(value: float) -> None:
    with pytest.raises(ValidationError):
        VerifierResult(available=True, yes_probability=value)


def test_verdict_values_are_restricted() -> None:
    with pytest.raises(ValidationError):
        VerifierResult(available=True, collision_visible="maybe")


def test_export_writes_then_reports_no_drift(tmp_path: Path) -> None:
    assert export(tmp_path, check=False) == ["incident.candidate.schema.json"]
    assert export(tmp_path, check=True) == []


def test_check_mode_fails_on_drift_without_writing(tmp_path: Path) -> None:
    (tmp_path / "incident.candidate.schema.json").write_text("{}\n")
    assert main(["--check", "--out", str(tmp_path)]) == 1
    assert (tmp_path / "incident.candidate.schema.json").read_text() == "{}\n"


def test_committed_schemas_are_up_to_date() -> None:
    assert main(["--check"]) == 0
