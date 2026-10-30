"""Write and verify the audit chain: ``hash = sha256(prev_hash || canonical_json(row))``."""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, NamedTuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.audit.models import AuditLog
from nadjet_api.auth.models import User

GENESIS_HASH = "0" * 64
# Serialises writers so the chain has no forks; held until the caller's transaction ends.
_CHAIN_LOCK_KEY = 7_204_001


class AuditTarget(NamedTuple):
    type: str
    id: str


@dataclass(frozen=True)
class ChainStatus:
    ok: bool
    checked: int
    broken_at: int | None = None  # id of the first row that does not verify


def canonical_json(
    *,
    actor_id: uuid.UUID | None,
    action: str,
    target_type: str | None,
    target_id: str | None,
    ip: str | None,
    at: datetime,
    details: dict[str, Any],
) -> str:
    row = {
        "actor_id": str(actor_id) if actor_id else None,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "ip": ip,
        "at": at.astimezone(UTC).isoformat(),
        "details": details,
    }
    return json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def chain_hash(prev_hash: str, canonical: str) -> str:
    return hashlib.sha256((prev_hash + canonical).encode()).hexdigest()


async def audit(
    session: AsyncSession,
    actor: User | None,
    action: str,
    target: AuditTarget | None = None,
    details: dict[str, Any] | None = None,
    *,
    ip: str | None = None,
) -> AuditLog:
    """Append an entry in the caller's transaction (the caller commits).

    Never put secrets in ``details``. If the transaction rolls back, the entry goes with it.
    """
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _CHAIN_LOCK_KEY})
    prev_hash = await session.scalar(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1))
    prev_hash = prev_hash or GENESIS_HASH
    fields: dict[str, Any] = {
        "actor_id": actor.id if actor else None,
        "action": action,
        "target_type": target.type if target else None,
        "target_id": target.id if target else None,
        "ip": ip,
        "at": datetime.now(UTC),
        "details": details or {},
    }
    entry = AuditLog(
        **fields, prev_hash=prev_hash, hash=chain_hash(prev_hash, canonical_json(**fields))
    )
    session.add(entry)
    await session.flush()
    return entry


async def verify_chain(session: AsyncSession) -> ChainStatus:
    """Recompute every hash in order; report the first broken row."""
    prev_hash = GENESIS_HASH
    checked = 0
    result = await session.stream_scalars(select(AuditLog).order_by(AuditLog.id))
    async for row in result:
        canonical = canonical_json(
            actor_id=row.actor_id,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            ip=row.ip,
            at=row.at,
            details=row.details,
        )
        if row.prev_hash != prev_hash or row.hash != chain_hash(prev_hash, canonical):
            return ChainStatus(ok=False, checked=checked, broken_at=row.id)
        prev_hash = row.hash
        checked += 1
    return ChainStatus(ok=True, checked=checked)
