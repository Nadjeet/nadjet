"""Tracking, relative speed, zone membership and camera motion (FR-VIS-003, FR-VIS-011).

Speed is ``pixel displacement / box height`` per second (TD-03): scale-free, so it needs no
calibration on the demo cameras. All of it is plain Python/NumPy; only ``ByteTrackTracker``
needs the ``supervision`` GPU extra.
"""

import statistics
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from nadjet_shared.catalogue import Zones
from nadjet_vision.detect import TARGET_CLASSES, Detection
from nadjet_vision.ingest import BgrFrame

Point = tuple[float, float]


@dataclass(frozen=True)
class Tracked:
    track_id: int
    detection: Detection


class Tracker(Protocol):
    def update(self, detections: list[Detection]) -> list[Tracked]: ...


class ByteTrackTracker:
    """ByteTrack from ``trackers`` (Roboflow, Apache-2.0) at the analysis frame rate.

    ``supervision`` 0.31 no longer ships a tracker. Detections that the tracker has not yet
    confirmed come back with ``tracker_id`` -1 and are not reported.
    """

    def __init__(self, fps: float, activation_threshold: float = 0.4) -> None:
        import supervision as sv
        from trackers import ByteTrackTracker as ByteTrack

        self._sv = sv
        self._tracker = ByteTrack(frame_rate=fps, track_activation_threshold=activation_threshold)

    def update(self, detections: list[Detection]) -> list[Tracked]:
        sv = self._sv
        if detections:
            batch = sv.Detections(
                xyxy=np.array([d.box for d in detections], dtype=np.float32),
                confidence=np.array([d.confidence for d in detections], dtype=np.float32),
                class_id=np.array([d.class_id for d in detections], dtype=int),
            )
        else:
            batch = sv.Detections.empty()
        tracked = self._tracker.update(batch)
        out: list[Tracked] = []
        if tracked.tracker_id is None:
            return out
        for xyxy, conf, cls, tid in zip(
            tracked.xyxy, tracked.confidence, tracked.class_id, tracked.tracker_id, strict=True
        ):
            if int(tid) < 0:
                continue
            box = (float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3]))
            label = TARGET_CLASSES.get(int(cls), str(int(cls)))
            out.append(Tracked(int(tid), Detection(box, int(cls), label, float(conf))))
        return out


@dataclass(frozen=True)
class _Sample:
    t: float
    x: float
    y: float
    h: float


class TrackHistory:
    """Per-track positions and relative speed in box-heights per second."""

    def __init__(self, window_s: float = 1.0, forget_after_s: float = 5.0) -> None:
        self._window_s = window_s
        self._forget_after_s = forget_after_s
        self._samples: dict[int, deque[_Sample]] = {}

    def update(self, t: float, tracked: Sequence[Tracked]) -> None:
        for item in tracked:
            x, y = item.detection.centre
            samples = self._samples.setdefault(item.track_id, deque())
            samples.append(_Sample(t, x, y, item.detection.height))
            while samples and t - samples[0].t > self._window_s:
                samples.popleft()
        for track_id in [
            tid for tid, s in self._samples.items() if not s or t - s[-1].t > self._forget_after_s
        ]:
            del self._samples[track_id]

    def speed(self, track_id: int) -> float | None:
        """Median step speed over the window; ``None`` until two samples exist."""
        samples = self._samples.get(track_id)
        if samples is None or len(samples) < 2:
            return None
        steps: list[float] = []
        for a, b in pairwise(samples):
            dt = b.t - a.t
            height = (a.h + b.h) / 2
            if dt <= 0 or height <= 0:
                continue
            steps.append(float(np.hypot(b.x - a.x, b.y - a.y)) / height / dt)
        return statistics.median(steps) if steps else None

    def __len__(self) -> int:
        return len(self._samples)


def point_in_polygon(point: Point, ring: Sequence[Sequence[float]]) -> bool:
    """Ray casting; ``ring`` may repeat its first point at the end."""
    x, y = point
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


@dataclass(frozen=True)
class ZoneMembership:
    live_lane: int | None  # index into zones.live_lanes
    in_carriageway: bool


def zone_membership(
    anchor: Point, zones: Zones | None, image_size: tuple[int, int] | None = None
) -> ZoneMembership:
    """Which live lane and whether the carriageway contains the object's ground point.

    Zones are drawn on a ``zones.frame`` sized image; ``image_size`` (width, height) of the
    analysed frame scales the anchor into that space when the stream resolution differs.
    """
    if zones is None:
        return ZoneMembership(None, False)
    if image_size is not None:
        width, height = image_size
        anchor = (
            anchor[0] * zones.frame.width / width,
            anchor[1] * zones.frame.height / height,
        )
    lane = next((i for i, r in enumerate(zones.live_lanes) if point_in_polygon(anchor, r)), None)
    return ZoneMembership(lane, point_in_polygon(anchor, zones.carriageway))


class CameraMotionDetector:
    """Global camera motion by phase correlation of consecutive small grey frames.

    A shaking or panning camera shifts the whole image; vehicles move only a small part of
    it, so the correlation peak follows the background. ``moving`` needs 2 of the last 3
    frames above the threshold and clears after 3 calm frames (no flicker).
    """

    def __init__(self, shift_px: float = 2.0, width: int = 160) -> None:
        self._threshold = shift_px
        self._width = width
        self._previous: NDArray[np.float32] | None = None
        self._recent: deque[bool] = deque(maxlen=3)
        self.moving = False
        self.last_shift_px = 0.0

    def _small_grey(self, frame: BgrFrame) -> NDArray[np.float32]:
        step = max(1, frame.shape[1] // self._width)
        grey = frame[::step, ::step].astype(np.float32)
        return grey.mean(axis=2) if grey.ndim == 3 else grey

    def update(self, frame: BgrFrame) -> bool:
        grey = self._small_grey(frame)
        previous, self._previous = self._previous, grey
        if previous is None or previous.shape != grey.shape:
            return self.moving
        window = np.outer(np.hanning(grey.shape[0]), np.hanning(grey.shape[1])).astype(np.float32)
        cross = np.fft.fft2(previous * window) * np.conj(np.fft.fft2(grey * window))
        magnitude = np.abs(cross)
        magnitude[magnitude == 0] = 1.0
        response = np.fft.ifft2(cross / magnitude).real
        peak = np.unravel_index(int(np.argmax(response)), response.shape)
        dy, dx = (
            int(p) if p <= s // 2 else int(p) - s for p, s in zip(peak, response.shape, strict=True)
        )
        self.last_shift_px = float(np.hypot(dx, dy))
        self._recent.append(self.last_shift_px >= self._threshold)
        if sum(self._recent) >= 2:
            self.moving = True
        elif not any(self._recent) and len(self._recent) == self._recent.maxlen:
            self.moving = False
        return self.moving
