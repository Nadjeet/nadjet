"""``/public/try``: upload a clip or use a phone as a live camera (no login, FR-CIT-002..005).

Public endpoints are rate-limited per IP, accept only what looks like a video of at most
``try_max_mb`` and ``try_max_seconds`` (rejected before processing, PRD E-12) and keep everything
in the sandbox for ``try_ttl_s``.
"""

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Annotated

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse
from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nadjet_api.config import Settings
from nadjet_api.db import get_session
from nadjet_api.incidents.deps import RedisDep
from nadjet_api.ratelimit import rate_limit
from nadjet_api.streams.tokens import encode_stream_token
from nadjet_api.tryit import media, service
from nadjet_api.tryit.models import TryJob, TrySession
from nadjet_shared.tryit import TryJobOut, TrySessionOut, TryStatus

router = APIRouter(prefix="/public/try", tags=["public-try"])

AI_KEY = "try:ai"
AI_TTL_S = 30
DURATION_SLACK_S = 0.5
CHUNK = 256 * 1024
ALLOWED_TYPES = {"video/mp4", "video/quicktime", "video/webm"}


def settings_of(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def store_of(request: Request) -> service.SandboxStore:
    store: service.SandboxStore = request.app.state.try_store
    return store


async def job_limit(request: Request) -> None:
    per_minute = settings_of(request).try_jobs_per_minute
    await rate_limit("try-job", per_minute=per_minute)(request)


async def session_limit(request: Request) -> None:
    per_minute = settings_of(request).try_sessions_per_minute
    await rate_limit("try-session", per_minute=per_minute)(request)


async def events_limit(request: Request) -> None:
    per_minute = settings_of(request).try_events_per_minute
    await rate_limit("try-events", per_minute=per_minute)(request)


async def ai_available(redis: Redis) -> bool:
    return bool(await redis.get(AI_KEY))


@router.get("/status")
async def try_status(request: Request, redis: RedisDep) -> TryStatus:
    """Limits and whether the Brev AI is reachable (the page shows "AI unavailable")."""
    s = settings_of(request)
    return TryStatus(
        ai_available=await ai_available(redis),
        max_seconds=s.try_max_seconds,
        max_mb=s.try_max_mb,
        ttl_s=s.try_ttl_s,
    )


@router.post(
    "/jobs",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(job_limit)],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                kind: {"schema": {"type": "string", "format": "binary"}} for kind in ALLOWED_TYPES
            },
        }
    },
    responses={
        413: {"description": "Too large"},
        415: {"description": "Not a video"},
        422: {"description": "Too long"},
        429: {"description": "Rate limit"},
    },
)
async def create_job(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    filename: Annotated[str, Query(max_length=255)] = "clip",
) -> TryJobOut:
    """Upload the raw video as the request body (``Content-Type: video/*``). The upload stops
    as soon as it is too large; the file is sniffed and, for MP4/MOV, its duration is read."""
    s = settings_of(request)
    limit = s.try_max_mb * 1024 * 1024
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Not a video (MP4, MOV, WebM)")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"Over {s.try_max_mb} MB")

    open_jobs = await db.scalar(
        select(func.count()).select_from(TryJob).where(TryJob.status.notin_(service.FINAL))
    )
    if (open_jobs or 0) >= s.try_max_open_jobs:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Too many analyses running")

    store = store_of(request)
    job_id = uuid.uuid4()
    store.job_dir(job_id).mkdir(parents=True, exist_ok=True)
    size, kind = 0, None
    target: anyio.Path | None = None
    handle: anyio.AsyncFile[bytes] | None = None
    try:
        async for chunk in request.stream():
            if kind is None:
                kind = media.sniff(chunk[:16].ljust(16, b"\0"))
                if kind is None:
                    raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Not a video")
                target = anyio.Path(store.input_path(job_id, kind))
                handle = await target.open("wb")
            size += len(chunk)
            if size > limit:
                raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"Over {s.try_max_mb} MB")
            assert handle is not None
            await handle.write(chunk)
        if kind is None or target is None:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Empty upload")
        assert handle is not None
        await handle.aclose()
        handle = None
        if kind == "mp4":
            duration = await asyncio.to_thread(media.mp4_duration_s, store.input_path(job_id, kind))
            if duration is not None and duration > s.try_max_seconds + DURATION_SLACK_S:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    f"Longer than {s.try_max_seconds} s ({duration:.0f} s)",
                )
        # Inside the try: a failure here must not leave the file behind (no row to purge it).
        job = await service.create_job(db, s, job_id, filename, content_type, size)
    except BaseException:
        if handle is not None:
            await handle.aclose()
        store.remove(job_id)
        raise
    return service.job_out(job)


