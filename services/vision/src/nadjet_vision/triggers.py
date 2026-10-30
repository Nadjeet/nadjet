"""Crash trigger rules over tracks (PRD FR-VIS-004, FR-VIS-010, FR-VIS-011, E-01..E-04).

``TriggerEngine.update`` is fed one observation per analysed frame (tracks, relative speeds,
zone membership, camera motion) and returns the triggers that fired on that frame. It is plain
Python: every rule is unit-tested on synthetic tracks. Nothing here reads a clip id, a file name,
a clock constant or a random value (FR-VIS-020); the only inputs are the measured tracks.

Thresholds are the doc 11 §6 defaults and can be overridden per camera (``Camera.triggers``).
Speeds are relative: box heights per second (TD-03).
"""

from collections import Counter, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from itertools import combinations, pairwise
from typing import Any, Self

from nadjet_shared import TriggerType
from nadjet_vision.detect import Detection
from nadjet_vision.track import Tracked, ZoneMembership

VEHICLE_LABELS = frozenset({"car", "motorcycle", "bus", "truck"})
PERSON_LABEL = "person"


@dataclass(frozen=True)
class TriggerConfig:
    """Rule thresholds. Defaults: docs/11 §6; the ones marked * are recorded in TD-39."""

    overlap_iou: float = 0.05  # collision: box IoU above this means contact
    overlap_centre_ratio: float = 0.6  # or centre distance below this x mean box width
    still_speed: float = 0.1  # lengths/s below which a track counts as stopped
    moving_speed: float = 0.5  # * lengths/s above which a track counts as moving
    collision_still_s: float = 3.0  # both tracks stopped this long after contact
    pair_memory_s: float = 10.0  # * how long a contact stays relevant after the last overlap
    hard_stop_drop: float = 0.7  # speed lost within the window
    hard_stop_window_s: float = 1.0
    hard_stop_still_s: float = 2.0  # then stays near zero this long
    jam_fraction: float = 0.3  # suppress when this share of other vehicles slows down
    # * hard_stop: the jam share is read this long after the impact (speed smoothing lag), not
    # at fire time (stop + 2 s), when traffic braking *because of* the crash would hide it.
    jam_lag_s: float = 1.0
    stalled_s: float = 20.0
    pedestrian_s: float = 2.0
    confirm_frames: int = 3  # E-04: consecutive frames before a state counts
    cooldown_s: float = 120.0  # FR-VIS-010, per location (one engine per camera)
    lost_after_s: float = 1.0  # * a track unseen this long loses its dwell timers (occlusion)
    forget_after_s: float = 5.0  # * a track unseen this long is dropped
    settle_s: float = 1.0  # * quiet period after camera motion (speed window)
    evidence_window_s: float = 5.0  # * evidence is anchored on the peak if fired within this

    @classmethod
    def with_overrides(cls, overrides: Mapping[str, float]) -> Self:
        """Defaults with a camera's ``triggers`` overrides; unknown names are an error."""
        known = {f.name: f for f in fields(cls)}
        unknown = sorted(set(overrides) - set(known))
        if unknown:
            raise ValueError(f"unknown trigger threshold(s): {', '.join(unknown)}")
        converted: dict[str, Any] = {
            name: int(value) if known[name].type is int else float(value)
            for name, value in overrides.items()
        }
        return replace(cls(), **converted)


@dataclass(frozen=True)
class Observation:
    """One analysed frame. ``t`` is the stream clock, ``wall`` the capture time (epoch s)."""

    t: float
    wall: float
    tracked: Sequence[Tracked]
    speeds: Mapping[int, float | None]
    zones: Mapping[int, ZoneMembership]
    camera_moving: bool


@dataclass(frozen=True)
class TriggerEvent:
    """A fired rule with its event window (stream clock, seconds) and measured signals."""

    trigger: TriggerType
    t_start: float
    t_peak: float  # best estimate of the impact -> event_time
    t_fire: float  # when the rule was satisfied
    evidence_t: float  # evidence clip is cut around this time
    track_ids: tuple[int, ...]
    signals: dict[str, float]
    peak_wall: float  # epoch seconds of t_peak
    fire_wall: float


