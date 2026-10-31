"""Try-it worker: two-pass analysis, sandbox incident, jobs, live sessions (FR-CIT-002..005)."""

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import numpy as np
import pytest
from pydantic import SecretStr

from nadjet_shared import AiStatus, TriggerType, VerifierResult
from nadjet_shared.tryit import Box, TryJobClaim, TryResult, TrySessionRef
from nadjet_vision.config import VisionSettings
from nadjet_vision.detect import Detection
from nadjet_vision.evidence import plan_clip, write_clip
from nadjet_vision.status import StatusThresholds
from nadjet_vision.tryit import (
    ClipRejected,
    SandboxPublisher,
    TryApi,
    analyse_clip,
    build_incident,
    damped_time,
    job_loop,
    live_watcher,
    probe_clip,
    process_job,
    report_ai_loop,
    snap_vehicles,
    verdict_label,
)

from .conftest import StreamFactory
from .test_incident_pipeline import PassThroughTracker

TH = StatusThresholds()


def det(x: float, label: str = "car", y: float = 100) -> Detection:
    return Detection((x, y, x + 40, y + 30), 3, label, 0.9)


def yes(t_contact: float | None = 3.0, p: float = 0.9, n: int | None = 2) -> VerifierResult:
    return VerifierResult(
        available=True, model="m", collision_visible="yes", yes_probability=p,
        t_contact=t_contact, vehicles_involved=n, description_fr="Deux voitures.",
    )  # fmt: skip


def no() -> VerifierResult:
    return VerifierResult(available=True, model="m", collision_visible="no", yes_probability=0.02)


# ---------------------------------------------------------------- pure logic


@pytest.mark.parametrize(
    ("scan", "refine", "expected"),
    [
        (10.0, None, 10.0),  # no second look: pass 1 stands
        (10.0, 11.0, 10.35),  # damped x0.35
        (10.0, 9.0, 9.65),
        (10.0, 20.0, 11.5),  # capped at +1.5 s
        (10.0, -20.0, 8.5),  # and at -1.5 s
        (10.0, 10.0, 10.0),
    ],
)
def test_the_pass_2_correction_is_damped_and_capped(
    scan: float, refine: float | None, expected: float
) -> None:
    assert damped_time(scan, refine) == pytest.approx(expected)


def test_the_detector_only_snaps_the_answer_onto_the_vehicles_closest_together() -> None:
    boxes = [det(0), det(500), det(520), det(900), det(300, "person")]
    snapped = snap_vehicles(boxes, 2)
    assert sorted(d.box[0] for d in snapped) == [500, 520]
    assert all(d.label != "person" for d in snap_vehicles(boxes, 5))
    three = snap_vehicles(boxes, 3)
    assert len(three) == 3 and {500, 520} <= {d.box[0] for d in three}
    assert snap_vehicles([det(0)], 2) == [det(0)]  # fewer than asked: all of them
    assert snap_vehicles([], 2) == []


def test_verdict_labels() -> None:
    assert verdict_label(yes()) == "collision visible"
    assert verdict_label(no()) == "no collision visible"
    assert verdict_label(VerifierResult(available=False)) == "AI unavailable"


def incident(**kw: Any):  # type: ignore[no-untyped-def]
    data: dict[str, Any] = dict(
        triggers=[], scan=None, refine=None, event_t=None, vehicles=[], thresholds=TH
    )
    data.update(kw)
    return build_incident(**data)


def test_no_rule_and_no_ai_hit_means_no_sandbox_incident() -> None:
    assert incident() is None
    assert incident(scan=no(), triggers=[(TriggerType.STALLED_VEHICLE, 5.0)]) is None


def test_the_ai_alone_never_confirms_a_collision() -> None:
    found = incident(scan=yes(), refine=yes(p=0.99), event_t=3.1)
    assert found is not None
    assert (found.type, found.ai_status, found.trigger) == (
        "possible_incident", AiStatus.POSSIBLE, None,
    )  # fmt: skip
    assert found.description_fr == "Deux voitures."


def test_a_collision_rule_with_a_confident_ai_confirms() -> None:
    found = incident(
        triggers=[(TriggerType.COLLISION_CANDIDATE, 3.5)],
        scan=yes(),
        refine=yes(p=0.95),
        event_t=3.1,
    )
    assert found is not None
    assert (found.type, found.ai_status, found.trigger) == (
        "collision", AiStatus.CONFIRMED, "collision_candidate",
    )  # fmt: skip


