"""Service-to-service endpoints of the try-it worker (``/internal/try``, ingest token)."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.db import get_session
from nadjet_api.incidents.deps import RedisDep, require_ingest_token
from nadjet_api.tryit import service
from nadjet_api.tryit.models import TryJob, TrySession
from nadjet_api.tryit.routes import AI_KEY, AI_TTL_S, settings_of, store_of
from nadjet_shared.tryit import (
    SessionEvent,
    TryAiReport,
    TryJobClaim,
    TryJobFailure,
    TryProgress,
    TryResult,
    TrySessionRef,
)

router = APIRouter(
    prefix="/internal/try", tags=["internal"], dependencies=[Depends(require_ingest_token)]
)
DbDep = Annotated[AsyncSession, Depends(get_session)]
CHUNK = 256 * 1024


@router.post(
    "/claim", response_model=TryJobClaim, responses={204: {"description": "Nothing queued"}}
)
async def claim(db: DbDep) -> Any:
    job = await service.claim_next(db)
    if job is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return TryJobClaim(id=str(job.id), filename=job.filename)


@router.get("/jobs/{job_id}/file", responses={404: {"description": "Gone"}})
async def job_file(job_id: uuid.UUID, request: Request) -> FileResponse:
    path = store_of(request).find_input(job_id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload gone")
    return FileResponse(path)


@router.post(
    "/jobs/{job_id}/progress",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={409: {"description": "Not processing"}},
)
async def progress(job_id: uuid.UUID, body: TryProgress, db: DbDep) -> Response:
    if not await service.set_progress(db, job_id, body.stage, body.progress):
        raise HTTPException(status.HTTP_409_CONFLICT, "Job is not processing")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _chunks(request: Request) -> AsyncIterator[bytes]:
    async for chunk in request.stream():
        yield chunk


@router.put(
    "/jobs/{job_id}/video",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Unknown job"}, 413: {"description": "Too large"}},
)
async def put_video(job_id: uuid.UUID, request: Request, db: DbDep) -> Response:
    """Store the annotated video (raw MP4 body)."""
    job = await db.get(TryJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    limit = settings_of(request).try_max_mb * 1024 * 1024
    path = store_of(request).video_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    async with await anyio.Path(path).open("wb") as handle:
        async for chunk in _chunks(request):
            size += len(chunk)
            if size > limit:
                raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Video too large")
            await handle.write(chunk)
    job.has_video = True
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/jobs/{job_id}/result",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={409: {"description": "Not processing"}},
)
async def post_result(job_id: uuid.UUID, body: TryResult, db: DbDep) -> Response:
    if not await service.finish(db, job_id, result=body.model_dump(mode="json")):
        raise HTTPException(status.HTTP_409_CONFLICT, "Job is not processing")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/jobs/{job_id}/fail",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={409: {"description": "Not processing"}},
)
async def post_failure(job_id: uuid.UUID, body: TryJobFailure, db: DbDep) -> Response:
    if not await service.finish(db, job_id, error=body.error, rejected=body.rejected):
        raise HTTPException(status.HTTP_409_CONFLICT, "Job is not processing")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions")
async def active_sessions(db: DbDep) -> list[TrySessionRef]:
    """Live phone sessions the worker should be attached to."""
    rows = await db.scalars(select(TrySession).order_by(TrySession.created_at))
    return [TrySessionRef(id=str(r.id), path=r.path) for r in rows]


@router.post(
    "/sessions/{session_id}/events",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Session ended"}},
)
async def session_event(session_id: uuid.UUID, body: SessionEvent, db: DbDep) -> Response:
    row = await db.get(TrySession, session_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session ended")
    row.events = [*row.events, body.model_dump(mode="json")][-service.MAX_SESSION_EVENTS :]
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/status", status_code=status.HTTP_204_NO_CONTENT)
async def report_status(body: TryAiReport, redis: RedisDep) -> Response:
    """The worker reports whether the Brev AI answers; the flag expires if it stops reporting."""
    if body.ai_available:
        await redis.set(AI_KEY, "1", ex=AI_TTL_S)
    else:
        await redis.delete(AI_KEY)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
