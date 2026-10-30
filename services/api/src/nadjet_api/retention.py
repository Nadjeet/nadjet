"""Retention (FR-SEC-005, NFR-PRIV-001): purge evidence older than ``NADJET_RETENTION_DAYS``.

Only the ``evidence`` table and its files are touched; the incident, its signed event chain and
the audit log are kept. Sandbox uploads (``tryit``) expire after an hour on their own schedule.
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nadjet_api.audit import AuditTarget, audit
from nadjet_api.config import Settings
from nadjet_api.incidents.models import Evidence
from nadjet_api.incidents.store import EvidenceStore

log = logging.getLogger(__name__)


async def purge_expired(
    factory: async_sessionmaker[AsyncSession],
    store: EvidenceStore,
    settings: Settings,
    at: datetime | None = None,
) -> int:
    """Delete evidence (file, then row) created before ``at - retention``; audit what went."""
    cutoff = (at or datetime.now(UTC)) - timedelta(days=settings.retention_days)
    async with factory() as db:
        expired = list(
            await db.execute(select(Evidence.id, Evidence.path).where(Evidence.created_at < cutoff))
        )
        removed = []
        for evidence_id, path in expired:
            try:
                await store.delete(path)
            except Exception:
                # Keep the row so the next run retries; one bad file must not stop the purge.
                log.exception("retention: could not delete %s", path)
                continue
            removed.append(evidence_id)
        if not removed:
            return 0
        await db.execute(delete(Evidence).where(Evidence.id.in_(removed)))
        await audit(
            db,
            None,
            "retention.purge",
            AuditTarget("evidence", "expired"),
            {
                "deleted": len(removed),
                "retention_days": settings.retention_days,
                "cutoff": cutoff.isoformat(),
            },
        )
        await db.commit()
    log.info("retention: purged %d evidence files older than %s", len(removed), cutoff)
    return len(removed)


async def retention_loop(app_state: object, interval_s: float, stop: asyncio.Event) -> None:
    """Background task of the API: run the purge on a schedule until ``stop`` is set."""
    while not stop.is_set():
        with contextlib.suppress(Exception):
            await purge_expired(
                getattr(app_state, "session_factory"),  # noqa: B009
                getattr(app_state, "store"),  # noqa: B009
                getattr(app_state, "settings"),  # noqa: B009
            )
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval_s)
