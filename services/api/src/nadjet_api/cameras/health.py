"""Camera health ingestion: Redis snapshot, fault state machine on ``cameras.status``.

Workers push a report every 5 s (``POST /internal/camera-health``). The latest report lives in
Redis with a short TTL; a camera whose worker stops reporting is shown as stale, never silently
healthy. A fault or recovery changes ``cameras.status`` once and is announced on the live
channel (``camera_fault`` / ``camera_recovered``) for the operator console (FR-CAM-005).
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.cameras.models import Camera
from nadjet_shared.health import CameraHealthReport

log = logging.getLogger(__name__)

HEALTH_TTL_S = 60
STALE_AFTER_S = 15.0  # three missed 5 s reports
EVENTS_CHANNEL = "incidents.events"  # shared live channel (see incidents/events.py)

Transition = Literal["camera_fault", "camera_recovered"]


def health_key(camera_id: str) -> str:
    return f"camera:health:{camera_id}"


def next_status(current: str, report: CameraHealthReport) -> tuple[str, Transition | None]:
    """New ``cameras.status`` after a report, and the live event to announce, if any."""
    if report.fault:
        return "degraded", ("camera_fault" if current != "degraded" else None)
    if current == "degraded":
        return "online", "camera_recovered"
    if current in ("unknown", "offline") and report.connected:
        return "online", None
    return current, None


def is_stale(
    report: CameraHealthReport, now: datetime, stale_after_s: float = STALE_AFTER_S
) -> bool:
    return (now - report.at).total_seconds() > stale_after_s


@dataclass(frozen=True)
class Applied:
    status: str
    transition: Transition | None


async def store_report(redis: Redis, report: CameraHealthReport) -> None:
    await redis.set(health_key(report.camera_id), report.model_dump_json(), ex=HEALTH_TTL_S)


async def load_reports(redis: Redis, camera_ids: list[str]) -> dict[str, CameraHealthReport]:
    if not camera_ids:
        return {}
    raws = await redis.mget([health_key(c) for c in camera_ids])
    reports: dict[str, CameraHealthReport] = {}
    for camera_id, raw in zip(camera_ids, raws, strict=True):
        if raw is None:
            continue
        try:
            reports[camera_id] = CameraHealthReport.model_validate_json(raw)
        except ValueError:
            log.warning("discarding malformed health report for %s", camera_id)
    return reports


async def apply_report(
    session: AsyncSession, camera: Camera, report: CameraHealthReport
) -> Applied:
    """Update ``cameras.status`` from a report (the caller commits)."""
    status, transition = next_status(camera.status, report)
    if status != camera.status:
        await session.execute(
            update(Camera)
            .where(Camera.id == camera.id)
            .values(status=status, updated_at=datetime.now(UTC))
        )
        camera.status = status
    return Applied(status=status, transition=transition)


async def announce(redis: Redis, camera_id: str, transition: Transition, status: str) -> None:
    """Best effort live event; clients refetch ``/system/cameras``."""
    message = {"type": transition, "camera_id": camera_id, "status": status}
    try:
        await redis.publish(EVENTS_CHANNEL, json.dumps(message))
    except Exception:
        log.exception("failed to publish %s for %s", transition, camera_id)
