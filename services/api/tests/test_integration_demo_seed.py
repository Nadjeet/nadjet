"""Integration: ``seed-demo`` is idempotent and never creates incidents (PRD FR-VIS-020, SC-003)."""

import uuid
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api import cli
from nadjet_api.auth.models import User
from nadjet_api.auth.roles import Agency, Role
from nadjet_api.auth.seed import SeedUser
from nadjet_api.demo import seed_demo
from nadjet_api.geo.seed import load_capabilities, load_facilities, load_units
from nadjet_api.incidents.models import Incident
from nadjet_shared.catalogue import load_catalogue

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]


def users(tag: str, phone: str | None) -> list[SeedUser]:
    password = SecretStr("demo-seed-test-pw")
    return [
        SeedUser(username=f"op-{tag}", display_name="Op", password=password, role=Role.OPERATOR),
        SeedUser(
            username=f"resp-{tag}",
            display_name="Resp",
            password=password,
            role=Role.RESPONDER,
            agency=Agency.SAMU,
            phone=phone,
        ),
    ]


async def run(session: AsyncSession, seeds: list[SeedUser]):  # type: ignore[no-untyped-def]
    seed = ROOT / "data" / "seed"
    return await seed_demo(
        session,
        users=seeds,
        catalogue=load_catalogue(ROOT / "data" / "cameras.yaml"),
        facilities=load_facilities(seed / "facilities.csv"),
        capabilities=load_capabilities(seed / "capabilities.csv"),
        units=load_units(seed / "units.csv"),
    )


async def test_seeding_twice_changes_nothing_and_creates_no_incident(session: AsyncSession) -> None:
    tag = uuid.uuid4().hex[:8]
    seeds = users(tag, phone="0550123456")
    before = await session.scalar(select(func.count()).select_from(Incident))
    try:
        first = await run(session, seeds)
        second = await run(session, seeds)
        assert first.users_created == 2 and second.users_created == 0
        assert second.users_existing == 2
        assert (second.cameras, second.facilities, second.units) == (
            first.cameras,
            first.facilities,
            first.units,
        )
        assert first.cameras > 0 and first.facilities > 0 and first.units > 0
        assert first.incidents == second.incidents == before
        assert f"resp-{tag}" not in first.responders_without_phone
    finally:
        await session.execute(delete(User).where(User.username.like(f"%-{tag}")))
        await session.commit()


async def test_a_responder_without_a_phone_is_reported_as_no_sms_demo(
    session: AsyncSession,
) -> None:
    tag = uuid.uuid4().hex[:8]
    try:
        report = await run(session, users(tag, phone=None))
        assert f"resp-{tag}" in report.responders_without_phone
        assert any("WARNING" in line and f"resp-{tag}" in line for line in report.lines())
    finally:
        await session.execute(delete(User).where(User.username.like(f"%-{tag}")))
        await session.commit()


def test_seed_demo_needs_a_users_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code = cli.main(["seed-demo", "--users", str(tmp_path / "missing.yaml")])
    assert code == 1
    assert "not found" in capsys.readouterr().err


async def test_a_hospital_user_bound_to_an_unknown_facility_is_reported(
    session: AsyncSession,
) -> None:
    """The example users bound the hospital account to ``demo-hospital``, which no seed file
    creates: its pre-alert view stayed empty on the live run."""
    tag = uuid.uuid4().hex[:8]
    password = SecretStr("demo-seed-test-pw")
    seeds = [
        SeedUser(username=f"h-bad-{tag}", display_name="H", password=password,
                 role=Role.HOSPITAL, facility_id="no-such-facility"),
        SeedUser(username=f"h-ok-{tag}", display_name="H", password=password,
                 role=Role.HOSPITAL, facility_id="osm-way-28919252"),
    ]  # fmt: skip
    try:
        report = await run(session, seeds)
        assert f"h-bad-{tag}" in report.hospitals_without_facility
        assert f"h-ok-{tag}" not in report.hospitals_without_facility
        assert any("WARNING" in line and f"h-bad-{tag}" in line for line in report.lines())
    finally:
        await session.execute(delete(User).where(User.username.like(f"%-{tag}")))
        await session.commit()


def test_example_users_bind_the_hospital_to_a_seeded_facility() -> None:
    import yaml

    seeded = {line.split(",", 1)[0] for line in (ROOT / "data/seed/facilities.csv").open()}
    example = yaml.safe_load((ROOT / "data/seed/users.example.yaml").read_text())
    for user in example["users"]:
        if user.get("role") == "hospital":
            assert user["facility_id"] in seeded, user["username"]
