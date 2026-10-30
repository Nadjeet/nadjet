"""Integration: /admin changes persist, are audited and are admin-only (FR-ADM-001, US-11)."""

import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.audit.models import AuditLog
from nadjet_api.auth.models import User
from nadjet_api.cameras.models import Camera

from .conftest import PASSWORD, MakeUser
from .test_integration_incidents import login

pytestmark = pytest.mark.integration


@pytest.fixture
async def admin(client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser) -> Any:
    user = await make_user(session, role="admin")
    return user, await login(client, user)


async def audited(session: AsyncSession, action: str, target_id: str) -> list[AuditLog]:
    rows = await session.scalars(
        select(AuditLog).where(AuditLog.action == action, AuditLog.target_id == target_id)
    )
    return list(rows)


@pytest.fixture
async def camera(session: AsyncSession) -> Camera:
    cam = Camera(
        id=f"adm-{uuid.uuid4().hex[:8]}", name="Admin test", stream_path="adm", lat=36.0, lon=3.0,
        road="RN1", wilaya="Alger",
    )  # fmt: skip
    session.add(cam)
    await session.commit()
    return cam


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/admin/cameras"),
        ("PATCH", "/admin/cameras/x"),
        ("PUT", "/admin/cameras/x/zones"),
        ("GET", "/admin/facilities"),
        ("PATCH", "/admin/facilities/x"),
        ("GET", "/admin/units"),
        ("PATCH", "/admin/units/x"),
        ("GET", "/admin/users"),
        ("POST", "/admin/users"),
        ("PATCH", f"/admin/users/{uuid.uuid4()}"),
    ],
)
async def test_every_admin_route_refuses_other_roles(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser, method: str, path: str
) -> None:
    assert (await client.request(method, path, json={})).status_code == 401
    for role in ("operator", "supervisor", "auditor"):
        headers = await login(client, await make_user(session, role=role))
        response = await client.request(method, path, json={}, headers=headers)
        assert response.status_code == 403, (role, response.text)


async def test_camera_edit_and_zone_upload_persist_and_are_audited(
    client: httpx.AsyncClient, session: AsyncSession, admin: Any, camera: Camera
) -> None:
    user, headers = admin
    response = await client.patch(
        f"/admin/cameras/{camera.id}", json={"name": "Renamed", "heading_deg": 90}, headers=headers
    )
    assert response.status_code == 200, response.text
    zones = {"live_lanes": [[[0, 0], [1, 0], [1, 1]]], "carriageway": [[[0, 0], [2, 0], [2, 2]]]}
    response = await client.put(f"/admin/cameras/{camera.id}/zones", json=zones, headers=headers)
    assert response.status_code == 200, response.text

    await session.refresh(camera)
    assert (camera.name, camera.heading_deg, camera.zones) == ("Renamed", 90, zones)
    (entry,) = await audited(session, "admin.camera.update", camera.id)
    assert entry.actor_id == user.id
    assert entry.details == {"fields": ["heading_deg", "name"]}
    assert len(await audited(session, "admin.camera.zones", camera.id)) == 1
    listed = await client.get("/admin/cameras", headers=headers)
    assert any(c["id"] == camera.id and c["name"] == "Renamed" for c in listed.json())


async def test_camera_edit_rejects_bad_values_and_unknown_cameras(
    client: httpx.AsyncClient, admin: Any, camera: Camera
) -> None:
    _, headers = admin
    for body in ({"heading_deg": 360}, {"name": None}, {"unknown": 1}, {"lat": 120}):
        response = await client.patch(f"/admin/cameras/{camera.id}", json=body, headers=headers)
        assert response.status_code == 422, body
    missing = await client.patch("/admin/cameras/nope", json={"name": "x"}, headers=headers)
    assert missing.status_code == 404
    assert (
        await client.put("/admin/cameras/nope/zones", json={}, headers=headers)
    ).status_code == 404


