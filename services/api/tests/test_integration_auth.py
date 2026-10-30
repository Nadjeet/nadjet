"""Integration: login, audit immutability + chain, rate limiter, seeding (real PostGIS/Redis)."""

import asyncio
import uuid
from pathlib import Path

import httpx
import pytest
from fastapi import Depends, FastAPI
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.audit import AuditTarget, audit, verify_chain
from nadjet_api.auth.roles import Role
from nadjet_api.auth.seed import SeedUser, load_seed_file, seed_users
from nadjet_api.ratelimit import rate_limit

from .conftest import PASSWORD, MakeUser

pytestmark = pytest.mark.integration

EXAMPLE_SEED = Path(__file__).resolve().parents[3] / "data" / "seed" / "users.example.yaml"


async def test_login_me_flow_and_audit(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user(session, role="responder", agency="samu")
    response = await client.post(
        "/auth/login", json={"username": user.username, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["agency"] == "samu"
    assert "password" not in response.text

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["username"] == user.username

    logged = await session.scalar(
        text("SELECT count(*) FROM audit_log WHERE action='auth.login' AND actor_id=:i"),
        {"i": user.id},
    )
    assert logged == 1


async def test_bad_credentials_are_indistinguishable(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user(session)
    inactive = await make_user(session, active=False)
    attempts = [
        {"username": user.username, "password": "wrong"},
        {"username": "no-such-user", "password": PASSWORD},
        {"username": inactive.username, "password": PASSWORD},
    ]
    responses = [await client.post("/auth/login", json=a) for a in attempts]
    assert {r.status_code for r in responses} == {401}
    assert len({r.text for r in responses}) == 1


async def test_me_rejects_missing_bad_and_deactivated(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    assert (await client.get("/auth/me")).status_code == 401
    assert (
        await client.get("/auth/me", headers={"Authorization": "Bearer junk"})
    ).status_code == 401
    user = await make_user(session)
    token = (
        await client.post("/auth/login", json={"username": user.username, "password": PASSWORD})
    ).json()["access_token"]
    await session.execute(text("UPDATE users SET active=false WHERE id=:i"), {"i": user.id})
    await session.commit()
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_audit_log_is_append_only_and_chain_verifies(
    session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user(session)
    first = await audit(session, user, "evidence.view", AuditTarget("incident", "1"), {"k": "v"})
    second = await audit(session, None, "system.event", details={"n": 1}, ip="10.0.0.1")
    await session.commit()
    first_id, first_hash = first.id, first.hash
    assert second.prev_hash == first_hash

    status = await verify_chain(session)
    assert status.ok and status.checked >= 2

    for statement in (
        "UPDATE audit_log SET action='x' WHERE id=:i",
        "DELETE FROM audit_log WHERE id=:i",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            await session.execute(text(statement), {"i": first_id})
        await session.rollback()
    with pytest.raises(DBAPIError, match="append-only"):
        await session.execute(text("TRUNCATE audit_log"))
    await session.rollback()
    assert (await verify_chain(session)).ok


async def test_verify_chain_reports_first_tampered_row(session: AsyncSession) -> None:
    """NFR-SEC-002: a row altered behind the trigger's back breaks the chain at that row."""
    entry = await audit(session, None, "tamper.test", details={"n": 1})
    await audit(session, None, "tamper.test", details={"n": 2})
    await session.commit()
    entry_id = entry.id
    # DDL is transactional in Postgres: the trigger is back once we roll back.
    await session.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only"))
    await session.execute(
        text("UPDATE audit_log SET details='{\"n\": 99}' WHERE id=:i"), {"i": entry_id}
    )
    status = await verify_chain(session)
    await session.rollback()
    assert not status.ok
    assert status.broken_at == entry_id
    assert (await verify_chain(session)).ok


async def test_concurrent_audit_writes_keep_one_chain(app: FastAPI) -> None:
    async def write(n: int) -> None:
        async with app.state.session_factory() as s:
            await audit(s, None, "concurrent.test", details={"n": n})
            await s.commit()

    await asyncio.gather(*(write(i) for i in range(8)))
    async with app.state.session_factory() as s:
        assert (await verify_chain(s)).ok


async def test_rate_limiter_blocks_then_resets(app: FastAPI) -> None:
    name = f"it-{uuid.uuid4().hex[:8]}"
    probe = FastAPI()
    probe.state.redis = app.state.redis

    @probe.get("/public", dependencies=[Depends(rate_limit(name, per_minute=3, window_s=1))])
    async def public() -> dict[str, bool]:
        return {"ok": True}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=probe), base_url="http://test"
    ) as c:
        codes = [(await c.get("/public")).status_code for _ in range(5)]
        assert codes == [200, 200, 200, 429, 429]
        blocked = await c.get("/public")
        assert blocked.headers["retry-after"] == "1"
        await asyncio.sleep(1.2)
        assert (await c.get("/public")).status_code == 200
    redis: Redis = app.state.redis
    assert await redis.ping()


async def test_seed_users_is_idempotent_and_covers_every_role(
    session: AsyncSession, tmp_path: Path
) -> None:
    example = EXAMPLE_SEED
    prefix = uuid.uuid4().hex[:8]
    seeds = [
        SeedUser.model_validate(
            {**s.model_dump(mode="json") | {"password": s.password.get_secret_value()}},
        ).model_copy(update={"username": f"{prefix}-{s.username}"})
        for s in load_seed_file(example)
    ]
    assert {s.role for s in seeds} == set(Role)

    assert await seed_users(session, seeds) == (len(seeds), 0)
    assert await seed_users(session, seeds) == (0, len(seeds))
    count = await session.scalar(
        text("SELECT count(*) FROM users WHERE username LIKE :p"), {"p": f"{prefix}-%"}
    )
    assert count == len(seeds)
