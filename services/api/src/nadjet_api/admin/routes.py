"""``/admin``: manage cameras, facilities, units and users (admin only, every change audited).

FR-ADM-001. Audit entries record which fields changed, never passwords.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.audit import AuditTarget, audit
from nadjet_api.auth.deps import require_roles
from nadjet_api.auth.models import User
from nadjet_api.auth.roles import Agency, Role, validate_role_binding
from nadjet_api.auth.security import hash_password
from nadjet_api.cameras.models import Camera
from nadjet_api.db import get_session

router = APIRouter(prefix="/admin", tags=["admin"])

AdminUser = Annotated[User, Depends(require_roles(Role.ADMIN))]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Not authenticated"},
    403: {"description": "Not an admin"},
}
MIN_PASSWORD_LENGTH = 12


class Patch(BaseModel):
    """Request body where only the fields that were sent are changed."""

    model_config = ConfigDict(extra="forbid")

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


# ------------------------------------------------------------------------------ cameras


class AdminCamera(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    road: str
    pk_km: float | None
    heading_deg: float
    wilaya: str
    zones: dict[str, Any] | None
    status: str
    simulated: bool


class CameraPatch(Patch):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    road: str | None = Field(default=None, min_length=1, max_length=64)
    pk_km: float | None = None
    heading_deg: float | None = Field(default=None, ge=0, lt=360)
    wilaya: str | None = Field(default=None, min_length=1, max_length=64)


def _camera(camera: Camera) -> AdminCamera:
    return AdminCamera.model_validate(camera, from_attributes=True)


@router.get("/cameras", responses=RESPONSES)
async def list_cameras(_admin: AdminUser, session: SessionDep) -> list[AdminCamera]:
    return [_camera(c) for c in await session.scalars(select(Camera).order_by(Camera.id))]


async def _camera_or_404(session: AsyncSession, camera_id: str) -> Camera:
    camera = await session.get(Camera, camera_id, with_for_update=True)
    if camera is None:
        raise _not_found("Camera")
    return camera


@router.patch("/cameras/{camera_id}", responses={**RESPONSES, 404: {"description": "Unknown"}})
async def update_camera(
    camera_id: str, body: CameraPatch, request: Request, admin: AdminUser, session: SessionDep
) -> AdminCamera:
    camera = await _camera_or_404(session, camera_id)
    changes = body.changes()
    for field, value in changes.items():
        if value is None and field != "pk_km":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{field} cannot be null")
        setattr(camera, field, value)
    camera.updated_at = datetime_now()
    await audit(
        session,
        admin,
        "admin.camera.update",
        AuditTarget("camera", camera_id),
        {"fields": sorted(changes)},
        ip=_client_ip(request),
    )
    await session.commit()
    return _camera(camera)


@router.put("/cameras/{camera_id}/zones", responses={**RESPONSES, 404: {"description": "Unknown"}})
async def replace_zones(
    camera_id: str,
    zones: dict[str, Any],
    request: Request,
    admin: AdminUser,
    session: SessionDep,
) -> AdminCamera:
    """Replace the camera's zones (``live_lanes`` / ``carriageway`` polygons) with this JSON."""
    camera = await _camera_or_404(session, camera_id)
    camera.zones = zones
    camera.updated_at = datetime_now()
    await audit(
        session,
        admin,
        "admin.camera.zones",
        AuditTarget("camera", camera_id),
        {"keys": sorted(zones)},
        ip=_client_ip(request),
    )
    await session.commit()
    return _camera(camera)


def datetime_now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------- facilities


class AdminFacility(BaseModel):
    id: str
    kind: str
    name: str
    wilaya: str | None
    capabilities: dict[str, bool]
    ready_state: Literal["ready", "divert"]
    contact_sms: str | None
    simulated: bool


class FacilityPatch(Patch):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    capabilities: dict[str, bool] | None = None
    ready_state: Literal["ready", "divert"] | None = None
    contact_sms: str | None = Field(default=None, max_length=32)


