"""Camera health: fault state machine, staleness, live frame (FR-CAM-005, US-13)."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from nadjet_api.cameras.health import STALE_AFTER_S, is_stale, next_status
from nadjet_api.incidents.events import frame
from nadjet_shared.health import CameraHealthReport

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


def report(
    *, fault: bool = False, connected: bool = True, at: datetime = NOW
) -> CameraHealthReport:
    return CameraHealthReport(
        camera_id="cam-a1-pk42",
        at=at,
        connected=connected,
        fps=5.2,
        queue_depth=0,
        fault=fault,
        fault_reason="stall" if fault else None,
    )


@pytest.mark.parametrize(
    ("current", "fault", "connected", "expected"),
    [
        ("online", True, True, ("degraded", "camera_fault")),
        ("unknown", True, False, ("degraded", "camera_fault")),
        ("degraded", True, True, ("degraded", None)),  # already announced
        ("degraded", False, True, ("online", "camera_recovered")),
        ("unknown", False, True, ("online", None)),
        ("offline", False, True, ("online", None)),
        ("online", False, True, ("online", None)),
        ("unknown", False, False, ("unknown", None)),
    ],
)
def test_next_status(
    current: str, fault: bool, connected: bool, expected: tuple[str, str | None]
) -> None:
    assert next_status(current, report(fault=fault, connected=connected)) == expected


def test_report_is_stale_after_three_missed_pushes() -> None:
    fresh = report(at=NOW - timedelta(seconds=STALE_AFTER_S - 1))
    old = report(at=NOW - timedelta(seconds=STALE_AFTER_S + 1))
    assert not is_stale(fresh, NOW)
    assert is_stale(old, NOW)


def test_fault_flag_and_reason_must_agree() -> None:
    with pytest.raises(ValidationError):
        CameraHealthReport(camera_id="c", at=NOW, connected=True, fps=1, queue_depth=0, fault=True)
    with pytest.raises(ValidationError):
        CameraHealthReport(
            camera_id="c",
            at=NOW,
            connected=True,
            fps=1,
            queue_depth=0,
            fault_reason="stall",
        )


def test_camera_events_have_their_own_sse_frame() -> None:
    message = {"type": "camera_fault", "camera_id": "cam-a1-pk42", "status": "degraded"}
    assert frame(message) == (
        'event: camera_fault\ndata: {"camera_id": "cam-a1-pk42", "status": "degraded"}\n\n'
    )
