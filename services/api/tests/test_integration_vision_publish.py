"""Integration: a rule trigger's candidate and evidence reach the real API (PostGIS, Redis).

Covers FR-VIS-005/006 from the worker side: ``IncidentPublisher`` posts the candidate, the
stream consumer persists it, the clip and keyframes are uploaded by idempotency key, the
incident's evidence is downloadable and ``/incidents/{id}/integrity`` is ``valid`` (TD-16).
"""

import asyncio
import hashlib
import time
import uuid
from fractions import Fraction

import av
import httpx
import numpy as np
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.incidents.ingest import CandidateConsumer
from nadjet_api.incidents.models import Incident, IncidentEvent
from nadjet_shared import TriggerType
from nadjet_shared.catalogue import Camera, GeoPoint
from nadjet_vision.config import VisionSettings
from nadjet_vision.ingest import Packet, StreamInfo
from nadjet_vision.publish import IncidentPublisher, build_candidate, candidate_key
from nadjet_vision.triggers import TriggerEvent

from .conftest import INGEST_TOKEN, MakeUser
from .test_integration_incidents import fresh_spot, login

pytestmark = pytest.mark.integration

FPS = 10
TIME_BASE = 90000


def fresh_wall() -> float:
    """A distinct event time per run: the idempotency key is derived from it."""
    return time.time() + (uuid.uuid4().int % 1_000_000) / 1000


def stream(seconds: int = 22) -> tuple[list[Packet], StreamInfo]:
    codec = av.CodecContext.create("libx264", "w")
    codec.width, codec.height, codec.pix_fmt = 160, 96, "yuv420p"
    codec.time_base = Fraction(1, TIME_BASE)
    codec.framerate = Fraction(FPS, 1)
    codec.gop_size = 20
    codec.options = {"preset": "ultrafast", "bf": "2", "scenecut": "0"}
    codec.open()
    packets: list[av.Packet] = []
    for n in range(seconds * FPS):
        image = np.full((96, 160, 3), (n * 3) % 255, dtype=np.uint8)
        frame = av.VideoFrame.from_ndarray(image, format="bgr24").reformat(format="yuv420p")
        frame.pts = n * TIME_BASE // FPS
        packets.extend(codec.encode(frame))
    packets.extend(codec.encode(None))
    out = [
        Packet(float(p.pts / TIME_BASE), bool(p.is_keyframe), bytes(p), float(p.dts / TIME_BASE))
        for p in packets
        if p.pts is not None and p.dts is not None
    ]
    return out, StreamInfo("h264", 160, 96, bytes(codec.extradata or b""), TIME_BASE)


def camera_at(lat: float, lon: float) -> Camera:
    return Camera(
        id="cam-it-vision",
        name="IT camera",
        video="x.mp4",
        clip_id="demo-crash-01",
        geo=GeoPoint(lat=lat, lon=lon),
        road="A1",
        pk_km=42,
        wilaya="Boumerdès",
    )


def crash_event(peak_wall: float) -> TriggerEvent:
    return TriggerEvent(
        trigger=TriggerType.COLLISION_CANDIDATE,
        t_start=14.0,
        t_peak=14.0,
        t_fire=18.0,
        evidence_t=14.0,
        track_ids=(1, 2),
        signals={"vehicle_count": 2.0, "overlap_iou": 0.2, "stopped_in_lane": 1.0},
        peak_wall=peak_wall,
        fire_wall=peak_wall + 4.0,
    )


async def consume_until(app: FastAPI, done: asyncio.Event) -> None:
    consumer = CandidateConsumer(app.state.redis, app.state.session_factory, app.state.signer)
    await consumer.setup()
    while not done.is_set():
        await consumer.poll_once(block_ms=100)


def worker_publisher(app: FastAPI) -> IncidentPublisher:
    return IncidentPublisher(
        VisionSettings(ingest_token=SecretStr(INGEST_TOKEN)),
        asyncio.get_running_loop(),
        transport=httpx.ASGITransport(app=app),
        retry_delays_s=(0.1, 0.2),
        evidence_retry_delays_s=(0.2, 0.2, 0.4, 0.4, 0.8, 0.8, 1.0, 1.0, 2.0, 2.0),
    )


async def test_candidate_and_evidence_from_the_worker_make_a_valid_incident(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    lat, lon = fresh_spot()
    event = crash_event(fresh_wall())
    key = candidate_key("cam-it-vision", event)
    packets, info = stream()
    sink = worker_publisher(app)

    done = asyncio.Event()
    consumer = asyncio.create_task(consume_until(app, done))
    # The evidence is submitted together with the candidate: it must wait for the incident.
    sink.publish_candidate(build_candidate(camera_at(lat, lon), event), key)
    sink.submit_evidence(key, event, packets, info)
    await sink.aclose(timeout_s=60)
    done.set()
    await consumer

    assert (sink.stats.candidates_sent, sink.stats.candidates_failed) == (1, 0)
    assert sink.stats.evidence_sent == 7
    assert (sink.stats.evidence_failed, sink.stats.hash_mismatches) == (0, 0)

    incident_id = await session.scalar(
        select(IncidentEvent.incident_id).where(IncidentEvent.idempotency_key == key)
    )
    assert incident_id is not None
    incident = await session.get(Incident, incident_id, populate_existing=True)
    assert incident is not None
    assert incident.ai_status == "probable"  # rules alone: verifier unavailable, never confirmed
    assert incident.camera_id == "cam-it-vision"

    operator = await login(client, await make_user(session, role="operator"))
    auditor = await login(client, await make_user(session, role="auditor"))
    detail = (await client.get(f"/incidents/{incident_id}", headers=operator)).json()
    evidence = detail["evidence"]
    assert sorted(e["kind"] for e in evidence) == ["clip"] + ["keyframe"] * 6
    clip = next(e for e in evidence if e["kind"] == "clip")
    assert clip["content_type"] == "video/mp4"
    assert clip["start_ts"] and clip["end_ts"]

    download = await client.get(f"/incidents/{incident_id}/evidence/{clip['id']}", headers=operator)
    assert download.status_code == 200
    assert download.content[4:8] == b"ftyp"
    assert hashlib.sha256(download.content).hexdigest() == clip["sha256"]

    integrity = (await client.get(f"/incidents/{incident_id}/integrity", headers=auditor)).json()
    assert (integrity["status"], integrity["files_checked"], integrity["failures"]) == (
        "valid",
        7,
        [],
    )


async def test_resending_the_same_event_makes_one_incident(
    app: FastAPI, session: AsyncSession
) -> None:
    """A retried post re-sends the event under the same key: one incident (FR-VIS-010)."""
    lat, lon = fresh_spot()
    event = crash_event(fresh_wall())
    key = candidate_key("cam-it-vision", event)
    candidate = build_candidate(camera_at(lat, lon), event)
    sink = worker_publisher(app)
    done = asyncio.Event()
    consumer = asyncio.create_task(consume_until(app, done))
    for _ in range(3):
        sink.publish_candidate(candidate, key)
    await sink.aclose(timeout_s=30)
    await asyncio.sleep(0.5)
    done.set()
    await consumer

    count = await session.scalar(
        select(func.count()).select_from(IncidentEvent).where(IncidentEvent.idempotency_key == key)
    )
    assert count == 1
