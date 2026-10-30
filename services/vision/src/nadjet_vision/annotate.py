"""Annotated stream: draw boxes, ids, relative speed and zones; republish as ``<camera>_ai``.

Frames are piped raw to ffmpeg (``h264_nvenc`` on the GPU host, TD-07) which pushes RTSP to the
video server; the browser plays it like any camera, so boxes and video stay in sync.
"""

import logging
import subprocess
from typing import IO

from nadjet_shared.catalogue import Zones
from nadjet_vision.ingest import BgrFrame
from nadjet_vision.track import Tracked

log = logging.getLogger("nadjet_vision.annotate")

SPEED_UNIT = "h/s"  # box-heights per second (TD-03)


def annotated_url(rtsp_base: str, camera_id: str) -> str:
    return f"{rtsp_base.rstrip('/')}/{camera_id}_ai"


def format_label(item: Tracked, speed: float | None) -> str:
    text = f"#{item.track_id} {item.detection.label}"
    return text if speed is None else f"{text} {speed:.1f}{SPEED_UNIT}"


def ffmpeg_command(url: str, width: int, height: int, fps: float, encoder: str) -> list[str]:
    """ffmpeg pipeline: raw BGR frames on stdin to an H.264 RTSP publisher."""
    codec_options = (
        ["-preset", "p1", "-tune", "ll"]
        if encoder.endswith("nvenc")
        else ["-preset", "ultrafast", "-tune", "zerolatency"]
    )
    return [
        "ffmpeg", "-loglevel", "error", "-nostdin",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
        "-r", f"{fps:g}", "-i", "-",
        "-c:v", encoder, *codec_options,
        "-g", str(max(1, round(fps * 2))), "-bf", "0", "-pix_fmt", "yuv420p",
        "-f", "rtsp", "-rtsp_transport", "tcp", url,
    ]  # fmt: skip


def draw(
    frame: BgrFrame,
    tracked: list[Tracked],
    speeds: dict[int, float | None],
    zones: Zones | None,
) -> BgrFrame:
    """Return a copy of ``frame`` with zones, boxes, track ids and speeds (uses OpenCV)."""
    import cv2
    import numpy as np

    out = frame.copy()
    if zones is not None:
        height, width = frame.shape[:2]
        sx, sy = width / zones.frame.width, height / zones.frame.height
        for ring, colour in [(zones.carriageway, (120, 120, 120))] + [
            (lane, (0, 200, 255)) for lane in zones.live_lanes
        ]:
            points = np.array([[x * sx, y * sy] for x, y in ring], dtype=np.int32)
            cv2.polylines(out, [points], isClosed=True, color=colour, thickness=2)
    for item in tracked:
        x1, y1, x2, y2 = (int(v) for v in item.detection.box)
        cv2.rectangle(out, (x1, y1), (x2, y2), (60, 220, 60), 2)
        label = format_label(item, speeds.get(item.track_id))
        cv2.putText(
            out, label, (x1, max(12, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (60, 220, 60), 1
        )
    return out


class AnnotatedPublisher:
    """Owns the ffmpeg process; restarts it after a failure on the next frame."""

    def __init__(self, url: str, fps: float, encoder: str) -> None:
        self._url, self._fps, self._encoder = url, fps, encoder
        self._proc: subprocess.Popen[bytes] | None = None
        self._size: tuple[int, int] | None = None

    def _start(self, frame: BgrFrame) -> None:
        height, width = frame.shape[:2]
        self._size = (width, height)
        command = ffmpeg_command(self._url, width, height, self._fps, self._encoder)
        self._proc = subprocess.Popen(command, stdin=subprocess.PIPE)  # noqa: S603

    def write(self, frame: BgrFrame) -> bool:
        """Send one annotated frame; ``False`` if ffmpeg is down (it is restarted next time)."""
        if self._proc is not None and self._proc.poll() is not None:
            log.warning("ffmpeg exited with %s; restarting", self._proc.returncode)
            self._proc = None
        if self._proc is None or self._size != (frame.shape[1], frame.shape[0]):
            self.close()
            self._start(frame)
        stdin: IO[bytes] | None = self._proc.stdin if self._proc else None
        try:
            assert stdin is not None
            stdin.write(frame.tobytes())
            stdin.flush()
        except (BrokenPipeError, OSError, AssertionError):
            self._proc = None
            return False
        return True

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            if proc.stdin:
                proc.stdin.close()
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