@router.get("/jobs/{job_id}", responses={404: {"description": "Unknown or expired"}})
async def get_job(
    job_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_session)]
) -> TryJobOut:
    job = await db.get(TryJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return service.job_out(job)


async def job_events(
    factory: async_sessionmaker[AsyncSession],
    job_id: uuid.UUID,
    poll_s: float = 0.5,
    max_s: float = 120.0,
) -> AsyncIterator[str]:
    """SSE frames: one per change of stage or progress, the last one when the job is final.

    Public and unauthenticated: the stream ends after ``max_s`` (the browser's EventSource
    reconnects), so idle connections cannot pile up and hold the database pool.
    """
    last: tuple[str, str, float] | None = None
    deadline = asyncio.get_running_loop().time() + max_s
    while True:
        if asyncio.get_running_loop().time() >= deadline:
            yield "retry: 1000\n\n"
            return
        async with factory() as db:
            job = await db.get(TryJob, job_id)
        if job is None:
            yield "event: gone\ndata: {}\n\n"
            return
        state = (job.status, job.stage, job.progress)
        if state != last:
            last = state
            yield f"event: job\ndata: {service.job_out(job).model_dump_json()}\n\n"
        if job.status in service.FINAL:
            return
        await asyncio.sleep(poll_s)


@router.get(
    "/jobs/{job_id}/events",
    dependencies=[Depends(events_limit)],
    responses={429: {"description": "Rate limit"}},
)
async def stream_job(job_id: uuid.UUID, request: Request) -> StreamingResponse:
    """Progress of a job over SSE (FR-CIT-002)."""
    return StreamingResponse(
        job_events(
            request.app.state.session_factory,
            job_id,
            max_s=settings_of(request).try_events_max_s,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/jobs/{job_id}/video", responses={404: {"description": "No annotated video"}})
async def job_video(
    job_id: uuid.UUID, request: Request, db: Annotated[AsyncSession, Depends(get_session)]
) -> FileResponse:
    job = await db.get(TryJob, job_id)
    path = store_of(request).video_path(job_id)
    if job is None or not job.has_video or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No annotated video")
    return FileResponse(path, media_type="video/mp4", headers={"Cache-Control": "no-store"})


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: uuid.UUID, request: Request, db: Annotated[AsyncSession, Depends(get_session)]
) -> Response:
    """Delete an upload and its outputs now (the owner of the link may do it before the TTL)."""
    await db.execute(delete(TryJob).where(TryJob.id == job_id))
    await db.commit()
    store_of(request).remove(job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------- live phone sessions


@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(session_limit)],
    responses={429: {"description": "Rate limit"}},
)
async def create_session(
    request: Request, db: Annotated[AsyncSession, Depends(get_session)]
) -> TrySessionOut:
    """A temporary live camera: the phone publishes to ``whip_url`` and pings while it stays."""
    s = settings_of(request)
    active = await db.scalar(select(func.count()).select_from(TrySession))
    if (active or 0) >= s.try_max_live_sessions:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Too many live demos right now")
    session_id = uuid.uuid4()
    row = TrySession(
        id=session_id,
        path=f"live/{session_id.hex[:8]}",
        events=[],
        expires_at=service.now() + timedelta(seconds=s.try_ttl_s),
        last_seen=service.now(),
    )
    db.add(row)
    await db.commit()
    out = service.session_out(row, s)
    # MediaMTX only lets the phone publish to its own path with this token (FR-SEC-007).
    out.publish_token = encode_stream_token(
        str(session_id), "publish", key=s.jwt_key, ttl=timedelta(seconds=s.try_ttl_s), path=row.path
    )
    return out


@router.get("/sessions/{session_id}", responses={404: {"description": "Ended"}})
async def get_session_state(
    session_id: uuid.UUID, request: Request, db: Annotated[AsyncSession, Depends(get_session)]
) -> TrySessionOut:
    row = await db.get(TrySession, session_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session ended")
    return service.session_out(row, settings_of(request))


@router.post(
    "/sessions/{session_id}/ping",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Ended"}},
)
async def ping_session(
    session_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_session)]
) -> Response:
    row = await db.get(TrySession, session_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session ended")
    row.last_seen = service.now()
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def end_session(
    session_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_session)]
) -> Response:
    """The phone leaves: the session and its results are deleted at once."""
    await db.execute(delete(TrySession).where(TrySession.id == session_id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def purge_loop(app_state: object, interval_s: float, stop: asyncio.Event) -> None:
    """Background task of the API: purge the sandbox on a schedule (deleted after 1 h)."""
    while not stop.is_set():
        with contextlib.suppress(Exception):
            await service.purge(
                getattr(app_state, "session_factory"),  # noqa: B009
                getattr(app_state, "try_store"),  # noqa: B009
                getattr(app_state, "settings"),  # noqa: B009
            )
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval_s)
