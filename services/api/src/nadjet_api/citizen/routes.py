"""``POST /public/reports``: one-tap citizen report with the phone's GPS position (US-9)."""

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated

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
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.config import Settings
from nadjet_api.db import get_session
from nadjet_api.incidents import service
from nadjet_api.incidents.deps import RedisDep, SignerDep, StoreDep, announce
from nadjet_api.incidents.evidence import save_evidence, upload_chunks
from nadjet_api.incidents.store import EvidenceTooLargeError
from nadjet_api.notifications.grammar import normalize_phone
from nadjet_api.ratelimit import hit
from nadjet_shared.events import (
    CandidateSource,
    GeoLocation,
    IncidentCandidate,
    TriggerType,
    Witness,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/public", tags=["public"])

# Algeria's bounding box: a position outside it is a mistyped or spoofed report.
LAT_RANGE = (18.0, 38.0)
LON_RANGE = (-9.0, 12.0)
MAX_PEOPLE = 99
PHONE_RE = re.compile(r"^\+?[0-9 ]{8,16}$")
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MULTIPART_OVERHEAD = 1024 * 1024  # form fields and boundaries on top of the photo


class ReportAccepted(BaseModel):
    short_code: str
    merged: bool
    photo_saved: bool


def photo_type(head: bytes) -> tuple[str, str] | None:
    """``(content_type, extension)`` from the file's own bytes; the client's header is untrusted."""
    if head.startswith(JPEG_MAGIC):
        return "image/jpeg", ".jpg"
    if head.startswith(PNG_MAGIC):
        return "image/png", ".png"
    return None


async def limit_reports(request: Request) -> None:
    """429 once a client IP files too many reports in the window (FR-CIT-004)."""
    settings: Settings = request.app.state.settings
    redis: Redis | None = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Rate limiter unavailable")
    client = request.client.host if request.client else "unknown"
    count = await hit(
        redis, f"ratelimit:public-report:{client}", window_s=settings.public_report_window_s
    )
    if count > settings.public_report_rate_limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many reports",
            headers={"Retry-After": str(settings.public_report_window_s)},
        )


@router.post(
    "/reports",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_reports)],
    responses={
        413: {"description": "Photo too large"},
        415: {"description": "Photo is not a JPEG or PNG"},
        422: {"description": "Position outside Algeria or invalid field"},
        429: {"description": "Rate limit exceeded"},
    },
)
async def post_report(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: RedisDep,
    signer: SignerDep,
    store: StoreDep,
    lat: Annotated[float, Form(ge=-90, le=90)],
    lon: Annotated[float, Form(ge=-180, le=180)],
    people_reported: Annotated[int | None, Form(ge=0, le=MAX_PEOPLE)] = None,
    trapped: Annotated[bool, Form()] = False,
    phone: Annotated[str | None, Form(max_length=20)] = None,
    photo: Annotated[UploadFile | None, File()] = None,
    idempotency_key: Annotated[str | None, Header(min_length=1, max_length=128)] = None,
) -> ReportAccepted:
    """Create an unverified citizen incident at ``lat``/``lon``, merged with a nearby one.

    Re-sending the same ``Idempotency-Key`` (a double tap, a retry) returns the same report.
    """
    settings: Settings = request.app.state.settings
    if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Position outside Algeria")
    if phone is not None:
        phone = phone.strip() or None
    if phone is not None and not PHONE_RE.match(phone):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid phone number")

    max_bytes = settings.public_photo_max_mb * 1024 * 1024
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > max_bytes + MULTIPART_OVERHEAD:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Photo too large")
    kind: tuple[str, str] | None = None
    if photo is not None and photo.filename:
        if (photo.size or 0) > max_bytes:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Photo too large")
        kind = photo_type(await photo.read(8))
        if kind is None:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Photo must be JPEG or PNG")
        await photo.seek(0)

    now = datetime.now(UTC)
    candidate = IncidentCandidate(
        source=CandidateSource.CITIZEN,
        location=GeoLocation(lat=lat, lon=lon),
        witness=Witness(people_reported=people_reported, trapped=trapped),
        trigger=TriggerType.CITIZEN_REPORT,
        event_time=now,
        detected_at=now,
    )
    key = f"web:{idempotency_key or uuid.uuid4()}"
    contact = {"phone": normalize_phone(phone)} if phone else None
    result = await service.ingest_candidate(session, signer, candidate, key, contact=contact)
    await session.commit()
    await announce(redis, result.changes)

    photo_saved = False
    if photo is not None and kind is not None and not result.duplicate:
        try:
            _evidence, change = await save_evidence(
                session,
                signer,
                store,
                result.incident.id,
                "photo",
                upload_chunks(photo),
                kind[1],
                kind[0],
                max_bytes=max_bytes,
            )
            await session.commit()
            await announce(redis, [change])
            photo_saved = True
        except (EvidenceTooLargeError, OSError):
            await session.rollback()
            log.exception("citizen photo for incident %s not stored", result.incident.id)
    return ReportAccepted(
        short_code=result.incident.short_code, merged=not result.created, photo_saved=photo_saved
    )