def test_a_rule_far_from_the_ai_moment_does_not_count_for_the_status() -> None:
    found = incident(
        triggers=[(TriggerType.HARD_STOP, 40.0)], scan=yes(), refine=yes(p=0.95), event_t=3.1
    )
    assert found is not None and found.ai_status is AiStatus.POSSIBLE and found.trigger is None


def test_rules_alone_when_the_ai_is_unavailable_give_a_probable_possible_incident() -> None:
    down = VerifierResult(available=False)
    found = incident(triggers=[(TriggerType.COLLISION_CANDIDATE, 4.0)], scan=down)
    assert found is not None
    assert (found.type, found.ai_status, found.event_time_s) == (
        "possible_incident", AiStatus.PROBABLE, 4.0,
    )  # fmt: skip


def test_rule_fires_and_ai_says_no_is_possible_with_both_visible() -> None:
    found = incident(triggers=[(TriggerType.HARD_STOP, 4.0)], scan=no())
    assert found is not None
    assert (found.ai_status, found.trigger) == (AiStatus.POSSIBLE, "hard_stop")


# ---------------------------------------------------------------- clip analysis


def video_file(tmp_path: Path, factory: StreamFactory, seconds: int = 12) -> Path:
    packets, info = factory(seconds=seconds)
    plan = plan_clip(packets, packets[-1].pts_s, before_s=seconds, after_s=0)
    assert plan is not None
    path = tmp_path / "clip.mp4"
    write_clip(plan, info, path)
    return path


class Detector:
    model_id = "fake-detector"

    def detect(self, frame: Any) -> list[Detection]:
        return [det(10), det(60), det(400)]


class Ai:
    def __init__(self, scan: VerifierResult, refine: VerifierResult | None = None) -> None:
        self.scan_result, self.refine_result = scan, refine
        self.calls: list[tuple[str, float]] = []

    async def scan(self, packets: Any, info: Any, start: float, end: float) -> VerifierResult:
        self.calls.append(("scan", end - start))
        return self.scan_result

    async def verify_event(self, packets: Any, info: Any, centre: float, trigger: Any):  # type: ignore[no-untyped-def]
        self.calls.append(("refine", centre))
        assert self.refine_result is not None
        return self.refine_result


async def analyse(path: Path, tmp_path: Path, ai: Ai | None) -> Any:
    stages: list[tuple[str, float]] = []
    outcome = await analyse_clip(
        path, tmp_path / "out.mp4",
        settings=VisionSettings(), detector=Detector(), tracker=PassThroughTracker(),
        verifier=ai,  # type: ignore[arg-type]
        report=lambda stage, p: stages.append((stage, p)),
        draw_frame=lambda image, tracked, speeds, zones: image,
    )  # fmt: skip
    return outcome, stages


async def test_AC_CIT_002_1_two_passes_give_annotated_video_timeline_and_verdict(
    tmp_path: Path, synthetic_stream: StreamFactory
) -> None:
    ai = Ai(yes(t_contact=3.0), yes(t_contact=0.4, p=0.92))
    outcome, stages = await analyse(video_file(tmp_path, synthetic_stream), tmp_path, ai)
    result = outcome.result
    assert outcome.video is not None and outcome.video.stat().st_size > 0
    assert result.frames_analysed > 40 and result.duration_s == pytest.approx(11.8, abs=0.6)
    assert result.ai_available and result.scan and result.refine
    assert result.scan_t_s == pytest.approx(3.0, abs=0.2)
    assert result.event_t_s == pytest.approx(3.0 + 0.35 * 0.4, abs=0.2)  # damped
    assert [c[0] for c in ai.calls] == ["scan", "refine"]  # pass 1 whole clip, then pass 2
    kinds = [t.kind for t in result.timeline]
    assert "ai_scan" in kinds and "ai_refine" in kinds
    assert all(t.source for t in result.timeline)  # every AI value carries its source
    incident = result.sandbox_incident
    assert incident is not None and incident.type == "possible_incident"
    assert len(incident.vehicles) == 2  # snapped onto 2 of the 3 detected vehicles
    assert sorted(b.x1 for b in incident.vehicles) == [10, 60]
    names = [s[0] for s in stages]
    assert names[0] == "detect" and "ai_scan" in names and "ai_refine" in names
    assert result.models["detector"] == "fake-detector"


