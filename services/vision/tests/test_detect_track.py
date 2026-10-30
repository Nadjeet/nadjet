"""Detection filtering, relative speed, zones and camera motion (FR-VIS-002/003/011)."""

from pathlib import Path

import numpy as np
import pytest

from nadjet_shared.catalogue import load_catalogue
from nadjet_vision.detect import Detection, Detector, filter_detections
from nadjet_vision.track import (
    CameraMotionDetector,
    Tracked,
    TrackHistory,
    point_in_polygon,
    zone_membership,
)

ROOT = Path(__file__).resolve().parents[3]


def det(x1: float, y1: float, x2: float, y2: float, cls: int = 3, conf: float = 0.9) -> Detection:
    return Detection((x1, y1, x2, y2), cls, "car", conf)


def test_filter_keeps_vehicles_and_people_above_threshold_only() -> None:
    raw = [
        det(0, 0, 10, 10),  # car
        det(0, 0, 10, 10, cls=1),  # person
        det(0, 0, 10, 10, cls=16),  # dog: not a target
        det(0, 0, 10, 10, conf=0.2),  # below threshold
        det(5, 5, 5, 9),  # empty box
    ]
    assert len(filter_detections(raw, threshold=0.4)) == 2


def test_fake_detector_satisfies_the_protocol() -> None:
    class Fake:
        model_id = "fake"

        def detect(self, frame: np.ndarray) -> list[Detection]:  # type: ignore[type-arg]
            return [det(0, 0, 4, 4)]

    detector: Detector = Fake()
    assert detector.detect(np.zeros((8, 8, 3), dtype=np.uint8))[0].label == "car"


def moving_car(history: TrackHistory, speed_heights_per_s: float, steps: int = 6) -> None:
    height = 100.0
    for i in range(steps):
        t = i * 0.2
        x = speed_heights_per_s * height * t
        history.update(t, [Tracked(1, det(x, 0, x + 160, height))])


def test_relative_speed_is_displacement_over_box_height_per_second() -> None:
    history = TrackHistory(window_s=1.0)
    moving_car(history, speed_heights_per_s=2.0)
    assert history.speed(1) == pytest.approx(2.0)


def test_relative_speed_is_scale_free() -> None:
    near, far = TrackHistory(), TrackHistory()
    for i in range(6):
        t = i * 0.2
        near.update(t, [Tracked(1, det(100 * t, 0, 100 * t + 80, 100))])
        far.update(t, [Tracked(1, det(50 * t, 0, 50 * t + 40, 50))])  # half size, half pixels
    assert near.speed(1) == pytest.approx(far.speed(1))  # type: ignore[arg-type]


def test_speed_is_median_smoothed_against_one_jittery_box() -> None:
    history = TrackHistory(window_s=1.0)
    xs = [0, 20, 40, 400, 80, 100]  # one wild detection at i=3
    for i, x in enumerate(xs):
        history.update(i * 0.2, [Tracked(1, det(x, 0, x + 100, 100))])
    assert history.speed(1) == pytest.approx(1.0, abs=0.01)  # the outlier does not move the median


def test_speed_needs_two_samples_and_stopped_vehicle_is_zero() -> None:
    history = TrackHistory()
    history.update(0.0, [Tracked(1, det(0, 0, 10, 10))])
    assert history.speed(1) is None
    for i in range(1, 6):
        history.update(i * 0.2, [Tracked(1, det(0, 0, 10, 10))])
    assert history.speed(1) == 0.0


def test_history_forgets_tracks_that_disappear() -> None:
    history = TrackHistory(forget_after_s=2.0)
    history.update(0.0, [Tracked(1, det(0, 0, 10, 10))])
    history.update(5.0, [Tracked(2, det(0, 0, 10, 10))])
    assert history.speed(1) is None
    assert len(history) == 1


SQUARE = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]


def test_point_in_polygon() -> None:
    assert point_in_polygon((5, 5), SQUARE)
    assert not point_in_polygon((15, 5), SQUARE)
    assert not point_in_polygon((5, -1), SQUARE)


def test_zone_membership_uses_the_camera_zones() -> None:
    zones = load_catalogue(ROOT / "data" / "cameras.yaml").cameras[0].zones
    assert zones is not None
    lane = zones.live_lanes[0]
    cx = sum(p[0] for p in lane[:-1]) / (len(lane) - 1)
    cy = sum(p[1] for p in lane[:-1]) / (len(lane) - 1)
    inside = zone_membership((cx, cy), zones)
    assert inside.live_lane == 0
    assert inside.in_carriageway
    outside = zone_membership((-50, -50), zones)
    assert outside.live_lane is None
    assert not outside.in_carriageway
    assert zone_membership((0, 0), None).live_lane is None


def test_zone_membership_scales_a_smaller_stream_to_the_zone_frame() -> None:
    """Zones are drawn on zones.frame; a 640x360 stream must hit the same lane at half scale."""
    zones = load_catalogue(ROOT / "data" / "cameras.yaml").cameras[0].zones
    assert zones is not None
    lane = zones.live_lanes[0]
    cx = sum(p[0] for p in lane[:-1]) / (len(lane) - 1)
    cy = sum(p[1] for p in lane[:-1]) / (len(lane) - 1)
    half = (zones.frame.width // 2, zones.frame.height // 2)
    assert zone_membership((cx / 2, cy / 2), zones, half).live_lane == 0
    assert zone_membership((cx, cy), zones, (zones.frame.width, zones.frame.height)).live_lane == 0


def textured(seed: int = 1, size: tuple[int, int] = (240, 320)) -> np.ndarray:  # type: ignore[type-arg]
    rng = np.random.default_rng(seed)
    grey = rng.integers(0, 255, size, dtype=np.uint8)
    return np.stack([grey, grey, grey], axis=2)


def test_motion_detector_flags_a_panning_camera_and_clears_when_still() -> None:
    background = textured()
    detector = CameraMotionDetector(shift_px=2.0)
    for _ in range(4):
        assert not detector.update(background)
    for i in range(1, 6):  # pan: whole image shifts 12 px per frame
        detector.update(np.roll(background, 12 * i, axis=1))
    assert detector.moving
    still = np.roll(background, 12 * 6, axis=1)
    for _ in range(5):
        detector.update(still)
    assert not detector.moving


def test_motion_detector_ignores_a_vehicle_crossing_a_static_scene() -> None:
    background = textured()
    detector = CameraMotionDetector(shift_px=2.0)
    for i in range(10):
        frame = background.copy()
        frame[100:140, 20 + 25 * i : 60 + 25 * i] = 255  # bright box moves across
        detector.update(frame)
    assert not detector.moving
