"""AI sweep: hits, consecutive upgrade, cooldown, backlog skip, never a collision (FR-VIS-015)."""

import asyncio
from typing import Any

import pytest

from nadjet_shared import AiStatus, IncidentCandidate, TriggerType, VerifierResult
from nadjet_vision.ingest import Packet, PacketRing, StreamInfo
from nadjet_vision.sweep import Sweeper, SweepTracker, sweep_event
from nadjet_vision.triggers import TriggerEvent

from .test_incident_pipeline import camera

INFO = StreamInfo("h264", 160, 90, b"", 90000)


def yes(p: float = 0.9, t_contact: float | None = -3.0) -> VerifierResult:
    return VerifierResult(
        available=True, model="m", collision_visible="yes", yes_probability=p, t_contact=t_contact
    )


def no() -> VerifierResult:
    return VerifierResult(available=True, model="m", collision_visible="no", yes_probability=0.05)


class FakeVerifier:
    def __init__(self, *results: VerifierResult, gate: asyncio.Event | None = None) -> None:
        self.results = list(results)
        self.gate = gate
        self.calls: list[float] = []

    async def sweep(self, packets: Any, info: Any, end_s: float) -> VerifierResult:
        self.calls.append(end_s)
        if self.gate is not None:
            await self.gate.wait()
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]


class Sink:
    def __init__(self) -> None:
        self.candidates: list[tuple[IncidentCandidate, str]] = []
        self.evidence: list[tuple[str, TriggerEvent]] = []

    def publish_candidate(
        self, candidate: IncidentCandidate, key: str, verify: object = None
    ) -> None:
        self.candidates.append((candidate, key))

    def submit_evidence(self, key: str, event: TriggerEvent, packets: Any, info: Any) -> None:
        self.evidence.append((key, event))


def ring() -> PacketRing:
    r = PacketRing(window_s=20)
    r.stream = INFO
    for t in range(0, 300):
        r.append(Packet(t / 10, t % 20 == 0, b"x"))
    return r


def sweeper(verifier: FakeVerifier, sink: Sink, **kwargs: Any) -> Sweeper:
    return Sweeper(
        camera(),
        verifier,
        sink,
        asyncio.get_running_loop(),
        **kwargs,  # type: ignore[arg-type]
    )


async def settle(sw: Sweeper) -> None:
    while sw._running or sw._futures:  # noqa: ASYNC110
        await asyncio.sleep(0.005)


def test_tracker_counts_consecutive_hits_and_resets() -> None:
    tracker = SweepTracker(0.5)
    assert [tracker.record(r) for r in (yes(), yes(), no(), yes())] == [1, 2, 0, 1]


@pytest.mark.parametrize("result", [yes(0.4), VerifierResult(available=False), no()])
def test_below_threshold_unavailable_or_no_is_not_a_hit(result: VerifierResult) -> None:
    assert not SweepTracker(0.5).is_hit(result)


def test_sweep_event_places_the_impact_inside_the_window() -> None:
    event = sweep_event(yes(t_contact=-3.0), end_s=30.0, wall=1000.0, hits=1)
    assert event.trigger is TriggerType.AI_SWEEP
    assert event.t_peak == pytest.approx(27.0)
    assert event.peak_wall == pytest.approx(997.0)
    assert event.fire_wall == 1000.0
    assert event.track_ids == ()
    assert event.signals["sweep_yes_probability"] == 0.9
    outside = sweep_event(yes(t_contact=5.0), 30.0, 1000.0, 1)
    assert outside.t_peak == 30.0  # an impossible contact time is not trusted
    assert sweep_event(yes(t_contact=None), 30.0, 1000.0, 1).t_peak == 30.0


async def test_AC_VIS_015_1_a_sweep_hit_is_possible_never_a_collision() -> None:
    sink = Sink()
    sw = sweeper(FakeVerifier(yes(0.99)), sink)
    assert sw.maybe_start(30.0, 1000.0, ring())
    await settle(sw)
    [(candidate, key)] = sink.candidates
    assert candidate.trigger is TriggerType.AI_SWEEP
    assert candidate.ai_status is AiStatus.POSSIBLE  # not confirmed, even at 0.99
    assert candidate.verifier.collision_visible == "yes"
    assert candidate.signals["sweep_consecutive_hits"] == 1.0
    assert candidate.track_ids == []
    assert sink.evidence[0][0] == key


