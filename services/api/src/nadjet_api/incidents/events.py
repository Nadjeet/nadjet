"""Real-time fan-out: Redis Pub/Sub to Server-Sent Events, filtered by role scope (TD-12)."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from redis.asyncio import Redis

from nadjet_api.auth.roles import Scope
from nadjet_api.incidents.service import Change

CHANNEL = "incidents.events"
HEARTBEAT_S = 15.0
log = logging.getLogger(__name__)


async def publish(redis: Redis, change: Change) -> None:
    """Announce a committed change. Best effort: clients refetch, the DB stays the truth."""
    message = {
        "type": change.type,
        "incident_id": str(change.incident_id),
        "version": change.version,
        "agencies": list(change.agencies),
        "facilities": list(change.facilities),
    }
    try:
        await redis.publish(CHANNEL, json.dumps(message))
    except Exception:
        log.exception("failed to publish %s for %s", change.type, change.incident_id)


async def publish_facility(redis: Redis, facility_id: str, ready_state: str) -> None:
    """Announce a hospital Ready/Divert change to the operators and that hospital's users.

    Best effort: clients refetch, the DB stays the truth.
    """
    message = {
        "type": "facility.updated",
        "facility_id": facility_id,
        "ready_state": ready_state,
        "agencies": [],
        "facilities": [facility_id],
    }
    try:
        await redis.publish(CHANNEL, json.dumps(message))
    except Exception:
        log.exception("failed to publish facility update for %s", facility_id)


def visible_to(scope: Scope, message: dict[str, object]) -> bool:
    if scope.unrestricted:
        return True
    if scope.agency:
        return scope.agency.value in list(message.get("agencies", []))  # type: ignore[call-overload]
    return scope.facility_id in list(message.get("facilities", []))  # type: ignore[call-overload]


def frame(message: dict[str, object]) -> str:
    if "camera_id" in message:  # camera_fault / camera_recovered (cameras/health.py)
        camera = json.dumps({"camera_id": message["camera_id"], "status": message["status"]})
        return f"event: {message['type']}\ndata: {camera}\n\n"
    if "facility_id" in message:  # facility.updated (hospital Ready/Divert)
        facility = json.dumps(
            {"facility_id": message["facility_id"], "ready_state": message["ready_state"]}
        )
        return f"event: {message['type']}\ndata: {facility}\n\n"
    data = json.dumps({"incident_id": message["incident_id"], "version": message["version"]})
    return f"event: {message['type']}\ndata: {data}\n\n"


async def stream(
    redis: Redis, scope: Scope, heartbeat_s: float = HEARTBEAT_S
) -> AsyncIterator[str]:
    """SSE frames for the incidents ``scope`` may see, plus a comment heartbeat."""
    pubsub = redis.pubsub()
    await pubsub.subscribe(CHANNEL)
    try:
        yield ": connected\n\n"
        loop = asyncio.get_running_loop()
        last_write = loop.time()
        while True:
            # Heartbeat on elapsed time, so filtered-out traffic cannot starve it.
            wait = max(0.0, heartbeat_s - (loop.time() - last_write))
            raw = await pubsub.get_message(ignore_subscribe_messages=True, timeout=wait)
            if raw is not None:
                message = json.loads(raw["data"])
                if visible_to(scope, message):
                    yield frame(message)
                    last_write = loop.time()
                    continue
            if loop.time() - last_write >= heartbeat_s:
                yield ": heartbeat\n\n"
                last_write = loop.time()
    except asyncio.CancelledError:
        raise
    finally:
        await pubsub.aclose()  # type: ignore[no-untyped-call]
