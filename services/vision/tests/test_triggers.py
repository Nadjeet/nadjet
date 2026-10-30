"""Trigger rules on synthetic track histories (FR-VIS-004, FR-VIS-010, FR-VIS-011, E-01..E-04).

The scenes drive the real ``TrackHistory`` speed measure, so the rules see what the pipeline
gives them. No clip, file name or clock value decides anything.
"""

from collections.abc import Callable

import pytest

from nadjet_shared import TriggerType
from nadjet_shared.catalogue import Frame, Zones
from nadjet_vision.detect import Detection
from nadjet_vision.track import Tracked, TrackHistory, zone_membership
from nadjet_vision.triggers import (
    Observation,
    TriggerConfig,
    TriggerEngine,
    TriggerEvent,
    in_contact,
    iou,
)

FPS = 5
DT = 1 / FPS
WALL0 = 1_800_000_000.0
LANE_Y = 400  # top of car boxes; ground point is 40 px lower, inside the live lane
ZONES = Zones(
    frame=Frame(width=1000, height=600),
    live_lanes=[[(0, 300), (1000, 300), (1000, 600), (0, 600), (0, 300)]],
    carriageway=[(0, 250), (1000, 250), (1000, 600), (0, 600), (0, 250)],
)


def box(x: float, y: float = LANE_Y, w: float = 60, h: float = 40, label: str = "car") -> Detection:
    ids = {"car": 3, "bus": 6, "person": 1, "truck": 8}
    return Detection((x, y, x + w, y + h), ids[label], label, 0.9)


class Scene:
    """Feeds frames at 5 fps to one engine through a real TrackHistory."""

    def __init__(
        self, config: TriggerConfig | None = None, zones: Zones | None = ZONES, wall0: float = WALL0
    ) -> None:
        self.engine = TriggerEngine(config)
        self.history = TrackHistory()
        self.zones = zones
        self.t = 0.0
        self.wall0 = wall0
        self.events: list[TriggerEvent] = []

    def step(
        self, objects: dict[int, Detection], camera_moving: bool = False
    ) -> list[TriggerEvent]:
        tracked = [Tracked(i, d) for i, d in objects.items()]
        self.history.update(self.t, tracked)
        speeds = {i: self.history.speed(i) for i in objects}
        zones = {i: zone_membership(d.anchor, self.zones) for i, d in objects.items()}
        out = self.engine.update(
            Observation(self.t, self.wall0 + self.t, tracked, speeds, zones, camera_moving)
        )
        self.events += out
        self.t += DT
        return out

    def run(
        self,
        seconds: float,
        make: Callable[[float], dict[int, Detection]],
        camera_moving: bool = False,
    ) -> None:
        start = self.t
        while self.t < start + seconds - 1e-9:
            self.step(make(self.t - start), camera_moving)


def traffic(
    t: float, x0: float = 0, speed_px: float = 12, lane_y: float = 330
) -> dict[int, Detection]:
    """Three free-flowing cars in a second lane band (ids 10..12), moving the whole time."""
    return {10 + k: box((x0 + 300 * k + speed_px * FPS * t) % 900, lane_y) for k in range(3)}


def kinds(events: list[TriggerEvent]) -> list[TriggerType]:
    return [e.trigger for e in events]


# --------------------------------------------------------------------- geometry


def test_iou_and_contact() -> None:
    a, b = box(100), box(150)  # 10 px overlap on 60 px boxes
    assert iou(a.box, b.box) == pytest.approx(10 * 40 / (2 * 2400 - 400))
    assert in_contact(a, b, TriggerConfig()) is not None
    assert in_contact(box(100), box(400), TriggerConfig()) is None


def test_contact_by_close_centres_without_box_overlap() -> None:
    cfg = TriggerConfig()
    a, b = box(100), box(161)  # 1 px gap: IoU 0, centres 61 px apart (< 0.6 x 60 = 36? no)
    assert in_contact(a, b, cfg) is None
    c = box(100, w=100)
    d = box(101, y=LANE_Y + 41)  # vertically separated, centres close
    assert in_contact(c, d, cfg) is not None


# --------------------------------------------------------------------- collision


def collision_scene(scene: Scene, *, other_traffic: bool = True) -> None:
    """Car 1 drives into stationary car 2 at x ~ 450, then both stay stopped."""

    def frame(t: float) -> dict[int, Detection]:
        x1 = min(200 + 75 * t, 455)
        objects = {1: box(x1), 2: box(500)}
        if other_traffic:
            objects.update(traffic(t))
        return objects

    scene.run(12, frame)