_FACILITY_COLUMNS = "id, kind, name, wilaya, capabilities, ready_state, contact_sms, simulated"
_LIST_FACILITIES = f"SELECT {_FACILITY_COLUMNS} FROM facilities ORDER BY id"  # noqa: S608


@router.get("/facilities", responses=RESPONSES)
async def list_facilities(_admin: AdminUser, session: SessionDep) -> list[AdminFacility]:
    rows = await session.execute(text(_LIST_FACILITIES))
    return [AdminFacility(**row) for row in rows.mappings()]


@router.patch("/facilities/{facility_id}", responses={**RESPONSES, 404: {"description": "Unknown"}})
async def update_facility(
    facility_id: str,
    body: FacilityPatch,
    request: Request,
    admin: AdminUser,
    session: SessionDep,
) -> AdminFacility:
    changes = body.changes()
    if any(changes.get(f) is None for f in ("name", "capabilities", "ready_state") if f in changes):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Fields cannot be null")
    row = await _update_row(session, "facilities", facility_id, changes, _FACILITY_COLUMNS)
    await audit(
        session,
        admin,
        "admin.facility.update",
        AuditTarget("facility", facility_id),
        {"fields": sorted(changes)},
        ip=_client_ip(request),
    )
    await session.commit()
    return AdminFacility(**row)


# ---------------------------------------------------------------------------------- units


class AdminUnit(BaseModel):
    id: str
    facility_id: str
    agency: str
    callsign: str
    status: Literal["available", "dispatched", "busy", "offline"]
    phone: str | None
    simulated: bool


class UnitPatch(Patch):
    callsign: str | None = Field(default=None, min_length=1, max_length=64)
    status: Literal["available", "busy", "offline"] | None = Field(
        default=None, description="`dispatched` is set by dispatch only"
    )
    phone: str | None = Field(default=None, max_length=32)


_UNIT_COLUMNS = "id, facility_id, agency, callsign, status, phone, simulated"
_LIST_UNITS = f"SELECT {_UNIT_COLUMNS} FROM units ORDER BY id"  # noqa: S608


@router.get("/units", responses=RESPONSES)
async def list_units(_admin: AdminUser, session: SessionDep) -> list[AdminUnit]:
    rows = await session.execute(text(_LIST_UNITS))
    return [AdminUnit(**row) for row in rows.mappings()]


@router.patch(
    "/units/{unit_id}",
    responses={**RESPONSES, 404: {"description": "Unknown"}, 409: {"description": "Conflict"}},
)
async def update_unit(
    unit_id: str, body: UnitPatch, request: Request, admin: AdminUser, session: SessionDep
) -> AdminUnit:
    changes = body.changes()
    if any(changes.get(f) is None for f in ("callsign", "status") if f in changes):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Fields cannot be null")
    try:
        row = await _update_row(session, "units", unit_id, changes, _UNIT_COLUMNS)
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Callsign already used") from None
    await audit(
        session,
        admin,
        "admin.unit.update",
        AuditTarget("unit", unit_id),
        {"fields": sorted(changes)},
        ip=_client_ip(request),
    )
    await session.commit()
    return AdminUnit(**row)


async def _update_row(
    session: AsyncSession, table: str, row_id: str, changes: dict[str, Any], columns: str
) -> dict[str, Any]:
    """``UPDATE`` only the sent columns (names come from the Pydantic models, never the client)."""
    jsonb = {"capabilities"}
    sets = ", ".join(f"{c} = CAST(:{c} AS jsonb)" if c in jsonb else f"{c} = :{c}" for c in changes)
    params = {c: (_json(v) if c in jsonb else v) for c, v in changes.items()}
    sql = f"UPDATE {table} SET {sets} WHERE id = :id RETURNING {columns}"  # noqa: S608
    if not changes:
        sql = f"SELECT {columns} FROM {table} WHERE id = :id"  # noqa: S608
    row = (await session.execute(text(sql), {**params, "id": row_id})).mappings().first()
    if row is None:
        raise _not_found(table.removesuffix("s").capitalize())
    return dict(row)


