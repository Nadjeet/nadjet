"""Simulator controls (PRD FR-CAM-004): list, restart, freeze, outage, restore and swap.

Path changes go through the MediaMTX control API (:9997). Freezing signals the ffmpeg
publisher inside the MediaMTX container with ``docker compose exec``.
"""

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from nadjet_camsim.config import CONTAINER_VIDEOS_DIR, path_config
from nadjet_shared.catalogue import Camera, Catalogue

Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]

VIDEO_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(mp4|mkv|mov)$")


class ControlError(RuntimeError):
    """A control command failed (message is meant for the operator)."""


@dataclass(frozen=True)
class CameraState:
    id: str
    online: bool
    readers: int
    source: str


def run_subprocess(argv: list[str]) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(argv, capture_output=True, text=True, check=False)  # noqa: S603


def signal_command(signal: str, cam_id: str) -> str:
    """Shell command signalling the ffmpeg publisher of ``cam_id`` (``[f]`` skips the shell)."""
    return f"pkill -{signal} -f '[f]fmpeg .*/{cam_id}$'"


def compose_exec(compose_file: Path, service: str, shell_command: str) -> list[str]:
    return [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "--profile",
        "video",
        "exec",
        "-T",
        service,
        "sh",
        "-c",
        shell_command,
    ]


class Controller:
    def __init__(
        self,
        catalogue: Catalogue,
        videos_dir: Path,
        api: httpx.Client,
        compose_file: Path,
        service: str = "mediamtx",
        run: Runner = run_subprocess,
    ) -> None:
        self.catalogue = catalogue
        self.videos_dir = videos_dir
        self.api = api
        self.compose_file = compose_file
        self.service = service
        self.run = run

    def camera(self, cam_id: str) -> Camera:
        for cam in self.catalogue.cameras:
            if cam.id == cam_id:
                return cam
        known = ", ".join(c.id for c in self.catalogue.cameras)
        raise ControlError(f"unknown camera {cam_id!r} (known: {known})")

    # -- MediaMTX control API
    def _call(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        try:
            response = self.api.request(method, url, **kwargs)  # type: ignore[arg-type]
        except httpx.HTTPError as exc:
            raise ControlError(
                f"MediaMTX control API unreachable at {self.api.base_url} "
                f"({type(exc).__name__}); is `make dev` running?"
            ) from exc
        if response.is_error:
            raise ControlError(f"MediaMTX answered {response.status_code}: {response.text.strip()}")
        return response

    def _signal(self, signal: str, cam_id: str) -> bool:
        argv = compose_exec(self.compose_file, self.service, signal_command(signal, cam_id))
        return self.run(argv).returncode == 0

    def _require_signal(self, signal: str, cam_id: str) -> None:
        if not self._signal(signal, cam_id):
            raise ControlError(f"no running publisher for {cam_id} (is the camera in outage?)")

    # -- commands
    def list_states(self) -> list[CameraState]:
        items = self._call("GET", "/v3/paths/list", params={"itemsPerPage": 1000}).json()["items"]
        by_name = {item["name"]: item for item in items}
        states = []
        for cam in self.catalogue.cameras:
            item = by_name.get(cam.id)
            source = (item.get("source") or {}).get("type", "") if item else ""
            states.append(
                CameraState(
                    cam.id,
                    online=bool(item and item.get("ready")),
                    readers=len(item.get("readers", [])) if item else 0,
                    source=source,
                )
            )
        return states

    def restart(self, cam_id: str) -> None:
        """Kill the publisher; MediaMTX restarts it (runOnInitRestart) from the clip start."""
        self.camera(cam_id)
        self._require_signal("KILL", cam_id)

    def freeze(self, cam_id: str) -> None:
        """SIGSTOP the publisher: no new frames, the RTSP session stays open."""
        self.camera(cam_id)
        self._require_signal("STOP", cam_id)

    def unfreeze(self, cam_id: str) -> None:
        self.camera(cam_id)
        self._require_signal("CONT", cam_id)

    def outage(self, cam_id: str) -> None:
        """Delete the path (readers are dropped) and make sure no publisher lingers."""
        self.camera(cam_id)
        self._call("DELETE", f"/v3/config/paths/delete/{cam_id}")
        self._signal("KILL", cam_id)  # best effort: a frozen publisher ignores the path closing

    def restore(self, cam_id: str) -> None:
        cam = self.camera(cam_id)
        self._call(
            "POST",
            f"/v3/config/paths/add/{cam_id}",
            json=path_config(f"{CONTAINER_VIDEOS_DIR}/{cam.video}"),
        )

    def swap(self, cam_id: str, video: str) -> None:
        """Publish another clip from the videos directory on the same path."""
        self.camera(cam_id)
        if not VIDEO_NAME.match(video):
            raise ControlError(f"invalid video name {video!r}: give a file name, not a path")
        if not (self.videos_dir / video).is_file():
            raise ControlError(f"video {video!r} not found in {self.videos_dir}")
        self._call(
            "PATCH",
            f"/v3/config/paths/patch/{cam_id}",
            json=path_config(f"{CONTAINER_VIDEOS_DIR}/{video}"),
        )