def test_collision_after_contact_when_both_stay_still() -> None:
    scene = Scene()
    collision_scene(scene)
    events = [e for e in scene.events if e.trigger is TriggerType.COLLISION_CANDIDATE]
    assert len(events) == 1
    event = events[0]
    assert event.track_ids == (1, 2)
    contact_t = (450 - 200) / 75  # car 1's box edge reaches car 2's: 3.33 s
    assert event.t_peak == pytest.approx(contact_t, abs=0.6)
    assert event.t_fire - event.t_peak >= 3.0
    assert event.signals["vehicle_count"] == 2.0
    assert event.signals["stopped_in_lane"] == 1.0
    assert event.peak_wall == pytest.approx(WALL0 + event.t_peak)
    assert event.evidence_t == event.t_peak  # fired within 5 s of the peak


def test_collision_is_not_a_repeat_of_the_hard_stop_of_the_same_vehicle() -> None:
    scene = Scene()
    collision_scene(scene)
    assert kinds(scene.events) == [TriggerType.HARD_STOP, TriggerType.COLLISION_CANDIDATE]
    assert set(scene.events[0].track_ids) <= set(scene.events[1].track_ids)


def test_collision_of_other_vehicles_inside_the_cooldown_is_suppressed() -> None:
    scene = Scene()
    scene.run(10, hard_stop_frame(stop_at=4.0))
    assert kinds(scene.events) == [TriggerType.HARD_STOP]

    def second(t: float) -> dict[int, Detection]:
        return {7: box(min(100 + 75 * t, 455), 480), 8: box(500, 480), **traffic(t)}

    scene.run(12, second)
    assert kinds(scene.events) == [TriggerType.HARD_STOP]


def test_no_collision_when_both_vehicles_were_already_stopped() -> None:
    scene = Scene()
    scene.run(15, lambda t: {1: box(450), 2: box(500), **traffic(t)})
    assert not scene.events


def test_no_collision_when_one_vehicle_drives_on() -> None:
    scene = Scene()
    scene.run(
        14, lambda t: {1: box(200 + 75 * t), 2: box(500), **traffic(t)}
    )  # passes through and beyond
    assert TriggerType.COLLISION_CANDIDATE not in kinds(scene.events)


def test_no_collision_inside_a_jam() -> None:
    """E-01: contact while the rest of the traffic is already slowing down."""
    scene = Scene()

    def frame(t: float) -> dict[int, Detection]:
        objects = {1: box(200 + 75 * min(t, 3.4)), 2: box(500)}
        objects.update({10 + k: box(100 + 120 * k, 330) for k in range(4)})  # queue, stopped
        return objects

    scene.run(14, frame)
    assert TriggerType.COLLISION_CANDIDATE not in kinds(scene.events)
    assert scene.engine.suppressed["jam"] >= 1


def test_collision_survives_one_vehicle_missing_for_a_moment() -> None:
    scene = Scene()

    def frame(t: float) -> dict[int, Detection]:
        x1 = min(200 + 75 * t, 455)
        objects = {1: box(x1), 2: box(500), **traffic(t)}
        if 4.0 <= t < 4.4:  # occluded for two frames, shorter than lost_after_s
            del objects[2]
        return objects

    scene.run(12, frame)
    assert TriggerType.COLLISION_CANDIDATE in kinds(scene.events)


# --------------------------------------------------------------------- hard stop


def hard_stop_frame(stop_at: float, *, ids_switch_at: float | None = None):  # type: ignore[no-untyped-def]
    def frame(t: float) -> dict[int, Detection]:
        x = 100 + 90 * min(t, stop_at)  # 18 px/frame = 2.25 lengths/s, then still
        car_id = 1 if ids_switch_at is None or t < ids_switch_at else 99
        return {car_id: box(x), **traffic(t)}

    return frame


def test_hard_stop_fires_after_the_vehicle_stays_still() -> None:
    scene = Scene()
    scene.run(10, hard_stop_frame(stop_at=4.0))
    events = [e for e in scene.events if e.trigger is TriggerType.HARD_STOP]
    assert len(events) == 1
    event = events[0]
    assert event.track_ids == (1,)
    assert event.t_peak == pytest.approx(4.0, abs=1.0)
    assert event.t_fire >= 4.0 + 2.0
    assert event.signals["speed_drop"] > 0.7
    assert event.signals["others_slowed"] == 0.0
    assert event.signals["stopped_in_lane"] == 1.0


def test_hard_stop_does_not_fire_before_the_stop_is_held() -> None:
    scene = Scene()
    scene.run(5.5, hard_stop_frame(stop_at=4.0))  # only ~1.5 s still
    assert not scene.events


