"""``POST /internal/camera-health``: worker health reports (service token)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.cameras import health
from nadjet_api.cameras.models import Camera
from nadjet_api.cameras.schemas import CameraHealthAck
from nadjet_api.db import get_session
from nadjet_api.incidents.deps import RedisDep, require_ingest_token
from nadjet_shared.health import CameraHealthReport

router = APIRouter(
    prefix="/internal", tags=["internal"], dependencies=[Depends(require_ingest_token)]
)


@router.post(
    "/camera-health",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        401: {"description": "Invalid service token"},
        404: {"description": "Unknown camera"},
    },
)
async def post_camera_health(
    report: CameraHealthReport,
    redis: RedisDep,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CameraHealthAck:
    """Store the latest report; a fault or recovery updates the camera status once."""
    camera = await session.get(Camera, report.camera_id)
    if camera is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Camera not found")
    await health.store_report(redis, report)
    applied = await health.apply_report(session, camera, report)
    await session.commit()
    if applied.transition is not None:
        await health.announce(redis, camera.id, applied.transition, applied.status)
    return CameraHealthAck(status=applied.status, transition=applied.transition)
