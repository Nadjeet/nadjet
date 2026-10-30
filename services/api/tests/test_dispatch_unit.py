"""Unit: need-based filtering and the hospital pre-alert line (FR-DSP-001/002, FR-NTF-006)."""

import pytest

from nadjet_api.dispatch.need import hospital_need, unit_agencies
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
