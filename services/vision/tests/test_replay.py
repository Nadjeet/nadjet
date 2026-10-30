"""Clip replay through the real pipeline with fakes (doc 04 §5): alerts, verdicts, sweeps."""

from typing import Any

import pytest

from nadjet_shared import TriggerType, VerifierResult
from nadjet_vision.config import VisionSettings
from nadjet_vision.replay import replay_clip

from .test_incident_pipeline import PassThroughTracker, PersonDetector, camera, fill_ring, sampled


def settings(**kw: Any) -> VisionSettings:
    return VisionSettings(sweep_every_s=5.0, **kw)


class Verifier:
    def __init__(self, event: VerifierResult, sweeps: list[VerifierResult]) -> None:
        self.event = event
        self.sweeps = list(sweeps)
        self.event_calls: list[tuple[float, TriggerType]] = []
        self.sweep_calls: list[float] = []

    async def verify_event(self, packets: Any, info: Any, centre: float, trigger: TriggerType):  # type: ignore[no-untyped-def]
        self.event_calls.append((centre, trigger))
        return self.event

    async def sweep(self, packets: Any, info: Any, end_s: float) -> VerifierResult:
        self.sweep_calls.append(end_s)
        return self.sweeps.pop(0) if len(self.sweeps) > 1 else self.sweeps[0]


def yes(p: float = 0.9) -> VerifierResult:
    return VerifierResult(available=True, model="m", collision_visible="yes", yes_probability=p)


def no() -> VerifierResult:
    return VerifierResult(available=True, model="m", collision_visible="no", yes_probability=0.02)


async def run(verifier: Verifier | None, seconds: int = 20, **kw: Any):  # type: ignore[no-untyped-def]
    ring = fill_ring(seconds)
    frames = (sampled(i * 0.2) for i in range(seconds * 5))
    return await replay_clip(
        frames,
        camera=camera(),
        settings=settings(**kw),
        detector=PersonDetector(),
        tracker=PassThroughTracker(),
        ring=ring,
        verifier=verifier,  # type: ignore[arg-type]
    )


async def test_rule_alert_is_recorded_with_stream_times_and_the_clip_duration() -> None:
    result = await run(None, sweep_enabled=False)
    [alert] = result.alerts
    assert alert.source == "rule" and alert.trigger == "pedestrian_on_road"
    assert alert.t_fire >= 2.0 and alert.t_peak == pytest.approx(0.0)
    assert alert.verifier_available is False and alert.ai_status == "probable"
    assert result.duration_s == pytest.approx(19.8)
    assert len(result.frame_ms) == 100 and result.verify_ms == [] and result.sweep_ms == []


async def test_the_verdict_and_its_latency_are_recorded_for_the_rule_alert() -> None:
    verifier = Verifier(no(), [no()])
    result = await run(verifier, sweep_enabled=False)
    [alert] = result.alerts
    assert (alert.collision_visible, alert.ai_status, alert.verifier_available) == (
        "no",
        "possible",
        True,
    )
    assert verifier.event_calls == [(0.0, TriggerType.PEDESTRIAN_ON_ROAD)]
    assert len(result.verify_ms) == 1


async def test_verification_can_be_switched_off_for_the_rules_only_run() -> None:
    verifier = Verifier(no(), [no()])
    result = await run(verifier, sweep_enabled=False, verify_candidates=False)
    assert verifier.event_calls == []
    assert result.alerts[0].verifier_available is False


async def test_sweeps_run_every_5_s_of_stream_time_and_their_hits_become_alerts() -> None:
    verifier = Verifier(no(), [yes(), yes()])
    result = await run(verifier)
    assert verifier.sweep_calls[:3] == pytest.approx([0.0, 5.0, 10.0], abs=0.21)
    assert len(result.sweep_ms) == len(verifier.sweep_calls)
    sweeps = [a for a in result.alerts if a.source == "sweep"]
    # Hit 1 at 0 s comes before any rule alert; hit 2 at 5 s is in the cooldown the rule alert at
    # ~2 s started, and only the upgrade to `probable` may break through it.
    assert [a.ai_status for a in sweeps] == ["possible", "probable"]
    assert sweeps[0].trigger == "ai_sweep"


async def test_sweep_hits_without_a_rule_alert_start_as_possible() -> None:
    verifier = Verifier(no(), [yes(), no(), yes(), no()])
    ring = fill_ring(30)
    frames = (sampled(i * 0.2) for i in range(150))

    class Quiet(PersonDetector):
        def detect(self, frame: Any) -> list:  # type: ignore[type-arg]
            return []

    result = await replay_clip(
        frames, camera=camera(), settings=settings(), detector=Quiet(),
        tracker=PassThroughTracker(), ring=ring, verifier=verifier,  # type: ignore[arg-type]
    )  # fmt: skip
    # Hit, miss, hit: the second episode falls in the sweep's own cooldown. Never confirmed.
    assert [(a.source, a.ai_status) for a in result.alerts] == [("sweep", "possible")]


async def test_a_replay_is_repeatable() -> None:
    first = await run(Verifier(yes(), [yes(), no()]))
    second = await run(Verifier(yes(), [yes(), no()]))
    assert first.alerts == second.alerts
