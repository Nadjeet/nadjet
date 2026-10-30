"""Camera catalogue (``data/cameras.yaml``) and MediaMTX config rendering."""

from pathlib import Path
from typing import Any

from nadjet_shared.catalogue import Camera, Catalogue, load_catalogue

__all__ = [
    "Camera",
    "Catalogue",
    "load_catalogue",
    "path_config",
    "publisher_command",
    "render_mediamtx",
]

CONTAINER_VIDEOS_DIR = "/videos"


def publisher_command(video_in_container: str) -> str:
    """ffmpeg command MediaMTX runs to publish a file as a looping camera, without re-encoding."""
    return (
        f"ffmpeg -hide_banner -loglevel warning -re -stream_loop -1 -i {video_in_container} "
        "-map 0:v:0 -c copy -f rtsp -rtsp_transport tcp rtsp://localhost:$RTSP_PORT/$MTX_PATH"
    )


def path_config(video_in_container: str) -> dict[str, Any]:
    """MediaMTX path settings that publish ``video_in_container`` as a looping camera."""
    return {"runOnInit": publisher_command(video_in_container), "runOnInitRestart": True}


FREEZE_READ_TIMEOUT = "1h"


def render_mediamtx(
    catalogue: Catalogue, videos_dir: Path, container_videos_dir: str = CONTAINER_VIDEOS_DIR
) -> tuple[dict[str, Any], list[str]]:
    """Return (mediamtx config, ids of cameras skipped because their video file is missing)."""
    paths: dict[str, Any] = {}
    skipped: list[str] = []
    for cam in catalogue.cameras:
        if not (videos_dir / cam.video).is_file():
            skipped.append(cam.id)
            continue
        paths[cam.id] = path_config(f"{container_videos_dir}/{cam.video}")
    config: dict[str, Any] = {
        "logLevel": "info",
        "api": True,
        "apiAddress": ":9997",
        "rtspAddress": ":8554",
        "rtspTransports": ["tcp"],
        # A frozen camera (SIGSTOP'd publisher, FR-CAM-004) sends nothing; with the default 10 s
        # MediaMTX drops it and its readers, turning a freeze into an outage.
        "readTimeout": FREEZE_READ_TIMEOUT,
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
