"""``/cameras`` and ``/system/cameras`` routes (operator roles)."""

from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.auth.deps import require_roles
from nadjet_api.auth.models import User
from nadjet_api.auth.roles import Role
from nadjet_api.cameras import health
from nadjet_api.cameras.models import Camera
from nadjet_api.cameras.schemas import CameraOut, CameraStatus, CameraSystemStatus, StreamUrls
from nadjet_api.config import Settings
from nadjet_api.db import get_session
from nadjet_api.incidents.deps import RedisDep

router = APIRouter(prefix="/cameras", tags=["cameras"])
system_router = APIRouter(prefix="/system", tags=["system"])

OperatorUser = Annotated[User, Depends(require_roles(Role.OPERATOR, Role.SUPERVISOR, Role.ADMIN))]


def camera_out(camera: Camera, settings: Settings) -> CameraOut:
    path = camera.stream_path
    return CameraOut(
        id=camera.id,
        name=camera.name,
        lat=camera.lat,
        lon=camera.lon,
        road=camera.road,
        pk_km=camera.pk_km,
        heading_deg=camera.heading_deg,
        wilaya=camera.wilaya,
        zones=camera.zones,
        status=cast(CameraStatus, camera.status),
        simulated=camera.simulated,
        stream=StreamUrls(
            path=path,
            rtsp_url=settings.rtsp_url_template.format(path=path),
            whep_url=settings.whep_url_template.format(path=path),
        ),
    )


@router.get("", responses={401: {"description": "Not authenticated"}, 403: {"description": "Role"}})
async def list_cameras(
    request: Request,
    _user: OperatorUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CameraOut]:
    """All registered cameras with coordinates, zones and stream URLs."""
    rows = await session.scalars(select(Camera).order_by(Camera.id))
    return [camera_out(c, request.app.state.settings) for c in rows]


@router.get("/{camera_id}", responses={404: {"description": "Unknown camera"}})
async def get_camera(
    camera_id: str,
    request: Request,
    _user: OperatorUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CameraOut:
    camera = await session.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Camera not found")
    return camera_out(camera, request.app.state.settings)


@system_router.get("/cameras", responses={401: {"description": "Not authenticated"}})
async def system_cameras(
    _user: OperatorUser,
    redis: RedisDep,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CameraSystemStatus]:
    """Camera status with FPS, per-stage latency and queue depth from each worker (FR-CAM-005)."""
    cameras = list(await session.scalars(select(Camera).order_by(Camera.id)))
    reports = await health.load_reports(redis, [c.id for c in cameras])
    now = datetime.now(UTC)
    return [
        CameraSystemStatus(
            id=c.id,
            name=c.name,
            status=cast(CameraStatus, c.status),
            simulated=c.simulated,
            health=reports.get(c.id),
            stale=(c.id not in reports) or health.is_stale(reports[c.id], now),
        )
        for c in cameras
    ]
