"""Camera catalogue (``data/cameras.yaml``) and MediaMTX config rendering."""

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

PATH_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


class GeoPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: float = Field(ge=18.9, le=37.2, description="Inside Algeria's bounding box")
    lon: float = Field(ge=-8.7, le=12.0)


class Camera(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    video: str = Field(description="File name inside the videos directory")
    geo: GeoPoint
    road: str
    pk_km: float | None = None
    heading_deg: float = Field(default=0, ge=0, lt=360)
    wilaya: str

    @field_validator("id")
    @classmethod
    def valid_path_name(cls, value: str) -> str:
        if not PATH_NAME.match(value):
            raise ValueError("id must be lowercase letters, digits and dashes (MediaMTX path)")
        return value


class Catalogue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cameras: list[Camera]

    @field_validator("cameras")
    @classmethod
    def unique_ids(cls, cameras: list[Camera]) -> list[Camera]:
        ids = [c.id for c in cameras]
        if len(ids) != len(set(ids)):
            raise ValueError("camera ids must be unique")
        return cameras


def load_catalogue(path: Path) -> Catalogue:
    return Catalogue.model_validate(yaml.safe_load(path.read_text()))


def publisher_command(video_in_container: str) -> str:
    """ffmpeg command MediaMTX runs to publish a file as a looping camera, without re-encoding."""
    return (
        f"ffmpeg -hide_banner -loglevel warning -re -stream_loop -1 -i {video_in_container} "
        "-map 0:v:0 -c copy -f rtsp -rtsp_transport tcp rtsp://localhost:$RTSP_PORT/$MTX_PATH"
    )


def render_mediamtx(
    catalogue: Catalogue, videos_dir: Path, container_videos_dir: str = "/videos"
) -> tuple[dict[str, Any], list[str]]:
    """Return (mediamtx config, ids of cameras skipped because their video file is missing)."""
    paths: dict[str, Any] = {}
    skipped: list[str] = []
    for cam in catalogue.cameras:
        if not (videos_dir / cam.video).is_file():
            skipped.append(cam.id)
            continue
        paths[cam.id] = {
            "runOnInit": publisher_command(f"{container_videos_dir}/{cam.video}"),
            "runOnInitRestart": True,
        }
    config: dict[str, Any] = {
        "logLevel": "info",
        "api": True,
        "apiAddress": ":9997",
        "rtspAddress": ":8554",
        "rtspTransports": ["tcp"],
        "webrtcAddress": ":8889",
        "webrtcLocalUDPAddress": ":8189",
        "webrtcLocalTCPAddress": ":8189",
        "hlsAddress": ":8888",
        "rtmp": False,
        "srt": False,
        # Local development only: anonymous access. Production uses API-delegated auth (TD-17).
        "authInternalUsers": [
            {
                "user": "any",
                "pass": "",
                "ips": [],
                "permissions": [
                    {"action": a} for a in ("publish", "read", "playback", "api", "metrics")
                ],
            }
        ],
        "paths": {**paths, "all_others": {}},
    }
    return config, skipped
