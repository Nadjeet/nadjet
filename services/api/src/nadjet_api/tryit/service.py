"""Sandbox job and session logic (no HTTP): queue, progress, purge after the TTL (FR-CIT-004)."""

import logging
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nadjet_api.config import Settings
from nadjet_api.tryit.models import TryJob, TrySession
from nadjet_shared.tryit import (
    SessionEvent,
    TryJobOut,
    TryResult,
    TrySessionOut,
)

log = logging.getLogger(__name__)
MAX_SESSION_EVENTS = 20
FINAL = ("done", "failed", "rejected")


def now() -> datetime:
    return datetime.now(UTC)


class SandboxStore:
    """One directory per job under the sandbox root; removed as a whole."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def job_dir(self, job_id: uuid.UUID) -> Path:
        return self.root / str(job_id)

    def input_path(self, job_id: uuid.UUID, extension: str) -> Path:
        return self.job_dir(job_id) / f"input.{extension}"

    def video_path(self, job_id: uuid.UUID) -> Path:
        return self.job_dir(job_id) / "annotated.mp4"

    def find_input(self, job_id: uuid.UUID) -> Path | None:
        return next(self.job_dir(job_id).glob("input.*"), None)

    def remove(self, job_id: uuid.UUID) -> None:
        shutil.rmtree(self.job_dir(job_id), ignore_errors=True)


def job_out(job: TryJob) -> TryJobOut:
    return TryJobOut(
        id=str(job.id),
        status=job.status,
        stage=job.stage,
        progress=job.progress,
        error=job.error,
        result=TryResult.model_validate(job.result) if job.result else None,
        has_video=job.has_video,
        expires_at=job.expires_at,
    )


def session_out(session: TrySession, settings: Settings) -> TrySessionOut:
    return TrySessionOut(
        id=str(session.id),
        status="active",
        path=session.path,
        whip_url=settings.whip_url_template.format(path=session.path),
        whep_url=settings.whep_url_template.format(path=session.path),
        expires_at=session.expires_at,
        events=[SessionEvent.model_validate(e) for e in session.events],
    )


async def create_job(
    db: AsyncSession,
    settings: Settings,
    job_id: uuid.UUID,
    filename: str,
    content_type: str,
    size_bytes: int,
) -> TryJob:
    job = TryJob(
        id=job_id,
        filename=filename[:255],
        content_type=content_type[:64],
        size_bytes=size_bytes,
        expires_at=now() + timedelta(seconds=settings.try_ttl_s),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def claim_next(db: AsyncSession) -> TryJob | None:
    """Oldest queued job, marked ``processing``; concurrent workers never get the same one."""
    job = await db.scalar(
        select(TryJob)
        .where(TryJob.status == "queued")
        .order_by(TryJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    job.status, job.stage, job.updated_at = "processing", "starting", now()
    await db.commit()
    return job


async def set_progress(db: AsyncSession, job_id: uuid.UUID, stage: str, progress: float) -> bool:
    result = await db.execute(
        update(TryJob)
        .where(TryJob.id == job_id, TryJob.status == "processing")
        .values(stage=stage, progress=progress, updated_at=now())
    )
    await db.commit()
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def finish(
    db: AsyncSession, job_id: uuid.UUID, *, result: dict[str, Any] | None = None,
    error: str | None = None, rejected: bool = False,
) -> bool:  # fmt: skip
    status = "done" if error is None else ("rejected" if rejected else "failed")
    values: dict[str, Any] = {"status": status, "updated_at": now(), "error": error}
    if status == "done":
        values.update(stage="done", progress=1.0, result=result)
    else:
        values["stage"] = status
    done = await db.execute(
        update(TryJob).where(TryJob.id == job_id, TryJob.status == "processing").values(**values)
    )
    await db.commit()
    return bool(done.rowcount)  # type: ignore[attr-defined]


async def purge(
    factory: async_sessionmaker[AsyncSession],
    store: SandboxStore,
    settings: Settings,
    at: datetime | None = None,
) -> dict[str, int]:
    """Delete expired jobs with their files, end idle sessions, fail jobs nobody is working on."""
    at = at or now()
    async with factory() as db:
        expired = list(await db.scalars(select(TryJob.id).where(TryJob.expires_at <= at)))
        for job_id in expired:
            store.remove(job_id)
        if expired:
            await db.execute(delete(TryJob).where(TryJob.id.in_(expired)))
        stuck = await db.execute(
            update(TryJob)
            .where(
                TryJob.status == "processing",
                TryJob.updated_at <= at - timedelta(seconds=settings.try_job_timeout_s),
            )
            .values(status="failed", stage="failed", error="The analysis timed out", updated_at=at)
        )
        idle = await db.execute(
            delete(TrySession).where(
                (TrySession.expires_at <= at)
                | (TrySession.last_seen <= at - timedelta(seconds=settings.try_session_idle_s))
            )
        )
        await db.commit()
    counts = {
        "jobs": len(expired),
        "stuck": stuck.rowcount,  # type: ignore[attr-defined]
        "sessions": idle.rowcount,  # type: ignore[attr-defined]
    }
    if any(counts.values()):
        log.info("sandbox purge: %s", counts)
    return counts
