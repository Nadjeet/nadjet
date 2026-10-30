"""Incident lifecycle state machine (FR-INC-005/006). Pure."""

from enum import StrEnum


class IncidentStatus(StrEnum):
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    REJECTED = "rejected"
    MERGED = "merged"
    DISPATCHED = "dispatched"
    ACKNOWLEDGED = "acknowledged"
    EN_ROUTE = "en_route"
    ON_SCENE = "on_scene"
    TRANSPORTING = "transporting"
    AT_HOSPITAL = "at_hospital"
    CLOSED = "closed"


class RejectReason(StrEnum):
    FALSE_POSITIVE = "false_positive"
    DUPLICATE = "duplicate"
    NOT_EMERGENCY = "not_emergency"
    OTHER = "other"


S = IncidentStatus
TRANSITIONS: dict[IncidentStatus, frozenset[IncidentStatus]] = {
    S.CANDIDATE: frozenset({S.VERIFIED, S.REJECTED, S.MERGED}),
    S.VERIFIED: frozenset({S.DISPATCHED}),
    S.DISPATCHED: frozenset({S.ACKNOWLEDGED}),
    S.ACKNOWLEDGED: frozenset({S.EN_ROUTE}),
    S.EN_ROUTE: frozenset({S.ON_SCENE}),
    S.ON_SCENE: frozenset({S.TRANSPORTING, S.CLOSED}),
    S.TRANSPORTING: frozenset({S.AT_HOSPITAL}),
    S.AT_HOSPITAL: frozenset({S.CLOSED}),
    S.REJECTED: frozenset(),
    S.MERGED: frozenset(),
    S.CLOSED: frozenset(),
}
CLOSED_STATUSES = frozenset({S.REJECTED, S.MERGED, S.CLOSED})
OPEN_STATUSES = frozenset(set(IncidentStatus) - CLOSED_STATUSES)


class IllegalTransitionError(Exception):
    def __init__(self, current: IncidentStatus, target: IncidentStatus) -> None:
        super().__init__(f"cannot go from {current.value} to {target.value}")
        self.current = current
        self.target = target


def check_transition(current: IncidentStatus, target: IncidentStatus) -> None:
    if target not in TRANSITIONS[current]:
        raise IllegalTransitionError(current, target)