async def test_when_pass_1_sees_no_collision_there_is_no_second_pass_and_no_incident(
    tmp_path: Path, synthetic_stream: StreamFactory
) -> None:
    ai = Ai(no())
    outcome, _ = await analyse(video_file(tmp_path, synthetic_stream), tmp_path, ai)
    assert [c[0] for c in ai.calls] == ["scan"]
    assert outcome.result.ai_available and outcome.result.refine is None
    assert outcome.result.sandbox_incident is None and outcome.result.event_t_s is None


async def test_FR_CIT_005_without_the_ai_the_rule_based_analysis_is_still_returned(
    tmp_path: Path, synthetic_stream: StreamFactory
) -> None:
    ai = Ai(VerifierResult(available=False, model="m"))
    outcome, _ = await analyse(video_file(tmp_path, synthetic_stream), tmp_path, ai)
    result = outcome.result
    assert result.ai_available is False and result.refine is None
    assert outcome.video is not None and result.frames_analysed > 40  # boxes still drawn
    none = await analyse(video_file(tmp_path, synthetic_stream), tmp_path, None)
    assert none[0].result.ai_available is False  # no verifier at all: same honest answer


def test_E_12_unusable_videos_are_rejected_before_analysis(
    tmp_path: Path, synthetic_stream: StreamFactory
) -> None:
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"this is not a video" * 100)
    with pytest.raises(ClipRejected, match="could not be read"):
        probe_clip(junk)
    ok = video_file(tmp_path, synthetic_stream, seconds=12)
    assert probe_clip(ok) == pytest.approx(12.0, abs=1.0)
    with pytest.raises(ClipRejected, match="Longer than 10 s"):
        probe_clip(ok, max_seconds=10)


# ---------------------------------------------------------------- jobs through the API client


