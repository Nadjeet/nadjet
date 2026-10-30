"""Pure ranking rules (FR-DSP-001, FR-DSP-002), kept free of I/O for unit tests."""

from dataclasses import dataclass


@dataclass(frozen=True)
class HospitalCandidate:
    id: str
    capable: bool  # has the capability the incident needs
    ready: bool  # ready_state == "ready"
    eta_s: float


def hospital_order(c: HospitalCandidate) -> tuple[bool, bool, float]:
    """Sort key: capable first, then Ready before Divert, then shortest ETA (FR-DSP-002)."""
    return (not c.capable, not c.ready, c.eta_s)


def rank_hospitals(candidates: list[HospitalCandidate]) -> list[HospitalCandidate]:
    return sorted(candidates, key=hospital_order)


def apply_urban_multiplier(free_flow_s: float, multiplier: float) -> float:
    """OSRM gives free-flow time; urban traffic is approximated by a constant factor."""
    return free_flow_s * multiplier
