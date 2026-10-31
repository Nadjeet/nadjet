"""What an incident needs from the response (FR-DSP-001, FR-DSP-002). Pure."""

MEDICAL_AGENCIES = ("civil_protection", "samu")
EXTRICATION_AGENCIES = ("civil_protection",)  # only Civil Protection frees trapped people


def unit_agencies(*, needs_extrication: bool) -> tuple[str, ...]:
    """Agencies whose units can answer: ambulances and Civil Protection, or Civil Protection
    alone when someone must be extricated."""
    return EXTRICATION_AGENCIES if needs_extrication else MEDICAL_AGENCIES


def hospital_need(*, priority: int, mass_casualty: bool, needs_extrication: bool) -> str:
    """Capability a hospital must declare: trauma for serious or crowded scenes."""
    return "trauma" if priority <= 2 or mass_casualty or needs_extrication else "emergency"