class FakeApi:
    """The API as the worker sees it: records calls, serves one clip."""

    def __init__(self, source: Path | bytes, queue: list[TryJobClaim] | None = None) -> None:
        self.source = source
        self.queue = list(queue or [])
        self.log: list[tuple[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/internal/try")
        self.log.append((f"{request.method} {path}", request.content[:0] or None))
        if path == "/claim":
            if not self.queue:
                return httpx.Response(204)
            return httpx.Response(200, json=self.queue.pop(0).model_dump())
        if path.endswith("/file"):
            data = self.source if isinstance(self.source, bytes) else self.source.read_bytes()
            return httpx.Response(200, content=data)
        if path.endswith("/result") or path.endswith("/fail"):
            self.log[-1] = (self.log[-1][0], json.loads(request.content))
        return httpx.Response(204)


def api_for(fake: FakeApi) -> TryApi:
    settings = VisionSettings(ingest_token=SecretStr("t"))
    return TryApi(settings, transport=httpx.MockTransport(fake.handler))


async def run_job(fake: FakeApi, ai: Ai | None) -> None:
    await process_job(
        api_for(fake), TryJobClaim(id="job-1", filename="a.mp4"),
        settings=VisionSettings(), detector=Detector(), make_tracker=PassThroughTracker,
        verifier=ai,  # type: ignore[arg-type]
        draw_frame=lambda image, tracked, speeds, zones: image,
    )  # fmt: skip


async def test_a_job_is_downloaded_analysed_and_its_video_and_result_are_posted(
    tmp_path: Path, synthetic_stream: StreamFactory
) -> None:
    fake = FakeApi(video_file(tmp_path, synthetic_stream))
    await run_job(fake, Ai(yes(), yes(0.3)))
    calls = [c[0] for c in fake.log]
    assert calls[0] == "GET /jobs/job-1/file"
    assert "POST /jobs/job-1/progress" in calls
    assert calls.index("PUT /jobs/job-1/video") < calls.index("POST /jobs/job-1/result")
    result = dict(fake.log)["POST /jobs/job-1/result"]
    assert result["ai_available"] is True and result["sandbox_incident"]["type"]


async def test_an_unreadable_upload_is_reported_as_rejected_not_as_an_error() -> None:
    fake = FakeApi(b"not a video at all" * 50)
    await run_job(fake, None)
    body = dict(fake.log)["POST /jobs/job-1/fail"]
    assert body["rejected"] is True and "could not be read" in body["error"]
    assert not any(c[0].endswith("/result") for c in fake.log)


async def test_an_unexpected_crash_fails_the_job_with_a_plain_message(
    tmp_path: Path, synthetic_stream: StreamFactory
) -> None:
    class Boom(Detector):
        def detect(self, frame: Any) -> list[Detection]:
            raise RuntimeError("gpu on fire")

    fake = FakeApi(video_file(tmp_path, synthetic_stream))
    await process_job(
        api_for(fake), TryJobClaim(id="job-1", filename="a.mp4"),
        settings=VisionSettings(), detector=Boom(), make_tracker=PassThroughTracker,
        verifier=None, draw_frame=lambda image, tracked, speeds, zones: image,
    )  # fmt: skip
    body = dict(fake.log)["POST /jobs/job-1/fail"]
    assert body == {"error": "The analysis failed", "rejected": False}


async def test_the_job_loop_polls_until_stopped_and_survives_an_unreachable_api(
    tmp_path: Path, synthetic_stream: StreamFactory
) -> None:
    fake = FakeApi(video_file(tmp_path, synthetic_stream), [TryJobClaim(id="job-1", filename="a")])
    flaky = {"n": 0}
    inner = fake.handler

    def handler(request: httpx.Request) -> httpx.Response:
        flaky["n"] += 1
        if flaky["n"] == 1:
            raise httpx.ConnectError("down", request=request)
        return inner(request)

    settings = VisionSettings(ingest_token=SecretStr("t"), try_poll_s=0.01)
    api = TryApi(settings, transport=httpx.MockTransport(handler))
    stop = asyncio.Event()
    task = asyncio.create_task(
        job_loop(
            api, stop, settings=settings, detector=Detector(), make_tracker=PassThroughTracker,
            verifier=None, draw_frame=lambda image, tracked, speeds, zones: image,
        )
    )  # fmt: skip
    for _ in range(300):
        if any(c[0].endswith("/result") for c in fake.log):
            break
        await asyncio.sleep(0.02)
    stop.set()
    await asyncio.wait_for(task, 5)
    assert any(c[0] == "POST /jobs/job-1/result" for c in fake.log)


async def test_the_worker_tells_the_api_whether_the_ai_answers() -> None:
    fake = FakeApi(b"")
    reported: list[bool] = []
    inner = fake.handler

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/status"):
            reported.append(json.loads(request.content)["ai_available"])
        return inner(request)

    class Client:
        def __init__(self) -> None:
            self.up = [True, False]

        async def check(self) -> str:
            if not self.up.pop(0):
                raise RuntimeError("vLLM stopped")
            return "m"

    client = Client()
    api = TryApi(
        VisionSettings(ingest_token=SecretStr("t")), transport=httpx.MockTransport(handler)
    )
    stop = asyncio.Event()
    task = asyncio.create_task(report_ai_loop(api, client, stop, every_s=0.01))
    while len(reported) < 2:  # noqa: ASYNC110
        await asyncio.sleep(0.01)
    stop.set()
    await task
    assert reported[:2] == [True, False]  # "AI unavailable" shows when vLLM is stopped


# ---------------------------------------------------------------- live phone sessions


class SessionsApi:
    def __init__(self, sessions: list[TrySessionRef]) -> None:
        self.sessions = sessions
        self.events: list[dict[str, Any]] = []
        self.paths: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        if request.url.path.endswith("/sessions") and request.method == "GET":
            return httpx.Response(200, json=[s.model_dump() for s in self.sessions])
        if request.url.path.endswith("/events"):
            self.events.append(json.loads(request.content))
        return httpx.Response(204)


async def test_a_worker_attaches_to_each_phone_session_and_detaches_when_it_leaves() -> None:
    sessions = SessionsApi([TrySessionRef(id="s1", path="live/abcd1234")])
    settings = VisionSettings(ingest_token=SecretStr("t"), try_poll_s=0.01, live_check_s=4.0)
    api = TryApi(settings, transport=httpx.MockTransport(sessions.handler))
    started: list[dict[str, Any]] = []
    stopped = asyncio.Event()

    async def runner(
        camera_id: str, live_settings: VisionSettings, stop: asyncio.Event, **kw: Any
    ) -> None:
        started.append({"camera_id": camera_id, "settings": live_settings, **kw})
        await stop.wait()
        stopped.set()

    stop = asyncio.Event()
    task = asyncio.create_task(
        live_watcher(
            api, stop, settings=settings, detector=Detector(), make_tracker=PassThroughTracker,
            verifier=None, run_session=runner,
        )
    )  # fmt: skip
    for _ in range(200):
        if started:
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)
    assert len(started) == 1  # attached once, not on every poll
    first = started[0]
    assert first["camera_id"] == "live-abcd1234" and first["stream_path"] == "live/abcd1234"
    assert first["push_health"] is False  # a phone is not in the camera registry
    assert first["settings"].sweep_every_s == 4.0 and first["settings"].sweep_enabled
    assert first["on_check"] is not None and isinstance(first["sink"], SandboxPublisher)

    sessions.sessions.clear()  # the phone left
    await asyncio.wait_for(stopped.wait(), 5)
    stop.set()
    await asyncio.wait_for(task, 5)


async def test_live_results_go_to_the_session_and_never_to_the_incident_queue() -> None:
    sessions = SessionsApi([])
    settings = VisionSettings(ingest_token=SecretStr("t"))
    api = TryApi(settings, transport=httpx.MockTransport(sessions.handler))
    loop = asyncio.get_running_loop()
    sink = SandboxPublisher(settings, loop, api, "s1", verifier=None)
    sink.record_check(no(), 0.0)
    sink.record_check(VerifierResult(available=False), 0.0)
    from nadjet_vision.publish import build_candidate
    from nadjet_vision.triggers import TriggerEvent

    from .test_publish import camera, event

    ev: TriggerEvent = event()
    sink.publish_candidate(build_candidate(camera(), ev), "k")
    sink.submit_evidence("k", ev, [], None)  # no evidence of a sandbox stream
    await sink.aclose()
    labels = [e["label"] for e in sessions.events]
    assert labels == ["no collision visible", "AI unavailable", "collision_candidate"]
    assert [e["kind"] for e in sessions.events] == ["ai_check", "ai_check", "trigger"]
    assert all(e["source"] for e in sessions.events)
    assert not any("candidates" in p or "evidence" in p for p in sessions.paths)
    assert np.array_equal(np.zeros(1), np.zeros(1))  # (keeps numpy import used by the module tests)
    assert Box(x1=0, y1=0, x2=1, y2=1, label="car").track_id is None


def test_E_12_a_clip_without_a_header_duration_is_cut_while_decoding(
    tmp_path: Path, synthetic_stream: StreamFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fragmented MP4 or WebM may report no duration: the length limit holds on the decoded
    stream, so a 2 h file cannot hold the job loop."""
    from nadjet_vision import tryit

    monkeypatch.setattr(tryit, "MAX_CLIP_S", 5.0)
    clip = video_file(tmp_path, synthetic_stream, seconds=12)
    with pytest.raises(ClipRejected, match="Longer than 5 s"):
        tryit.detect_pass(
            clip,
            settings=VisionSettings(),
            detector=Detector(),
            tracker=PassThroughTracker(),
            ring=tryit.PacketRing(window_s=60, max_packets=2000),
            video_path=tmp_path / "out.mp4",
            on_progress=lambda _p: None,
            duration_s=0.0,
            draw_frame=lambda image, tracked, speeds, zones: image,
        )


async def test_FR_CIT_002_result_post_is_retried_when_the_connection_drops() -> None:
    """A pooled connection the API had closed dropped the result post ("Server disconnected
    without sending a response") and failed one upload in three on the live run."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if len(calls) == 1:
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
        return httpx.Response(204)

    api = TryApi(
        VisionSettings(ingest_token=SecretStr("t")), transport=httpx.MockTransport(handler)
    )
    with patch("nadjet_vision.tryit.SEND_RETRY_DELAYS_S", (0.0, 0.0)):
        await api.result(
            "job-1", TryResult(duration_s=30.0, frames_analysed=150, ai_available=True)
        )
    assert calls == ["/internal/try/jobs/job-1/result"] * 2


async def test_FR_CIT_002_result_post_gives_up_after_the_retries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    api = TryApi(
        VisionSettings(ingest_token=SecretStr("t")), transport=httpx.MockTransport(handler)
    )
    with (
        patch("nadjet_vision.tryit.SEND_RETRY_DELAYS_S", (0.0,)),
        pytest.raises(httpx.ConnectError),
    ):
        await api.result(
            "job-1", TryResult(duration_s=30.0, frames_analysed=150, ai_available=True)
        )
