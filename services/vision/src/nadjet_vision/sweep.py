"""AI sweep: every few seconds ask the verifier about the last 8 s of a camera (FR-VIS-015).

Catches crashes the rules miss (single-vehicle crashes, rollovers). A sweep never makes a
``collision``: its candidate is ``possible``, or ``probable`` on two consecutive hits (doc 11 §6).
A sweep is skipped while the previous one of that camera still runs (backlog protection) and
stays quiet during the rule cooldown, except for the second consecutive hit that upgrades the
incident the first one made.
"""

import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field

from nadjet_shared import IncidentCandidate, TriggerType, VerifierResult
from nadjet_shared.catalogue import Camera
from nadjet_vision.clipvideo import SWEEP_WINDOW_S
from nadjet_vision.ingest import Packet, PacketRing, StreamInfo
from nadjet_vision.publish import IncidentSink, build_candidate, candidate_key
from nadjet_vision.status import StatusThresholds, classify
from nadjet_vision.triggers import TriggerEvent
from nadjet_vision.verifier import AiVerifier

log = logging.getLogger("nadjet_vision.sweep")


@dataclass
class SweepTracker:
    """Consecutive sweep hits (pure state)."""

    yes_threshold: float = 0.5
    consecutive: int = 0

    def is_hit(self, result: VerifierResult) -> bool:
        return (
            result.available
            and result.collision_visible == "yes"
            and (result.yes_probability or 0.0) >= self.yes_threshold
        )

    def record(self, result: VerifierResult) -> int:
        """Hits in a row including this window (0 when it is not a hit)."""
        self.consecutive = self.consecutive + 1 if self.is_hit(result) else 0
        return self.consecutive


def should_emit(hits: int, cooling_down: bool) -> bool:
    """A sweep hit is published unless it falls in a cooldown; only the second hit in a row
    (the upgrade to `probable`) may break through it."""
    return not cooling_down or hits == 2


def sweep_event(result: VerifierResult, end_s: float, wall: float, hits: int) -> TriggerEvent:
    """Event of a sweep hit. ``t_contact`` is relative to the window end (stream seconds)."""
    contact = result.t_contact
    peak = end_s + contact if contact is not None and -SWEEP_WINDOW_S <= contact <= 0 else end_s
    return TriggerEvent(
        trigger=TriggerType.AI_SWEEP,
        t_start=end_s - SWEEP_WINDOW_S,
        t_peak=peak,
        t_fire=end_s,
        evidence_t=peak,
        track_ids=(),
        signals={
            "sweep_yes_probability": result.yes_probability or 0.0,
            "sweep_consecutive_hits": float(hits),
        },
        peak_wall=wall - (end_s - peak),
        fire_wall=wall,
    )


@dataclass
class Sweeper:
    """Schedules sweeps from the analysis thread and publishes their hits."""

    camera: Camera
    verifier: AiVerifier
    sink: IncidentSink
    loop: asyncio.AbstractEventLoop
    every_s: float = 5.0
    cooldown_s: float = 120.0
    tracker: SweepTracker = field(default_factory=SweepTracker)
    thresholds: StatusThresholds = field(default_factory=StatusThresholds)
    rule_cooling_down: Callable[[float], bool] = lambda wall: False
    skipped_busy: int = 0
    _last_start: float | None = None
    _running: bool = False
    _last_emit_wall: float | None = None
    _futures: set[Future[None]] = field(default_factory=set)

    def maybe_start(self, pts_s: float, wall: float, ring: PacketRing) -> bool:
        """Start a sweep ending at ``pts_s`` if one is due and none is running."""
        if self._last_start is not None and 0 <= pts_s - self._last_start < self.every_s:
            return False
        if ring.stream is None or ring.duration_s() < SWEEP_WINDOW_S / 2:
            return False
        if self._running:
            self.skipped_busy += 1
            return False
        self._last_start = pts_s
        self._running = True
        future: Future[None] = asyncio.run_coroutine_threadsafe(
            self._run(pts_s, wall, ring.snapshot(), ring.stream), self.loop
        )
        self._futures.add(future)
        future.add_done_callback(self._futures.discard)
        return True

    async def _run(
        self, end_s: float, wall: float, packets: list[Packet], info: StreamInfo
    ) -> None:
        try:
            result = await self.verifier.sweep(packets, info, end_s)
            hits = self.tracker.record(result)
            if hits:
                self._emit(result, end_s, wall, hits, packets, info)
        except Exception:
            log.exception("sweep failed")
        finally:
            self._running = False

    def _emit(
        self,
        result: VerifierResult,
        end_s: float,
        wall: float,
        hits: int,
        packets: list[Packet],
        info: StreamInfo,
    ) -> None:
        cooling = self.rule_cooling_down(wall) or (
            self._last_emit_wall is not None and wall - self._last_emit_wall < self.cooldown_s
        )
        if not should_emit(hits, cooling):
            log.info("camera=%s sweep hit suppressed by cooldown", self.camera.id)
            return
        event = sweep_event(result, end_s, wall, hits)
        status = classify(
            rule_fired=False,
            verifier=result,
            consecutive_sweep_hits=hits,
            thresholds=self.thresholds,
        )
        candidate: IncidentCandidate = build_candidate(
            self.camera, event, verifier=result, ai_status=status
        )
        key = candidate_key(self.camera.id, event)
        self._last_emit_wall = wall
        log.info("camera=%s sweep hit %d status=%s", self.camera.id, hits, status.value)
        self.sink.publish_candidate(candidate, key)
        self.sink.submit_evidence(key, event, packets, info)