def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    if ix <= 0 or iy <= 0:
        return 0.0
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def in_contact(a: Detection, b: Detection, config: TriggerConfig) -> float | None:
    """IoU when the two boxes touch (IoU or close centres, FR-VIS-004), else ``None``."""
    overlap = iou(a.box, b.box)
    if overlap > config.overlap_iou:
        return overlap
    (ax, ay), (bx, by) = a.centre, b.centre
    mean_width = ((a.box[2] - a.box[0]) + (b.box[2] - b.box[0])) / 2
    distance = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
    return (
        overlap if mean_width > 0 and distance < config.overlap_centre_ratio * mean_width else None
    )


@dataclass
class _Track:
    label: str
    detection: Detection
    last_seen: float
    speeds: deque[tuple[float, float]] = field(default_factory=deque)  # (t, speed), last ~4 s
    still_frames: int = 0
    still_since: float | None = None
    carriage_frames: int = 0
    carriage_since: float | None = None
    live_lane: int | None = None
    speed: float | None = None

    @property
    def is_vehicle(self) -> bool:
        return self.label in VEHICLE_LABELS

    def reset_dwell(self) -> None:
        self.still_frames = 0
        self.still_since = None
        self.carriage_frames = 0
        self.carriage_since = None


@dataclass
class _Contact:
    first_t: float
    last_t: float
    iou: float
    pre_speed: float
    static: bool  # contact inside a jam, or between tracks that were not moving
    fired: bool = False


@dataclass(frozen=True)
class _Others:
    count: int
    slowed: int
    moving: int

    @property
    def slowed_fraction(self) -> float:
        return self.slowed / self.count if self.count else 0.0


