"""Response models of the camera registry."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from nadjet_shared.health import CameraHealthReport

CameraStatus = Literal["unknown", "online", "degraded", "offline"]


class StreamUrls(BaseModel):
    path: str = Field(description="Video server path (MediaMTX)")
    rtsp_url: str = Field(description="RTSP URL for vision workers")
    whep_url: str = Field(description="WebRTC WHEP URL for the browser")


class CameraOut(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    road: str
    pk_km: float | None
    heading_deg: float
    wilaya: str
    zones: dict[str, Any] | None = Field(description="live_lanes and carriageway polygons")
    status: CameraStatus
    simulated: bool
    stream: StreamUrls


class CameraHealthAck(BaseModel):
    status: CameraStatus
    transition: Literal["camera_fault", "camera_recovered"] | None = Field(
        description="Set when this report changed the camera status"
    )


class CameraSystemStatus(BaseModel):
    """One row of the system page: registry status plus the latest worker report."""

    id: str
    name: str
    status: CameraStatus
    simulated: bool
    health: CameraHealthReport | None = Field(description="Latest report, null if none or expired")
    stale: bool = Field(description="No report for more than 15 s: the worker is not reporting")
