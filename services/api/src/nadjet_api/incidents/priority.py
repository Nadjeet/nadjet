"""Explainable priority P1-P4 (FR-INC-003/004/008, D-15; docs/04 section 6). Pure functions.

Level numbers: 1 is the most urgent. Each fired rule sets a minimum; the final priority is the
most urgent minimum. Night/highway and an AI raise add at most one level together; the AI never
lowers. Triage, once present, replaces the AI raise and the context bump.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from nadjet_shared.events import AiStatus, VerifierResult, Witness

# Names of the observable signals read from ``IncidentCandidate.signals`` (value > 0 = present).
BUS_INVOLVED = "bus_involved"
PERSON_ON_ROAD = "person_on_road"
FLAMES = "flames"
SMOKE = "smoke"
OVERTURNED = "overturned"
VEHICLE_COUNT = "vehicle_count"
STOPPED_IN_LANE = "stopped_in_lane"
STOPPED_OFF_LANE = "stopped_off_lane"
NIGHT = "night"
HIGHWAY = "highway"

MASS_CASUALTY_VICTIMS = 5


class TriageTag(StrEnum):
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"
    BLACK = "black"


TRIAGE_LEVEL = {TriageTag.RED: 1, TriageTag.YELLOW: 2, TriageTag.GREEN: 3, TriageTag.BLACK: 3}


@dataclass(frozen=True)
class Reason:
    rule: str
    level: int
    detail: str
    source: str  # rule name or model id (FR-VIS-021)


@dataclass(frozen=True)
class PriorityResult:
    priority: int
    reasons: list[Reason]
    to_assess: bool = False
    mass_casualty: bool = False
    needs_extrication: bool = False
    flags: list[str] = field(default_factory=list)


def _on(signals: dict[str, float], name: str) -> bool:
    return signals.get(name, 0.0) > 0


def _rule_minimums(signals: dict[str, float], witness: Witness | None) -> list[Reason]:
    vehicles = int(signals.get(VEHICLE_COUNT, 0))
    rules: list[tuple[bool, str, int, str]] = [
        (_on(signals, BUS_INVOLVED), "bus_involved", 1, "Bus involved (possible mass casualty)"),
        (_on(signals, PERSON_ON_ROAD), "person_on_road", 1, "Person on the carriageway"),
        (_on(signals, FLAMES), "flames", 1, "Visible flames"),
        (bool(witness and witness.trapped), "trapped", 1, "Someone reported trapped"),
        (vehicles >= 3, "vehicles_3_plus", 2, f"{vehicles} vehicles involved"),
        (_on(signals, OVERTURNED), "overturned", 2, "Overturned vehicle"),
        (_on(signals, SMOKE), "smoke", 2, "Persistent smoke near a vehicle"),
        (_on(signals, STOPPED_IN_LANE), "stopped_in_lane", 3, "Vehicle stopped in a live lane"),
        (vehicles == 2, "two_vehicle_collision", 3, "Two-vehicle collision"),
        (_on(signals, STOPPED_OFF_LANE), "stopped_off_lane", 4, "Vehicle stopped off the lane"),
    ]
    return [
        Reason(rule, level, detail, f"rule:{rule}") for hit, rule, level, detail in rules if hit
    ]


def compute_priority(
    signals: dict[str, float],
    verifier: VerifierResult,
    ai_status: AiStatus | None,
    witness: Witness | None = None,
    triage: list[TriageTag] | None = None,
) -> PriorityResult:
    """Priority, reasons and flags from signals, AI result, witness answers and triage.

    ``ai_status=None`` means no AI was involved (operator-created incident).
    """
    triage = triage or []
    reasons = _rule_minimums(signals, witness)
    flags: list[str] = []

    if ai_status is not None and not verifier.available:
        flags.append("ai_unavailable")
    if ai_status is AiStatus.INSUFFICIENT_EVIDENCE:
        flags.append("insufficient_evidence")
    if verifier.collision_visible == "no":
        flags.append("ai_contradicts_rule")

    to_assess = ai_status is AiStatus.INSUFFICIENT_EVIDENCE or not reasons
    if to_assess:
        reasons.append(
            Reason("to_assess", 2, "Not enough evidence to judge (D-15)", "rule:to_assess")
        )

    if triage:
        worst = min(TRIAGE_LEVEL[t] for t in triage)
        reasons.append(
            Reason("triage", worst, f"Triage reports {len(triage)} casualt(ies)", "triage")
        )
    level = min(r.level for r in reasons)

    if not triage:
        bump = False
        if _on(signals, NIGHT) or _on(signals, HIGHWAY):
            bump = True
            context = "night" if _on(signals, NIGHT) else "highway"
            reasons.append(
                Reason("context", max(level - 1, 1), f"{context}: +1 level", f"rule:{context}")
            )
        if (
            verifier.available
            and verifier.priority_raise > 0
            and verifier.findings
            and not bump
            and verifier.model
        ):
            reasons.append(
                Reason(
                    "ai_raise",
                    max(level - 1, 1),
                    "AI raise: " + "; ".join(verifier.findings),
                    verifier.model,
                )
            )
            bump = True
        if bump:
            level -= 1
        level = max(level, 1)

    victims = len(triage)
    return PriorityResult(
        priority=level,
        reasons=reasons,
        to_assess=to_assess,
        mass_casualty=_on(signals, BUS_INVOLVED) or victims >= MASS_CASUALTY_VICTIMS,
        needs_extrication=bool(witness and witness.trapped),
        flags=flags,
    )