def test_no_hard_stop_when_the_vehicle_brakes_gently() -> None:
    scene = Scene()

    positions: list[float] = []
    x, speed = 100.0, 18.0
    for _ in range(80):
        positions.append(x)
        x += speed
        speed = max(0.0, speed - 0.7)  # about 3.5 px/s per frame: no 70% drop within 1 s

    def gentle(t: float) -> dict[int, Detection]:
        n = min(round(t * FPS), len(positions) - 1)
        return {1: box(positions[n]), **traffic(t)}

    scene.run(16, gentle)
    assert TriggerType.HARD_STOP not in kinds(scene.events)


def test_no_hard_stop_when_the_whole_traffic_stops_together() -> None:
    """E-01: a jam forms; the stopping vehicle is not special."""
    scene = Scene()

    def frame(t: float) -> dict[int, Detection]:
        run_t = min(t, 4.0)
        objects = {1: box(100 + 90 * run_t)}
        objects.update(
            {10 + k: box(100 + 200 * k + 90 * run_t, 330) for k in range(1, 4)}  # all stop at 4 s
        )
        return objects

    scene.run(12, frame)
    assert TriggerType.HARD_STOP not in kinds(scene.events)
    assert scene.engine.suppressed["jam"] >= 1


def test_hard_stop_fires_when_few_others_slow_down() -> None:
    scene = Scene()

    def frame(t: float) -> dict[int, Detection]:
        objects = {1: box(100 + 90 * min(t, 4.0))}
        traffic_cars = traffic(t)
        # 1 of 3 others stops too: 33 % >= 30 % would be a jam, so use 1 of 4.
        traffic_cars[13] = box(700 + 12 * FPS * min(t, 4.0), 480)
        objects.update(traffic_cars)
        return objects

    scene.run(10, frame)
    assert scene.engine.suppressed["jam"] == 0
    assert TriggerType.HARD_STOP in kinds(scene.events)


def test_id_switch_at_the_stop_is_not_a_hard_stop() -> None:
    """The new id has no measured speed before the stop: nothing to compare against."""
    scene = Scene()
    scene.run(12, hard_stop_frame(stop_at=4.0, ids_switch_at=4.4))
    assert TriggerType.HARD_STOP not in kinds(scene.events)


def test_id_switch_while_moving_does_not_fire() -> None:
    scene = Scene()
    scene.run(8, hard_stop_frame(stop_at=100.0, ids_switch_at=3.0))
    assert not scene.events


# --------------------------------------------------------------------- stalled vehicle


def test_stalled_vehicle_fires_after_20_s_in_a_live_lane() -> None:
    scene = Scene()
    scene.run(30, lambda t: {1: box(500), **traffic(t)})
    events = [e for e in scene.events if e.trigger is TriggerType.STALLED_VEHICLE]
    assert len(events) == 1
    assert events[0].t_fire >= 20.0
    assert events[0].signals["stopped_in_lane"] == 1.0
    assert events[0].t_start == pytest.approx(events[0].t_peak)
    assert events[0].evidence_t == events[0].t_fire  # the ring cannot reach back 20 s


def test_stalled_vehicle_needs_moving_traffic() -> None:
    scene = Scene()
    scene.run(30, lambda t: {1: box(500)})
    assert not scene.events
    assert scene.engine.suppressed["no_traffic"] > 0


def test_stalled_vehicle_outside_the_live_lane_is_ignored() -> None:
    scene = Scene()
    scene.run(30, lambda t: {1: box(500, y=100), **traffic(t)})  # ground point above the lane
    assert not scene.events


def test_no_stalled_vehicle_in_a_queue() -> None:
    scene = Scene()
    scene.run(30, lambda t: {10 + k: box(100 + 120 * k, 330) for k in range(5)})
    assert not scene.events


# --------------------------------------------------------------------- pedestrian


def person(x: float = 400, y: float = 450) -> Detection:
    return box(x, y, w=20, h=50, label="person")


def test_pedestrian_on_carriageway_for_2_s() -> None:
    scene = Scene()
    scene.run(4, lambda t: {5: person(), **traffic(t)})
    events = [e for e in scene.events if e.trigger is TriggerType.PEDESTRIAN_ON_ROAD]
    assert len(events) == 1
    assert events[0].track_ids == (5,)
    assert events[0].t_fire >= 2.0
    assert events[0].signals["person_on_road"] == 1.0
    assert events[0].t_peak == pytest.approx(0.0)  # when the person stepped onto the road


def test_pedestrian_off_the_road_does_not_trigger() -> None:
    scene = Scene()
    scene.run(8, lambda t: {5: person(y=100)})  # ground point above the carriageway
    assert not scene.events


def test_pedestrian_crossing_quickly_does_not_trigger() -> None:
    scene = Scene()
    scene.run(1.4, lambda t: {5: person()})
    scene.run(5, lambda t: {5: person(y=100)})
    assert not scene.events