def _json(value: Any) -> str:
    return json.dumps(value)


# --------------------------------------------------------------------------------- users


class AdminUserOut(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    role: Role
    agency: Agency | None
    facility_id: str | None
    phone: str | None
    active: bool
    created_at: datetime


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)
    role: Role
    agency: Agency | None = None
    facility_id: str | None = None
    phone: str | None = Field(default=None, max_length=32)


class UserPatch(Patch):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    role: Role | None = None
    agency: Agency | None = None
    facility_id: str | None = None
    phone: str | None = Field(default=None, max_length=32)
    active: bool | None = Field(default=None, description="false deactivates the account")
    password: str | None = Field(default=None, min_length=MIN_PASSWORD_LENGTH, max_length=128)


def _user(user: User) -> AdminUserOut:
    return AdminUserOut.model_validate(user, from_attributes=True)


def _check_binding(role: Role, agency: Agency | None, facility_id: str | None) -> None:
    try:
        validate_role_binding(role, agency, facility_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


@router.get("/users", responses=RESPONSES)
async def list_users(_admin: AdminUser, session: SessionDep) -> list[AdminUserOut]:
    return [_user(u) for u in await session.scalars(select(User).order_by(User.username))]


@router.post(
    "/users",
    status_code=status.HTTP_201_CREATED,
    responses={**RESPONSES, 409: {"description": "Username taken"}},
)
async def create_user(
    body: UserCreate, request: Request, admin: AdminUser, session: SessionDep
) -> AdminUserOut:
    _check_binding(body.role, body.agency, body.facility_id)
    user = User(
        username=body.username,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role=body.role.value,
        agency=body.agency.value if body.agency else None,
        facility_id=body.facility_id,
        phone=body.phone,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken") from None
    await audit(
        session,
        admin,
        "admin.user.create",
        AuditTarget("user", str(user.id)),
        {"username": user.username, "role": user.role},
        ip=_client_ip(request),
    )
    await session.commit()
    return _user(user)


@router.patch(
    "/users/{user_id}",
    responses={**RESPONSES, 404: {"description": "Unknown"}, 409: {"description": "Own account"}},
)
async def update_user(
    user_id: uuid.UUID, body: UserPatch, request: Request, admin: AdminUser, session: SessionDep
) -> AdminUserOut:
    user = await session.get(User, user_id, with_for_update=True)
    if user is None:
        raise _not_found("User")
    changes = body.changes()
    if any(changes.get(f) is None for f in ("display_name", "role", "active") if f in changes):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Fields cannot be null")
    if user.id == admin.id and (changes.get("active") is False or "role" in changes):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Admins cannot deactivate or change the role of themselves"
        )
    role = body.role or Role(user.role)
    # A role change must bring its own agency/facility; unrelated edits keep the stored ones.
    binding_changed = {"role", "agency", "facility_id"} & changes.keys()
    agency = Agency(user.agency) if user.agency else None
    facility_id = user.facility_id
    if binding_changed:
        agency = body.agency if "agency" in changes else (agency if "role" not in changes else None)
        facility_id = (
            body.facility_id
            if "facility_id" in changes
            else (facility_id if "role" not in changes else None)
        )
        _check_binding(role, agency, facility_id)
    for field in ("display_name", "phone", "active"):
        if field in changes:
            setattr(user, field, changes[field])
    if binding_changed:
        user.role = role.value
        user.agency = agency.value if agency else None
        user.facility_id = facility_id
    if body.password:
        user.password_hash = hash_password(body.password)
    await audit(
        session,
        admin,
        "admin.user.update",
        AuditTarget("user", str(user.id)),
        {"fields": sorted(changes)},
        ip=_client_ip(request),
    )
    await session.commit()
    return _user(user)
