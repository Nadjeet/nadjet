"""Service-to-service endpoints (vision workers): candidates and evidence upload."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.config import Settings
from nadjet_api.db import get_session
from nadjet_api.incidents.deps import RedisDep, SignerDep, StoreDep, announce, require_ingest_token
from nadjet_api.incidents.evidence import save_evidence, upload_chunks
from nadjet_api.incidents.ingest import enqueue
from nadjet_api.incidents.models import Incident, IncidentEvent
from nadjet_api.incidents.schemas import CandidateAccepted, EvidenceOut
from nadjet_api.incidents.store import EvidenceTooLargeError
from nadjet_shared.events import IncidentCandidate

router = APIRouter(
    prefix="/internal", tags=["internal"], dependencies=[Depends(require_ingest_token)]
)

ALLOWED_TYPES: dict[str, dict[str, str]] = {
    "clip": {"video/mp4": ".mp4", "video/webm": ".webm"},
    "keyframe": {"image/jpeg": ".jpg", "image/png": ".png"},
    "photo": {"image/jpeg": ".jpg", "image/png": ".png"},
}


@router.post(
    "/candidates",
    status_code=status.HTTP_202_ACCEPTED,
    responses={401: {"description": "Invalid service token"}},
)
async def post_candidate(
    candidate: IncidentCandidate,
    redis: RedisDep,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=128)],
) -> CandidateAccepted:
    """Queue a candidate (Redis Stream). Re-sending the same ``Idempotency-Key`` is safe."""
    return CandidateAccepted(stream_id=await enqueue(redis, candidate, idempotency_key))


@router.post(
    "/evidence",
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "Unknown incident"},
        409: {"description": "Candidate not persisted yet, retry"},
        413: {"description": "File too large"},
        415: {"description": "Unsupported media type"},
    },
)
async def upload_evidence(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: RedisDep,
    signer: SignerDep,
    store: StoreDep,
    file: Annotated[UploadFile, File()],
    kind: Annotated[Literal["clip", "keyframe", "photo"], Form()],
    incident_id: Annotated[uuid.UUID | None, Form()] = None,
    idempotency_key: Annotated[str | None, Form()] = None,
    start_ts: Annotated[datetime | None, Form()] = None,
    end_ts: Annotated[datetime | None, Form()] = None,
) -> EvidenceOut:
    """Store a file under the evidence root; SHA-256 is computed server-side (FR-SEC-003).

    Identify the incident by ``incident_id`` or by the ``idempotency_key`` of its candidate.
    """
    settings: Settings = request.app.state.settings
    extension = ALLOWED_TYPES[kind].get(file.content_type or "")
    if extension is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Unsupported media type")
    if incident_id is None and idempotency_key:
        incident_id = await session.scalar(
            select(IncidentEvent.incident_id).where(
                IncidentEvent.idempotency_key == idempotency_key
            )
        )
        if incident_id is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Candidate not persisted yet")
    if incident_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "incident_id or idempotency_key required"
        )
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")

    try:
        evidence, change = await save_evidence(
            session,
            signer,
            store,
            incident_id,
            kind,
            upload_chunks(file),
            extension,
            file.content_type or "",
            max_bytes=settings.evidence_max_mb * 1024 * 1024,
            start_ts=start_ts,
            end_ts=end_ts,
        )
    except EvidenceTooLargeError:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File too large") from None
    await session.commit()
    await announce(redis, [change])
    return EvidenceOut.model_validate(evidence)
