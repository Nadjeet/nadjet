"""Response models of the camera registry."""

from typing import Any, Literal

from pydantic import BaseModel, Field

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