class TriggerEngine:
    """Per-camera rule evaluation with confirmation frames, suppression and cooldown."""

    SPEED_HISTORY_S = 4.0

    def __init__(self, config: TriggerConfig | None = None) -> None:
        self.config = config or TriggerConfig()
        self.suppressed: Counter[str] = Counter()
        self._tracks: dict[int, _Track] = {}
        self._contacts: dict[tuple[int, int], _Contact] = {}
        self._fired: set[tuple[str, tuple[int, ...]]] = set()
        self._last_t: float | None = None
        self._quiet_until = float("-inf")
        self._last_emit_wall: float | None = None
        self._last_event: TriggerEvent | None = None
        # (t, slowed share per track id) of recent frames, for the hard-stop jam check at impact
        self._slowed_history: deque[tuple[float, dict[int, bool]]] = deque()

    # ------------------------------------------------------------------ public

    def update(self, obs: Observation) -> list[TriggerEvent]:
        cfg = self.config
        if self._last_t is not None and (
            obs.t < self._last_t - 0.5 or obs.t - self._last_t > cfg.forget_after_s
        ):
            self._reset()  # stream restarted (loop, reconnect): ids and clock are new
        self._last_t = obs.t

        if obs.camera_moving:
            self._quiet_until = obs.t + cfg.settle_s
            self._suspend()
            self.suppressed["camera_motion"] += 1
            return []
        if obs.t < self._quiet_until:
            return []

        self._observe(obs)
        self._record_slowed(obs.t)
        offset = obs.wall - obs.t
        candidates = [
            *self._pedestrians(obs.t),
            *self._hard_stops(obs.t),
            *self._stalled(obs.t),
            *self._collisions(obs.t),
        ]
        emitted: list[TriggerEvent] = []
        for event in sorted(candidates, key=lambda e: e.t_peak):
            event = replace(event, peak_wall=event.t_peak + offset, fire_wall=obs.wall)
            if self._in_cooldown(obs.wall) and not self._escalates(event, obs.wall):
                self.suppressed["cooldown"] += 1
                continue
            self._last_emit_wall = obs.wall
            self._last_event = event
            emitted.append(event)
        return emitted

    # --------------------------------------------------------------- bookkeeping

    def _reset(self) -> None:
        self._tracks.clear()
        self._contacts.clear()
        self._fired.clear()
        self._quiet_until = float("-inf")
        self._slowed_history.clear()

    def _suspend(self) -> None:
        """Global camera motion invalidates speeds and dwell timers: start over after it."""
        for track in self._tracks.values():
            track.reset_dwell()
            track.speeds.clear()
        self._contacts.clear()

    def _in_cooldown(self, wall: float) -> bool:
        return (
            self._last_emit_wall is not None
            and 0 <= wall - self._last_emit_wall < self.config.cooldown_s
        )

    def _escalates(self, event: TriggerEvent, wall: float) -> bool:
        """A crash stops the car first (``hard_stop``) and the pair 3 s later: the collision rule
        about the same vehicles, soon after, is the same incident with better evidence, not a
        repeat. The API merges the two candidates (same place, within 60 s)."""
        last = self._last_event
        return (
            last is not None
            and event.trigger is TriggerType.COLLISION_CANDIDATE
            and last.trigger is not TriggerType.COLLISION_CANDIDATE
            and bool(set(event.track_ids) & set(last.track_ids))
            and wall - last.fire_wall <= self.config.pair_memory_s
        )

    def _observe(self, obs: Observation) -> None:
        cfg = self.config
        for item in obs.tracked:
            track = self._tracks.get(item.track_id)
            if track is None:
                track = self._tracks[item.track_id] = _Track(
                    item.detection.label, item.detection, obs.t
                )
            elif obs.t - track.last_seen > cfg.lost_after_s:
                track.reset_dwell()  # occluded for a while: timers cannot span the gap
            track.detection = item.detection
            track.last_seen = obs.t
            membership = obs.zones.get(item.track_id)
            track.live_lane = membership.live_lane if membership else None

            speed = obs.speeds.get(item.track_id)
            track.speed = speed
            if speed is None:
                track.still_frames, track.still_since = 0, None
            else:
                track.speeds.append((obs.t, speed))
                while track.speeds and obs.t - track.speeds[0][0] > self.SPEED_HISTORY_S:
                    track.speeds.popleft()
                if speed < cfg.still_speed:
                    track.still_frames += 1
                    if track.still_frames == 1:
                        track.still_since = obs.t
                else:
                    track.still_frames, track.still_since = 0, None

            if membership is not None and membership.in_carriageway:
                track.carriage_frames += 1
                if track.carriage_frames == 1:
                    track.carriage_since = obs.t
            else:
                track.carriage_frames, track.carriage_since = 0, None

        for track_id in [
            tid for tid, t in self._tracks.items() if obs.t - t.last_seen > cfg.forget_after_s
        ]:
            del self._tracks[track_id]
        self._fired = {k for k in self._fired if all(i in self._tracks for i in k[1])}

    def _seen(self, t: float) -> list[tuple[int, _Track]]:
        return [(i, tr) for i, tr in self._tracks.items() if tr.last_seen == t]

    def _is_still(self, track: _Track) -> bool:
        return track.still_frames >= self.config.confirm_frames and track.still_since is not None

    def _slowed_flags(self, t: float) -> dict[int, bool]:
        """Counted vehicles at ``t`` (live lanes when zones are known): id -> slowed or stopped."""
        cfg = self.config
        flags: dict[int, bool] = {}
        zoned = any(tr.live_lane is not None for _, tr in self._seen(t))
        for track_id, track in self._seen(t):
            if not track.is_vehicle or track.speed is None or (zoned and track.live_lane is None):
                continue
            reference = max((s for ts, s in track.speeds if t - 3.0 <= ts <= t - 1.0), default=0.0)
            braked = reference >= cfg.moving_speed and track.speed < 0.5 * reference
            flags[track_id] = track.speed < cfg.still_speed or braked
        return flags

    def _record_slowed(self, t: float) -> None:
        self._slowed_history.append((t, self._slowed_flags(t)))
        horizon = t - (self.config.hard_stop_still_s + self.config.hard_stop_window_s + 5.0)
        while self._slowed_history and self._slowed_history[0][0] < horizon:
            self._slowed_history.popleft()

    def _slowed_fraction_at(self, t: float, exclude: Sequence[int]) -> float:
        """Share of other vehicles slowed in the first recorded frame at or after ``t``."""
        flags = next((f for ts, f in self._slowed_history if ts >= t), None)
        if flags is None:
            return 0.0
        others = [slowed for i, slowed in flags.items() if i not in exclude]
        return sum(others) / len(others) if others else 0.0

    def _others(self, t: float, exclude: Sequence[int]) -> _Others:
        """Traffic around the subject: other vehicles (in live lanes when zones are known)."""
        cfg = self.config
        count = slowed = moving = 0
        zoned = any(tr.live_lane is not None for _, tr in self._seen(t))
        for track_id, track in self._seen(t):
            if track_id in exclude or not track.is_vehicle or track.speed is None:
                continue
            if zoned and track.live_lane is None:
                continue
            count += 1
            reference = max((s for ts, s in track.speeds if t - 3.0 <= ts <= t - 1.0), default=0.0)
            braked = reference >= cfg.moving_speed and track.speed < 0.5 * reference
            if track.speed < cfg.still_speed or braked:
                slowed += 1
            elif track.speed >= cfg.moving_speed:
                moving += 1
        return _Others(count, slowed, moving)

    def _fire_once(self, kind: str, ids: tuple[int, ...]) -> bool:
        key = (kind, ids)
        if key in self._fired:
            return False
        self._fired.add(key)
        return True

    def _event(
        self,
        trigger: TriggerType,
        t: float,
        t_start: float,
        t_peak: float,
        ids: tuple[int, ...],
        signals: dict[str, float],
    ) -> TriggerEvent:
        anchored = t - t_peak <= self.config.evidence_window_s
        return TriggerEvent(
            trigger=trigger,
            t_start=t_start,
            t_peak=t_peak,
            t_fire=t,
            evidence_t=t_peak if anchored else t,
            track_ids=ids,
            signals=signals,
            peak_wall=0.0,
            fire_wall=0.0,
        )

    # -------------------------------------------------------------------- rules

    def _pedestrians(self, t: float) -> list[TriggerEvent]:
        cfg = self.config
        out: list[TriggerEvent] = []
        for track_id, track in self._seen(t):
            since = track.carriage_since
            if track.label != PERSON_LABEL or since is None:
                continue
            if track.carriage_frames < cfg.confirm_frames or t - since < cfg.pedestrian_s:
                continue
            if self._fire_once("pedestrian", (track_id,)):
                signals = {"person_on_road": 1.0, "on_road_s": t - since}
                out.append(
                    self._event(
                        TriggerType.PEDESTRIAN_ON_ROAD, t, since, since, (track_id,), signals
                    )
                )
        return out

    def _hard_stops(self, t: float) -> list[TriggerEvent]:
        cfg = self.config
        out: list[TriggerEvent] = []
        for track_id, track in self._seen(t):
            since = track.still_since
            if not track.is_vehicle or since is None or not self._is_still(track):
                continue
            if t - since < cfg.hard_stop_still_s or ("hard_stop", (track_id,)) in self._fired:
                continue
            drop = self._speed_drop(track, since)
            if drop is None:
                continue  # no measured speed before the stop (new id, occlusion): not a stop
            start, peak, before = drop
            jam = self._slowed_fraction_at(peak + cfg.jam_lag_s, (track_id,))
            if jam >= cfg.jam_fraction:
                self.suppressed["jam"] += 1
                self._fired.add(("hard_stop", (track_id,)))  # decided: do not re-evaluate
                continue
            self._fired.add(("hard_stop", (track_id,)))
            signals = {
                "speed_before": before,
                "speed_drop": 1.0 - (track.speed or 0.0) / before,
                "stopped_s": t - since,
                "others_slowed": jam,
                "vehicle_count": 1.0,
                "bus_involved": 1.0 if track.label == "bus" else 0.0,
            }
            if track.live_lane is not None:
                signals["stopped_in_lane"] = 1.0
            out.append(self._event(TriggerType.HARD_STOP, t, start, peak, (track_id,), signals))
        return out

    def _speed_drop(self, track: _Track, still_since: float) -> tuple[float, float, float] | None:
        """(t_start, t_peak, speed_before) when speed fell by > hard_stop_drop within the window.

        ``t_peak`` is the sample pair with the steepest fall.
        """
        cfg = self.config
        window = [(ts, s) for ts, s in track.speeds if still_since - cfg.hard_stop_window_s <= ts]
        before_window = [(ts, s) for ts, s in window if ts <= still_since]
        if not before_window:
            return None
        t_before, before = max(before_window, key=lambda p: p[1])
        if before < cfg.moving_speed:
            return None
        after = next((s for ts, s in track.speeds if ts >= still_since), None)
        if after is None or after > (1.0 - cfg.hard_stop_drop) * before:
            return None
        ordered = [(ts, s) for ts, s in track.speeds if ts >= t_before and ts <= still_since]
        peak = t_before
        steepest = 0.0
        for (t0, s0), (t1, s1) in pairwise(ordered):
            if t1 > t0 and (s0 - s1) / (t1 - t0) > steepest:
                steepest, peak = (s0 - s1) / (t1 - t0), (t0 + t1) / 2
        return t_before, peak, before

    def _stalled(self, t: float) -> list[TriggerEvent]:
        cfg = self.config
        out: list[TriggerEvent] = []
        for track_id, track in self._seen(t):
            since = track.still_since
            if not track.is_vehicle or since is None or not self._is_still(track):
                continue
            if track.live_lane is None or t - since < cfg.stalled_s:
                continue
            if ("stalled", (track_id,)) in self._fired:
                continue
            others = self._others(t, (track_id,))
            if others.moving < 1 or others.slowed_fraction >= cfg.jam_fraction:
                self.suppressed["jam" if others.moving else "no_traffic"] += 1
                continue  # evaluated again next frame: traffic may still flow
            self._fired.add(("stalled", (track_id,)))
            signals = {
                "stopped_in_lane": 1.0,
                "stopped_s": t - since,
                "others_moving": float(others.moving),
                "vehicle_count": 1.0,
                "bus_involved": 1.0 if track.label == "bus" else 0.0,
            }
            out.append(
                self._event(TriggerType.STALLED_VEHICLE, t, since, since, (track_id,), signals)
            )
        return out

    def _collisions(self, t: float) -> list[TriggerEvent]:
        cfg = self.config
        vehicles = [(i, tr) for i, tr in self._seen(t) if tr.is_vehicle]
        for (ia, a), (ib, b) in combinations(vehicles, 2):
            key = (min(ia, ib), max(ia, ib))
            overlap = in_contact(a.detection, b.detection, cfg)
            if overlap is None:
                continue
            contact = self._contacts.get(key)
            if contact is None or t - contact.last_t > cfg.pair_memory_s:
                contact = self._new_contact(t, key, a, b, overlap)
                self._contacts[key] = contact
            contact.last_t = t
            contact.iou = max(contact.iou, overlap)
            if t - contact.first_t <= 1.0:
                contact.pre_speed = max(contact.pre_speed, a.speed or 0.0, b.speed or 0.0)
        for key in [k for k, c in self._contacts.items() if t - c.last_t > cfg.pair_memory_s]:
            del self._contacts[key]

        out: list[TriggerEvent] = []
        for key, contact in self._contacts.items():
            first, second = (self._tracks.get(i) for i in key)
            if contact.fired or contact.static or first is None or second is None:
                continue
            if first.last_seen != t or second.last_seen != t:
                continue
            if not (self._is_still(first) and self._is_still(second)):
                continue
            assert first.still_since is not None
            assert second.still_since is not None
            joint = max(first.still_since, second.still_since)
            if joint < contact.first_t - 1.0 or t - joint < cfg.collision_still_s:
                continue
            contact.fired = True
            signals = {
                "overlap_iou": contact.iou,
                "speed_before": contact.pre_speed,
                "stopped_s": t - joint,
                "vehicle_count": 2.0,
                "bus_involved": 1.0 if "bus" in (first.label, second.label) else 0.0,
            }
            if first.live_lane is not None or second.live_lane is not None:
                signals["stopped_in_lane"] = 1.0
            out.append(
                self._event(
                    TriggerType.COLLISION_CANDIDATE,
                    t,
                    contact.first_t,
                    contact.first_t,
                    key,
                    signals,
                )
            )
        return out

    def _new_contact(
        self, t: float, key: tuple[int, int], a: _Track, b: _Track, overlap: float
    ) -> _Contact:
        """First contact of a pair: was either vehicle moving, and is traffic already slow?"""
        cfg = self.config
        recent = max(
            (s for tr in (a, b) for ts, s in tr.speeds if t - 1.5 <= ts <= t),
            default=0.0,
        )
        others = self._others(t, key)
        static = recent < cfg.moving_speed
        if not static and others.slowed_fraction >= cfg.jam_fraction:
            static = True
            self.suppressed["jam"] += 1
        return _Contact(first_t=t, last_t=t, iou=overlap, pre_speed=recent, static=static)
