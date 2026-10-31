"""Unit: need-based filtering and the hospital pre-alert line (FR-DSP-001/002, FR-NTF-006)."""

import uuid
from datetime import UTC, datetime

import pytest

from nadjet_api.dispatch.need import hospital_need, unit_agencies
from nadjet_api.dispatch.schemas import DeliveryOut, DispatchOut
from nadjet_api.dispatch.service import for_responder
from nadjet_api.notifications.grammar import fits_sms, format_alert


def test_FR_DSP_001_units_are_ambulances_and_civil_protection_by_default() -> None:
    assert unit_agencies(needs_extrication=False) == ("civil_protection", "samu")


def test_FR_DSP_001_extrication_needs_civil_protection_only() -> None:
    assert unit_agencies(needs_extrication=True) == ("civil_protection",)


@pytest.mark.parametrize(
    ("priority", "mass_casualty", "extrication", "expected"),
    [
        (1, False, False, "trauma"),
        (2, False, False, "trauma"),
        (3, False, False, "emergency"),
        (4, False, False, "emergency"),
        (4, True, False, "trauma"),
        (3, False, True, "trauma"),
    ],
)
def test_FR_DSP_002_hospital_capability_follows_severity(
    priority: int, mass_casualty: bool, extrication: bool, expected: str
) -> None:
    need = hospital_need(
        priority=priority, mass_casualty=mass_casualty, needs_extrication=extrication
    )
    assert need == expected


def test_FR_NTF_006_prealert_line_carries_the_eta_and_fits_one_sms() -> None:
    line = format_alert(
        kind="PRE",
        priority=1,
        lat=36.762,
        lon=3.477,
        road="A1",
        pk_km=42,
        vehicles=2,
        short_code="7F3",
        eta_min=12,
    )
    assert line == "PRE|P1|36.76200,3.47700|A1 PK42|2V|E12|7F3"
    assert fits_sms(line)


def test_alert_line_is_unchanged_without_an_eta() -> None:
    line = format_alert(
        kind="ACC",
        priority=1,
        lat=36.648,
        lon=3.329,
        road="A1",
        pk_km=42,
        vehicles=2,
        short_code="7F3",
    )
    assert line == "ACC|P1|36.64800,3.32900|A1 PK42|2V|7F3"


def _row(kind: str, status: str = "dispatched") -> DispatchOut:
    return DispatchOut(
        id=uuid.uuid4(),
        kind=kind,  # type: ignore[arg-type]
        resource_id="x",
        name="X",
        agency=None,
        simulated=False,
        lat=36.7,
        lon=3.4,
        eta_s=60,
        distance_m=500,
        route_geojson=None,
        status=status,  # type: ignore[arg-type]
        dispatched_by=uuid.uuid4(),
        at=datetime.now(UTC),
        deliveries=[DeliveryOut(channel="sms", status="sent", attempts=1)],
    )


def test_FR_RSP_001_a_responder_only_gets_the_active_hospital_without_deliveries() -> None:
    rows = [_row("unit"), _row("hospital", "replaced"), _row("hospital"), _row("unit")]
    seen = for_responder(rows)
    assert [(r.kind, r.status, r.deliveries) for r in seen] == [("hospital", "dispatched", [])]
    assert rows[2].deliveries  # the operator's copy is untouched