def test_pedestrian_timer_does_not_span_an_occlusion() -> None:
    scene = Scene()
    scene.run(1.4, lambda t: {5: person()})
    scene.run(2.0, lambda t: {})  # gone for 2 s (> lost_after_s)
    scene.run(1.4, lambda t: {5: person()})
    assert not scene.events


def test_two_frame_blip_is_not_confirmed() -> None:
    cfg = TriggerConfig(pedestrian_s=0.0, confirm_frames=3)
    scene = Scene(cfg)
    scene.run(0.4, lambda t: {5: person()})  # 2 frames on the road
    scene.run(1.0, lambda t: {5: person(y=100)})
    assert not scene.events


# --------------------------------------------------------------------- camera motion


def test_no_trigger_while_the_camera_moves() -> None:
    scene = Scene()
    scene.run(10, hard_stop_frame(stop_at=4.0), camera_moving=True)
    assert not scene.events
    assert scene.engine.suppressed["camera_motion"] > 0


def test_stop_during_camera_motion_is_not_reported_as_a_hard_stop_afterwards() -> None:
    scene = Scene()
    scene.run(6, hard_stop_frame(stop_at=4.0), camera_moving=True)
    scene.run(8, lambda t: {1: box(100 + 90 * 4.0), **traffic(t)})  # still stopped, camera steady
    assert TriggerType.HARD_STOP not in kinds(scene.events)  # the speed before the stop is unknown


def test_rules_resume_after_the_camera_settles() -> None:
    scene = Scene()
    scene.run(3, lambda t: traffic(t), camera_moving=True)
    scene.run(12, hard_stop_frame(stop_at=4.0))
    assert TriggerType.HARD_STOP in kinds(scene.events)


# --------------------------------------------------------------------- cooldown


def test_second_event_inside_the_cooldown_is_suppressed() -> None:
    scene = Scene()
    scene.run(10, hard_stop_frame(stop_at=4.0))
    assert kinds(scene.events) == [TriggerType.HARD_STOP]
    scene.run(30, lambda t: {1: box(500), **traffic(t)})  # would also be stalled at +20 s
    assert kinds(scene.events) == [TriggerType.HARD_STOP]
    assert scene.engine.suppressed["cooldown"] >= 1


def test_event_after_the_cooldown_is_emitted_again() -> None:
    scene = Scene(TriggerConfig(cooldown_s=20.0))
    scene.run(10, hard_stop_frame(stop_at=4.0))
    scene.run(40, lambda t: {2: box(500), **traffic(t)})
    assert kinds(scene.events) == [TriggerType.HARD_STOP, TriggerType.STALLED_VEHICLE]


def test_looped_clip_gives_one_event_per_cooldown_not_one_per_loop() -> None:
    """E-02: the stream clock restarts at each loop; the wall clock does not."""
    scene = Scene()
    for loop in range(3):
        scene.t = 0.0  # PTS restart
        scene.wall0 = WALL0 + loop * 30.0  # loop length 30 s, cooldown 120 s
        scene.run(10, hard_stop_frame(stop_at=4.0))
        scene.run(20, lambda t: traffic(t))
    assert kinds(scene.events) == [TriggerType.HARD_STOP]
    assert scene.engine.suppressed["cooldown"] >= 2


def test_stream_restart_clears_track_state() -> None:
    scene = Scene()
    scene.run(3, lambda t: {1: box(500), **traffic(t)})
    scene.t = 0.0  # reconnect: ids and clock start over
    scene.history = TrackHistory()
    scene.run(15, lambda t: {1: box(100 + 12 * FPS * t), **traffic(t)})
    assert not scene.events


# --------------------------------------------------------------------- configuration


def test_overrides_change_thresholds_per_camera() -> None:
    cfg = TriggerConfig.with_overrides({"stalled_s": 5.0, "confirm_frames": 2})
    assert cfg.stalled_s == 5.0
    assert cfg.confirm_frames == 2
    assert cfg.cooldown_s == 120.0  # untouched default (doc 11 §6)
    scene = Scene(cfg)
    scene.run(12, lambda t: {1: box(500), **traffic(t)})
    assert TriggerType.STALLED_VEHICLE in kinds(scene.events)


def test_unknown_threshold_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown trigger threshold"):
        TriggerConfig.with_overrides({"stalled": 5.0})


def test_defaults_match_doc_11_section_6() -> None:
    cfg = TriggerConfig()
    assert (cfg.overlap_iou, cfg.overlap_centre_ratio, cfg.still_speed) == (0.05, 0.6, 0.1)
    assert (cfg.collision_still_s, cfg.hard_stop_drop, cfg.hard_stop_still_s) == (3.0, 0.7, 2.0)
    assert (cfg.jam_fraction, cfg.stalled_s, cfg.pedestrian_s) == (0.3, 20.0, 2.0)
    assert (cfg.confirm_frames, cfg.cooldown_s) == (3, 120.0)