async def test_facility_edit_changes_capabilities_ready_state_and_sms_contact(
    client: httpx.AsyncClient, session: AsyncSession, admin: Any
) -> None:
    _, headers = admin
    fid = f"adm-fac-{uuid.uuid4().hex[:6]}"
    await session.execute(
        text(
            "INSERT INTO facilities (id, kind, name, geom) VALUES "
            "(:id, 'hospital', 'Admin test hospital', ST_SetSRID(ST_MakePoint(3, 36), 4326))"
        ),
        {"id": fid},
    )
    await session.commit()
    response = await client.patch(
        f"/admin/facilities/{fid}",
        json={"capabilities": {"trauma": True}, "ready_state": "divert", "contact_sms": "+213555"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["capabilities"] == {"trauma": True}
    row = (
        await session.execute(
            text("SELECT ready_state, contact_sms, capabilities FROM facilities WHERE id = :i"),
            {"i": fid},
        )
    ).one()
    assert tuple(row) == ("divert", "+213555", {"trauma": True})
    assert len(await audited(session, "admin.facility.update", fid)) == 1
    bad = await client.patch(
        f"/admin/facilities/{fid}", json={"ready_state": "busy"}, headers=headers
    )
    assert bad.status_code == 422
    unknown = await client.patch("/admin/facilities/none", json={"name": "x"}, headers=headers)
    assert unknown.status_code == 404
    await session.execute(text("DELETE FROM facilities WHERE id = :i"), {"i": fid})
    await session.commit()


async def test_unit_edit_cannot_set_dispatched_or_reuse_a_callsign(
    client: httpx.AsyncClient, session: AsyncSession, admin: Any
) -> None:
    _, headers = admin
    suffix = uuid.uuid4().hex[:6]
    fid = f"adm-fac-{suffix}"
    await session.execute(
        text(
            "INSERT INTO facilities (id, kind, name, geom) VALUES "
            "(:id, 'civil_protection', 'Admin station', ST_SetSRID(ST_MakePoint(3, 36), 4326))"
        ),
        {"id": fid},
    )
    for n in (1, 2):
        await session.execute(
            text(
                "INSERT INTO units (id, facility_id, agency, callsign, geom) VALUES "
                "(:id, :f, 'civil_protection', :c, ST_SetSRID(ST_MakePoint(3, 36), 4326))"
            ),
            {"id": f"adm-u{n}-{suffix}", "f": fid, "c": f"ADM-{n}-{suffix}"},
        )
    await session.commit()
    unit = f"adm-u1-{suffix}"
    ok = await client.patch(
        f"/admin/units/{unit}", json={"status": "offline", "phone": "+213777"}, headers=headers
    )
    assert ok.status_code == 200, ok.text
    assert (ok.json()["status"], ok.json()["phone"]) == ("offline", "+213777")
    assert len(await audited(session, "admin.unit.update", unit)) == 1
    dispatched = await client.patch(
        f"/admin/units/{unit}", json={"status": "dispatched"}, headers=headers
    )
    assert dispatched.status_code == 422
    clash = await client.patch(
        f"/admin/units/{unit}", json={"callsign": f"ADM-2-{suffix}"}, headers=headers
    )
    assert clash.status_code == 409
    await session.rollback()
    await session.execute(text("DELETE FROM units WHERE facility_id = :f"), {"f": fid})
    await session.execute(text("DELETE FROM facilities WHERE id = :f"), {"f": fid})
    await session.commit()


async def test_user_create_role_binding_deactivate_and_login_effects(
    client: httpx.AsyncClient, session: AsyncSession, admin: Any
) -> None:
    actor, headers = admin
    name = f"adm-{uuid.uuid4().hex[:8]}"
    body = {
        "username": name,
        "display_name": "New",
        "password": "a-long-password-1",
        "role": "operator",
    }
    created = await client.post("/admin/users", json=body, headers=headers)
    assert created.status_code == 201, created.text
    assert "password" not in created.text
    user_id = created.json()["id"]
    (entry,) = await audited(session, "admin.user.create", user_id)
    assert entry.actor_id == actor.id
    assert "a-long-password-1" not in str(entry.details)
    assert (await client.post("/admin/users", json=body, headers=headers)).status_code == 409
    login_ok = await client.post(
        "/auth/login", json={"username": name, "password": "a-long-password-1"}
    )
    assert login_ok.status_code == 200

    # Role bindings: a responder needs an agency, an operator must not have one.
    bad_role = await client.patch(
        f"/admin/users/{user_id}", json={"role": "responder"}, headers=headers
    )
    assert bad_role.status_code == 422
    good_role = await client.patch(
        f"/admin/users/{user_id}", json={"role": "responder", "agency": "samu"}, headers=headers
    )
    assert good_role.status_code == 200, good_role.text
    assert (good_role.json()["role"], good_role.json()["agency"]) == ("responder", "samu")
    back = await client.patch(
        f"/admin/users/{user_id}", json={"role": "supervisor"}, headers=headers
    )
    assert back.status_code == 200, back.text
    assert back.json()["agency"] is None

    off = await client.patch(f"/admin/users/{user_id}", json={"active": False}, headers=headers)
    assert off.status_code == 200
    refused = await client.post(
        "/auth/login", json={"username": name, "password": "a-long-password-1"}
    )
    assert refused.status_code == 401
    stored = await session.get(User, uuid.UUID(user_id), populate_existing=True)
    assert stored is not None and not stored.active
    assert len(await audited(session, "admin.user.update", user_id)) == 3
    listed = await client.get("/admin/users", headers=headers)
    assert any(u["id"] == user_id and not u["active"] for u in listed.json())


async def test_user_validation_and_self_protection(
    client: httpx.AsyncClient, session: AsyncSession, admin: Any
) -> None:
    actor, headers = admin
    weak = {"username": "weakling", "display_name": "W", "password": "short", "role": "operator"}
    assert (await client.post("/admin/users", json=weak, headers=headers)).status_code == 422
    unbound = {**weak, "password": "a-long-password-1", "role": "hospital"}
    assert (await client.post("/admin/users", json=unbound, headers=headers)).status_code == 422
    for body in ({"active": False}, {"role": "operator"}):
        response = await client.patch(f"/admin/users/{actor.id}", json=body, headers=headers)
        assert response.status_code == 409, body
    for body in ({"display_name": None}, {"active": None}, {"role": None}):
        response = await client.patch(f"/admin/users/{actor.id}", json=body, headers=headers)
        assert response.status_code == 422, body
    assert (
        await client.patch(f"/admin/users/{uuid.uuid4()}", json={}, headers=headers)
    ).status_code == 404
    # Changing the own display name and password is allowed.
    ok = await client.patch(
        f"/admin/users/{actor.id}",
        json={"display_name": "Me", "password": "another-long-pass-2"},
        headers=headers,
    )
    assert ok.status_code == 200, ok.text
    fresh = await client.post(
        "/auth/login", json={"username": actor.username, "password": "another-long-pass-2"}
    )
    assert fresh.status_code == 200
    assert PASSWORD != "another-long-pass-2"