async def test_a_second_consecutive_hit_upgrades_to_probable_even_in_cooldown() -> None:
    sink = Sink()
    sw = sweeper(FakeVerifier(yes(), yes()), sink)
    sw.maybe_start(30.0, 1000.0, ring())
    await settle(sw)
    sw.maybe_start(35.0, 1005.0, ring())
    await settle(sw)
    assert [c.ai_status for c, _ in sink.candidates] == [AiStatus.POSSIBLE, AiStatus.PROBABLE]
    assert sink.candidates[0][1] != sink.candidates[1][1]


async def test_a_third_hit_inside_the_cooldown_is_quiet() -> None:
    sink = Sink()
    sw = sweeper(FakeVerifier(yes()), sink)
    for i in range(3):
        sw.maybe_start(30.0 + 5 * i, 1000.0 + 5 * i, ring())
        await settle(sw)
    assert len(sink.candidates) == 2  # first hit, then the upgrade; hit 3 is a repeat


async def test_a_miss_in_between_restarts_the_count() -> None:
    sink = Sink()
    sw = sweeper(FakeVerifier(yes(), no(), yes()), sink, cooldown_s=0.0)
    for i in range(3):
        sw.maybe_start(30.0 + 5 * i, 1000.0 + 5 * i, ring())
        await settle(sw)
    assert [c.ai_status for c, _ in sink.candidates] == [AiStatus.POSSIBLE, AiStatus.POSSIBLE]


async def test_a_first_hit_during_the_rule_cooldown_is_suppressed() -> None:
    sink = Sink()
    sw = sweeper(FakeVerifier(yes()), sink, rule_cooling_down=lambda wall: True)
    sw.maybe_start(30.0, 1000.0, ring())
    await settle(sw)
    assert not sink.candidates


async def test_after_the_cooldown_a_new_episode_is_reported_again() -> None:
    sink = Sink()
    sw = sweeper(FakeVerifier(yes(), no(), yes()), sink, cooldown_s=60.0)
    for i, wall in enumerate((1000.0, 1005.0, 1200.0)):
        sw.maybe_start(30.0 + 5 * i, wall, ring())
        await settle(sw)
    assert len(sink.candidates) == 2


async def test_a_sweep_is_skipped_while_the_previous_one_still_runs() -> None:
    gate = asyncio.Event()
    verifier = FakeVerifier(no(), gate=gate)
    sw = sweeper(verifier, Sink())
    assert sw.maybe_start(30.0, 1000.0, ring())
    assert not sw.maybe_start(36.0, 1006.0, ring())  # due, but busy
    assert sw.skipped_busy == 1
    gate.set()
    await settle(sw)
    assert sw.maybe_start(41.0, 1011.0, ring())
    await settle(sw)
    assert verifier.calls == [30.0, 41.0]


async def test_sweeps_start_at_the_configured_interval_only() -> None:
    verifier = FakeVerifier(no())
    sw = sweeper(verifier, Sink())
    assert sw.maybe_start(30.0, 1000.0, ring())
    await settle(sw)
    assert not sw.maybe_start(33.0, 1003.0, ring())
    assert sw.maybe_start(35.0, 1005.0, ring())
    await settle(sw)


async def test_no_sweep_until_the_ring_holds_video() -> None:
    sw = sweeper(FakeVerifier(no()), Sink())
    empty = PacketRing()
    assert not sw.maybe_start(30.0, 1000.0, empty)
    empty.stream = INFO
    assert not sw.maybe_start(30.0, 1000.0, empty)  # no packets yet


async def test_a_failing_verifier_does_not_stop_later_sweeps() -> None:
    class Boom(FakeVerifier):
        async def sweep(self, packets: Any, info: Any, end_s: float) -> VerifierResult:
            raise RuntimeError("boom")

    sw = sweeper(Boom(), Sink())
    sw.maybe_start(30.0, 1000.0, ring())
    await settle(sw)
    assert sw.maybe_start(35.0, 1005.0, ring())
