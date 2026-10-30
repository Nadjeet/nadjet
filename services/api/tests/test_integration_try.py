"""Integration: the try-it sandbox end to end (PostGIS, Redis): upload, worker, purge, live."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.incidents.models import Incident
from nadjet_api.main import create_app
from nadjet_api.tryit import service
from nadjet_api.tryit.models import TryJob, TrySession
from nadjet_api.tryit.routes import job_events
from nadjet_shared import AiStatus, VerifierResult
from nadjet_shared.tryit import SandboxIncident, TryResult

from .conftest import INGEST_TOKEN, MakeUser, make_settings
from .test_integration_incidents import login
from .test_try_unit import mp4

pytestmark = pytest.mark.integration

INTERNAL = {"Authorization": f"Bearer {INGEST_TOKEN}"}
VIDEO = {"Content-Type": "video/mp4"}


def make_app(tmp_path: Path, **overrides: Any) -> FastAPI:
    overrides.setdefault("try_dir", tmp_path / "sandbox")
    overrides.setdefault("try_jobs_per_minute", 1000)
    overrides.setdefault("try_sessions_per_minute", 1000)
    overrides.setdefault("try_purge_interval_s", 3600)
    return create_app(make_settings(tmp_path, **overrides))


@pytest.fixture(autouse=True)
async def clean_sandbox(app: FastAPI) -> None:
    """The queue is global: start every test with an empty sandbox."""
    async with app.state.session_factory() as db:
        await db.execute(delete(TryJob))
        await db.execute(delete(TrySession))
        await db.commit()


@pytest.fixture
async def sandbox(tmp_path: Path) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient]]:
    app = make_app(tmp_path)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            yield app, client


async def upload(client: httpx.AsyncClient, body: bytes, **kw: Any) -> httpx.Response:
    return await client.post("/public/try/jobs", content=body, headers=kw.pop("headers", VIDEO))


def result(**kw: Any) -> TryResult:
    verdict = VerifierResult(
        available=True, model="m", collision_visible="yes", yes_probability=0.9
    )
    data: dict[str, Any] = {
        "duration_s": 30.0, "frames_analysed": 150, "ai_available": True,
        "scan": verdict, "refine": verdict, "scan_t_s": 12.0, "event_t_s": 12.4,
        "sandbox_incident": SandboxIncident(
            type="possible_incident", ai_status=AiStatus.PROBABLE, event_time_s=12.4
        ),
    }  # fmt: skip
    data.update(kw)
    return TryResult(**data)


# ---------------------------------------------------------------- upload checks (E-12)


async def test_a_valid_clip_is_queued_in_the_sandbox(
    sandbox: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    app, client = sandbox
    response = await upload(client, mp4(30.0))
    assert response.status_code == 202, response.text
    body = response.json()
    assert (body["status"], body["has_video"], body["result"]) == ("queued", False, None)
    stored = app.state.try_store.find_input(uuid.UUID(body["id"]))
    assert stored is not None and stored.suffix == ".mp4"
    assert (await client.get(f"/public/try/jobs/{body['id']}")).json()["status"] == "queued"


@pytest.mark.parametrize(
    ("body", "headers", "code"),
    [
        (b"%PDF-1.7 not a video at all", VIDEO, 415),  # video type, wrong bytes
        (mp4(30.0), {"Content-Type": "application/pdf"}, 415),
        (mp4(30.0), {"Content-Type": "text/plain"}, 415),
        (b"", VIDEO, 415),
        (mp4(90.0), VIDEO, 422),  # longer than 60 s
    ],
)
async def test_E_12_bad_uploads_are_rejected_before_processing_and_leave_nothing(
    sandbox: tuple[FastAPI, httpx.AsyncClient], body: bytes, headers: dict[str, str], code: int
) -> None:
    app, client = sandbox
    response = await upload(client, body, headers=headers)
    assert response.status_code == code, response.text
    assert "detail" in response.json()
    root = app.state.try_store.root
    assert not root.exists() or not any(root.iterdir())  # nothing stored, nothing queued


async def test_E_12_an_oversized_upload_is_refused_early_and_while_streaming(
    tmp_path: Path,
) -> None:
    app = make_app(tmp_path, try_max_mb=1)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            big = mp4(10.0) + b"\0" * (1024 * 1024)
            declared = await upload(client, big)  # Content-Length says it is too large
            assert declared.status_code == 413

            async def chunks() -> AsyncIterator[bytes]:
                yield mp4(10.0)
                for _ in range(20):
                    yield b"\0" * (100 * 1024)  # no Content-Length: stopped while streaming

            streamed = await client.post("/public/try/jobs", content=chunks(), headers=VIDEO)
            assert streamed.status_code == 413
    assert not any(app.state.try_store.root.iterdir())


async def test_FR_CIT_004_uploads_are_rate_limited_per_ip(tmp_path: Path) -> None:
    app = make_app(tmp_path, try_jobs_per_minute=2)
    async with app.router.lifespan_context(app):
        await app.state.redis.delete("ratelimit:try-job:127.0.0.1")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            codes = [(await upload(client, mp4(5.0))).status_code for _ in range(3)]
        await app.state.redis.delete("ratelimit:try-job:127.0.0.1")
    assert codes == [202, 202, 429]


# ---------------------------------------------------------------- worker flow


async def test_the_worker_claims_analyses_and_the_result_appears_without_touching_incidents(
    sandbox: tuple[FastAPI, httpx.AsyncClient], session: AsyncSession
) -> None:
    app, client = sandbox
    before = await session.scalar(select(func.count()).select_from(Incident))
    job_id = (await upload(client, mp4(30.0))).json()["id"]

    assert (await client.post("/internal/try/claim")).status_code == 401  # needs the token
    claimed = await client.post("/internal/try/claim", headers=INTERNAL)
    assert claimed.status_code == 200 and claimed.json()["id"] == job_id
    file = await client.get(f"/internal/try/jobs/{job_id}/file", headers=INTERNAL)
    assert file.content == mp4(30.0)

    progress = {"stage": "scan", "progress": 0.4}
    assert (
        await client.post(f"/internal/try/jobs/{job_id}/progress", json=progress, headers=INTERNAL)
    ).status_code == 204
    mid = (await client.get(f"/public/try/jobs/{job_id}")).json()
    assert (mid["status"], mid["stage"], mid["progress"]) == ("processing", "scan", 0.4)

    video = b"\0\0\0\x18ftypisom" + b"annotated" * 100
    put = await client.put(f"/internal/try/jobs/{job_id}/video", content=video, headers=INTERNAL)
    assert put.status_code == 204
    posted = await client.post(
        f"/internal/try/jobs/{job_id}/result",
        content=result().model_dump_json(),
        headers={**INTERNAL, "Content-Type": "application/json"},
    )
    assert posted.status_code == 204

    done = (await client.get(f"/public/try/jobs/{job_id}")).json()
    assert (done["status"], done["has_video"], done["progress"]) == ("done", True, 1.0)
    assert done["result"]["sandbox_incident"]["type"] == "possible_incident"
    assert done["result"]["refine"]["collision_visible"] == "yes"
    served = await client.get(f"/public/try/jobs/{job_id}/video")
    assert (served.status_code, served.content) == (200, video)

    # Sandbox incidents live in the job row only: the operator queue never sees them.
    after = await session.scalar(select(func.count()).select_from(Incident))
    assert after == before
    assert app.state.try_store.find_input(uuid.UUID(job_id)) is not None


async def test_two_workers_never_claim_the_same_job(
    sandbox: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    _, client = sandbox
    ids = {(await upload(client, mp4(5.0))).json()["id"] for _ in range(2)}
    claims = await asyncio.gather(
        *(client.post("/internal/try/claim", headers=INTERNAL) for _ in range(2))
    )
    claimed = {c.json()["id"] for c in claims if c.status_code == 200}
    assert len(claimed) == len([c for c in claims if c.status_code == 200])
    assert claimed <= ids
    again = await client.post("/internal/try/claim", headers=INTERNAL)
    assert again.status_code in (200, 204)


async def test_a_rejected_or_failed_job_says_why(
    sandbox: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    _, client = sandbox
    job_id = (await upload(client, mp4(5.0))).json()["id"]
    await client.post("/internal/try/claim", headers=INTERNAL)
    failed = await client.post(
        f"/internal/try/jobs/{job_id}/fail",
        json={"error": "No video stream in the file", "rejected": True},
        headers=INTERNAL,
    )
    assert failed.status_code == 204
    body = (await client.get(f"/public/try/jobs/{job_id}")).json()
    assert (body["status"], body["error"]) == ("rejected", "No video stream in the file")
    again = await client.post(
        f"/internal/try/jobs/{job_id}/progress",
        json={"stage": "x", "progress": 0.1},
        headers=INTERNAL,
    )
    assert again.status_code == 409  # a final job cannot be moved again


async def test_the_page_reads_whether_the_ai_is_available(
    sandbox: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    _, client = sandbox
    for available in (True, False):
        reported = await client.post(
            "/internal/try/status", json={"ai_available": available}, headers=INTERNAL
        )
        assert reported.status_code == 204
        status = (await client.get("/public/try/status")).json()
        assert status["ai_available"] is available
        assert (status["max_seconds"], status["max_mb"]) == (60, 100)


async def test_progress_is_streamed_until_the_job_is_final(
    sandbox: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    app, client = sandbox
    job_id = (await upload(client, mp4(5.0))).json()["id"]
    frames: list[str] = []

    async def collect() -> None:
        async for frame in job_events(app.state.session_factory, uuid.UUID(job_id), poll_s=0.02):
            frames.append(frame)

    reader = asyncio.create_task(collect())
    await asyncio.sleep(0.1)
    await client.post("/internal/try/claim", headers=INTERNAL)
    await client.post(
        f"/internal/try/jobs/{job_id}/progress",
        json={"stage": "scan", "progress": 0.5},
        headers=INTERNAL,
    )
    await asyncio.sleep(0.1)
    await client.post(
        f"/internal/try/jobs/{job_id}/result", content=result().model_dump_json(),
        headers={**INTERNAL, "Content-Type": "application/json"},
    )  # fmt: skip
    await asyncio.wait_for(reader, 5)
    states = [json.loads(f.split("data: ", 1)[1])["status"] for f in frames]
    assert states[0] == "queued" and states[-1] == "done" and "processing" in states
    assert all(f.startswith("event: job\n") for f in frames)


# ---------------------------------------------------------------- deletion after the TTL


async def test_AC_CIT_002_1_upload_and_outputs_are_deleted_after_the_ttl(tmp_path: Path) -> None:
    app = make_app(tmp_path, try_ttl_s=1)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            job_id = (await upload(client, mp4(30.0))).json()["id"]
            await client.post("/internal/try/claim", headers=INTERNAL)
            await client.put(
                f"/internal/try/jobs/{job_id}/video", content=b"video", headers=INTERNAL
            )
            await client.post(
                f"/internal/try/jobs/{job_id}/result", content=result().model_dump_json(),
                headers={**INTERNAL, "Content-Type": "application/json"},
            )  # fmt: skip
            directory = app.state.try_store.job_dir(uuid.UUID(job_id))
            assert directory.is_dir() and (directory / "annotated.mp4").is_file()

            early = await service.purge(
                app.state.session_factory, app.state.try_store, app.state.settings
            )
            assert early["jobs"] == 0 and directory.is_dir()  # not expired yet

            later = service.now() + timedelta(seconds=2)
            purged = await service.purge(
                app.state.session_factory, app.state.try_store, app.state.settings, at=later
            )
            assert purged["jobs"] >= 1
            assert not directory.exists()  # upload and annotated video are gone
            assert (await client.get(f"/public/try/jobs/{job_id}")).status_code == 404
            assert (await client.get(f"/public/try/jobs/{job_id}/video")).status_code == 404


async def test_a_job_nobody_is_working_on_fails_instead_of_hanging(tmp_path: Path) -> None:
    app = make_app(tmp_path, try_job_timeout_s=30)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            job_id = (await upload(client, mp4(5.0))).json()["id"]
            await client.post("/internal/try/claim", headers=INTERNAL)
            await service.purge(
                app.state.session_factory, app.state.try_store, app.state.settings,
                at=service.now() + timedelta(seconds=60),
            )  # fmt: skip
            body = (await client.get(f"/public/try/jobs/{job_id}")).json()
    assert (body["status"], body["error"]) == ("failed", "The analysis timed out")


async def test_the_owner_can_delete_an_upload_at_once(
    sandbox: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    app, client = sandbox
    job_id = (await upload(client, mp4(5.0))).json()["id"]
    assert (await client.delete(f"/public/try/jobs/{job_id}")).status_code == 204
    assert (await client.get(f"/public/try/jobs/{job_id}")).status_code == 404
    assert not app.state.try_store.job_dir(uuid.UUID(job_id)).exists()


# ---------------------------------------------------------------- live phone sessions


async def test_a_phone_session_appears_on_the_wall_as_a_live_demo_and_ends_when_it_leaves(
    sandbox: tuple[FastAPI, httpx.AsyncClient], session: AsyncSession, make_user: MakeUser
) -> None:
    _app, client = sandbox
    created = await client.post("/public/try/sessions")
    assert created.status_code == 201
    live = created.json()
    assert live["path"].startswith("live/") and live["whip_url"].endswith(f"{live['path']}/whip")

    refs = (await client.get("/internal/try/sessions", headers=INTERNAL)).json()
    assert refs == [{"id": live["id"], "path": live["path"]}]

    operator = await login(client, await make_user(session, role="operator"))
    cameras = (await client.get("/cameras", headers=operator)).json()
    demo = next(c for c in cameras if c["live_demo"])
    assert demo["id"] == "live-" + live["path"].removeprefix("live/")
    # The phone has not published yet: never shown as live before the worker saw a frame.
    assert demo["stream"]["path"] == live["path"] and demo["status"] == "unknown"
    assert all(not c["live_demo"] for c in cameras if c is not demo)

    event = {
        "at": service.now().isoformat(), "kind": "ai_check", "label": "no collision",
        "source": "Qwen/Qwen3-VL-8B-Instruct-FP8",
    }  # fmt: skip
    posted = await client.post(
        f"/internal/try/sessions/{live['id']}/events", json=event, headers=INTERNAL
    )
    assert posted.status_code == 204
    state = (await client.get(f"/public/try/sessions/{live['id']}")).json()
    assert [e["label"] for e in state["events"]] == ["no collision"]
    cameras = (await client.get("/cameras", headers=operator)).json()
    assert next(c for c in cameras if c["live_demo"])["status"] == "online"

    assert (await client.post(f"/public/try/sessions/{live['id']}/ping")).status_code == 204
    assert (await client.delete(f"/public/try/sessions/{live['id']}")).status_code == 204
    assert (await client.get(f"/public/try/sessions/{live['id']}")).status_code == 404
    cameras = (await client.get("/cameras", headers=operator)).json()
    assert not any(c["live_demo"] and c["stream"]["path"] == live["path"] for c in cameras)


async def test_a_session_whose_phone_stops_pinging_is_ended_and_deleted(tmp_path: Path) -> None:
    app = make_app(tmp_path, try_session_idle_s=30)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            live = (await client.post("/public/try/sessions")).json()
            keep = (await client.post("/public/try/sessions")).json()
            soon = service.now() + timedelta(seconds=20)
            await service.purge(
                app.state.session_factory, app.state.try_store, app.state.settings, at=soon
            )
            assert (await client.get(f"/public/try/sessions/{live['id']}")).status_code == 200
            late = service.now() + timedelta(seconds=45)
            await client.post(f"/public/try/sessions/{keep['id']}/ping")
            purged = await service.purge(
                app.state.session_factory, app.state.try_store, app.state.settings, at=late
            )
            assert purged["sessions"] >= 1
            assert (await client.get(f"/public/try/sessions/{live['id']}")).status_code == 404
            await client.delete(f"/public/try/sessions/{keep['id']}")


async def test_live_sessions_are_rate_limited_per_ip(tmp_path: Path) -> None:
    app = make_app(tmp_path, try_sessions_per_minute=1)
    async with app.router.lifespan_context(app):
        await app.state.redis.delete("ratelimit:try-session:127.0.0.1")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            first = await client.post("/public/try/sessions")
            second = await client.post("/public/try/sessions")
            await client.delete(f"/public/try/sessions/{first.json()['id']}")
        await app.state.redis.delete("ratelimit:try-session:127.0.0.1")
    assert (first.status_code, second.status_code) == (201, 429)


async def test_the_sandbox_tables_never_reference_incidents(session: AsyncSession) -> None:
    from sqlalchemy import text

    rows = await session.execute(
        text(
            "SELECT conrelid::regclass::text FROM pg_constraint "
            "WHERE contype='f' AND conrelid::regclass::text IN ('try_jobs','try_sessions')"
        )
    )
    assert rows.all() == []  # no foreign key to any real table
    assert TryJob.__table__.foreign_keys == set()
    assert TrySession.__table__.foreign_keys == set()


async def test_abuse_caps_open_jobs_and_live_sessions_globally(tmp_path: Path) -> None:
    """Public and anonymous: beyond the caps the sandbox answers 503 instead of filling the
    disk, the GPU worker and the operator wall."""
    app = make_app(tmp_path, try_max_open_jobs=1, try_max_live_sessions=1)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            assert (await upload(client, mp4(5.0))).status_code == 202
            assert (await upload(client, mp4(5.0))).status_code == 503
            assert (await client.post("/public/try/sessions")).status_code == 201
            assert (await client.post("/public/try/sessions")).status_code == 503


async def test_a_progress_stream_ends_after_its_lifetime(
    sandbox: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Idle public SSE connections cannot hold the database pool: the stream ends and the
    browser reconnects."""
    app, client = sandbox
    job_id = (await upload(client, mp4(5.0))).json()["id"]
    frames = [
        f
        async for f in job_events(
            app.state.session_factory, uuid.UUID(job_id), poll_s=0.02, max_s=0.2
        )
    ]
    assert frames[0].startswith("event: job\n")
    assert frames[-1].startswith("retry:")
