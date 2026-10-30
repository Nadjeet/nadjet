"""Roles, agencies and the data scope each role may see (FR-SEC-001, FR-SEC-002)."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class Role(StrEnum):
    OPERATOR = "operator"
    SUPERVISOR = "supervisor"
    RESPONDER = "responder"  # bound to one agency
    HOSPITAL = "hospital"  # bound to one facility
    AUDITOR = "auditor"
    ADMIN = "admin"


class Agency(StrEnum):
    CIVIL_PROTECTION = "civil_protection"
    GENDARMERIE = "gendarmerie"
    POLICE = "police"
    SAMU = "samu"


@dataclass(frozen=True)
class Scope:
    """Filter later issues apply to their queries.

    ``unrestricted`` roles see everything; otherwise results are limited to ``agency`` or
    ``facility_id`` (exactly one of them is set).
    """

    unrestricted: bool = False
    agency: Agency | None = None
    facility_id: str | None = None


def validate_role_binding(role: Role, agency: Agency | None, facility_id: str | None) -> None:
    """Raise ``ValueError`` unless agency/facility match the role (responder, hospital)."""
    if role is Role.RESPONDER and (agency is None or facility_id is not None):
        raise ValueError("responder requires an agency and no facility_id")
    if role is Role.HOSPITAL and (facility_id is None or agency is not None):
        raise ValueError("hospital requires a facility_id and no agency")
    if role not in (Role.RESPONDER, Role.HOSPITAL) and (agency or facility_id):
        raise ValueError(f"{role.value} must not have an agency or facility_id")


class HasRoleBinding(Protocol):
    role: str
    agency: str | None
    facility_id: str | None


def scope_for(user: HasRoleBinding) -> Scope:
    """Data scope for ``user`` (any object with role, agency and facility_id)."""
    role = Role(user.role)
    agency = Agency(user.agency) if user.agency else None
    validate_role_binding(role, agency, user.facility_id)
    if role is Role.RESPONDER:
        return Scope(agency=agency)
    if role is Role.HOSPITAL:
        return Scope(facility_id=user.facility_id)
    return Scope(unrestricted=True)
