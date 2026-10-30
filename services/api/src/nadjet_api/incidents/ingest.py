"""Candidate ingestion through a Redis Stream consumer group (NFR-REL-002: no candidate lost).

The API only appends to the stream (``enqueue``). The ``consume`` worker persists each entry and
acknowledges it after the database commit; entries left pending by a crash are re-claimed.
Persisting is idempotent on the candidate's key, so redelivery never duplicates an incident.
"""

import asyncio
import contextlib
import logging
import socket
from typing import Any

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nadjet_api.incidents.events import publish
from nadjet_api.incidents.service import ingest_candidate
from nadjet_api.incidents.signing import ChainSigner
from nadjet_shared.events import IncidentCandidate

STREAM = "incidents.candidates"
DEAD_LETTER = "incidents.candidates.dead"
GROUP = "api"
BATCH = 10
log = logging.getLogger(__name__)


async def enqueue(redis: Redis, candidate: IncidentCandidate, key: str) -> str:
    """Append a candidate to the stream; returns the stream entry id."""
    entry_id = await redis.xadd(STREAM, {"key": key, "candidate": candidate.model_dump_json()})
    return str(entry_id)


class CandidateConsumer:
    def __init__(
        self,
        redis: Redis,
        session_factory: async_sessionmaker[AsyncSession],
        signer: ChainSigner,
        *,
        name: str | None = None,
        claim_idle_ms: int = 30_000,
        max_deliveries: int = 10,
    ) -> None:
        self.redis = redis
        self.session_factory = session_factory
        self.signer = signer
        self.name = name or f"{socket.gethostname()}-{id(self):x}"
        self.claim_idle_ms = claim_idle_ms
        self.max_deliveries = max_deliveries

    async def setup(self) -> None:
        with contextlib.suppress(ResponseError):  # BUSYGROUP: group already exists
            await self.redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)

    async def handle(self, entry_id: str, fields: dict[str, Any]) -> None:
        """Persist one entry, then acknowledge it. Failures leave it pending for retry."""
        try:
            candidate = IncidentCandidate.model_validate_json(fields["candidate"])
            key = fields["key"]
        except (KeyError, ValidationError):
            log.exception("dead-lettering malformed candidate %s", entry_id)
            await self._dead_letter(entry_id, fields)
            return
        try:
            async with self.session_factory() as session:
                result = await ingest_candidate(session, self.signer, candidate, key)
                await session.commit()
        except Exception:
            if await self._deliveries(entry_id) >= self.max_deliveries:
                log.exception("dead-lettering candidate %s after repeated failures", entry_id)
                await self._dead_letter(entry_id, fields)
            else:
                log.exception("failed to persist candidate %s; will retry", entry_id)
            return
        await self.redis.xack(STREAM, GROUP, entry_id)  # only after the DB commit
        for change in result.changes:
            await publish(self.redis, change)

    async def _dead_letter(self, entry_id: str, fields: dict[str, Any]) -> None:
        await self.redis.xadd(
            DEAD_LETTER, {"entry_id": entry_id, **{k: str(v) for k, v in fields.items()}}
        )
        await self.redis.xack(STREAM, GROUP, entry_id)

    async def _deliveries(self, entry_id: str) -> int:
        pending: Any = await self.redis.xpending_range(STREAM, GROUP, entry_id, entry_id, 1)
        return int(pending[0]["times_delivered"]) if pending else 0

    async def _claim_stale(self) -> list[tuple[str, dict[str, Any]]]:
        claimed: list[tuple[str, dict[str, Any]]] = []
        cursor = "0-0"
        while True:
            result: Any = await self.redis.xautoclaim(
                STREAM, GROUP, self.name, self.claim_idle_ms, start_id=cursor, count=BATCH
            )
            cursor, messages = str(result[0]), result[1]
            claimed.extend((str(i), f) for i, f in messages if f)
            if cursor == "0-0":
                return claimed

    async def poll_once(self, block_ms: int = 1000) -> int:
        """Process stale pending entries, then new ones; returns the number handled."""
        entries = await self._claim_stale()
        response: Any = await self.redis.xreadgroup(
            GROUP, self.name, {STREAM: ">"}, count=BATCH, block=block_ms
        )
        for _stream, messages in response or []:
            entries.extend((str(i), f) for i, f in messages)
        for entry_id, fields in entries:
            await self.handle(entry_id, fields)
        return len(entries)

    async def run(self, stop: asyncio.Event) -> None:
        await self.setup()
        log.info("candidate consumer %s started", self.name)
        while not stop.is_set():
            try:
                await self.poll_once()
            except Exception:  # keep the worker alive (Redis down, NOGROUP after a reset, ...)
                log.exception("consumer poll failed; retrying")
                with contextlib.suppress(Exception):
                    await self.setup()
                await asyncio.sleep(1)
