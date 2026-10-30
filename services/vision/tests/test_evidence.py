"""Evidence clip planning, stream-copy muxing and keyframes (FR-VIS-005, TD-16)."""

from pathlib import Path

import av
import pytest

from nadjet_vision.evidence import (
    JPEG_MAGIC,
    build_evidence,
    keyframe_times,
    plan_clip,
    sha256_hex,
)
from nadjet_vision.ingest import Packet

from .conftest import StreamFactory

FPS = 10


def bare(seconds: int, keyframe_every: int = 2) -> list[Packet]:
    return [Packet(float(t), t % keyframe_every == 0, b"x") for t in range(seconds)]


def test_plan_starts_on_the_last_keyframe_at_least_before_s_ahead_of_the_peak() -> None:
    plan = plan_clip(bare(30), peak_pts=20.0, before_s=10.0, after_s=5.0)
    assert plan is not None
    assert plan.packets[0].keyframe
    assert plan.start_pts == 10.0
    assert plan.pre_s >= 10.0
    assert plan.post_s == 5.0


def test_plan_starts_before_the_window_when_keyframes_are_sparse() -> None:
    packets = [Packet(float(t), t in (0, 7), b"x") for t in range(30)]
    plan = plan_clip(packets, peak_pts=20.0)
    assert plan is not None
    assert plan.start_pts == 7.0
    assert plan.pre_s == 13.0


def test_plan_reports_a_short_pre_roll_instead_of_inventing_footage() -> None:
    plan = plan_clip(bare(30), peak_pts=4.0)
    assert plan is not None
    assert plan.start_pts == 0.0
    assert plan.pre_s == 4.0  # honest: less than the 10 s wanted


def test_plan_reports_a_short_post_roll_when_the_stream_ends_early() -> None:
    plan = plan_clip(bare(12), peak_pts=10.0)
    assert plan is not None
    assert plan.post_s == 1.0


def test_plan_needs_a_keyframe_before_the_peak() -> None:
    assert plan_clip([Packet(5.0, True, b"x")], peak_pts=1.0) is None
    assert plan_clip([], peak_pts=1.0) is None


def test_plan_follows_decode_order_with_reordered_timestamps() -> None:
    packets = [
        Packet(0.0, True, b"i", 0.0),
        Packet(0.3, False, b"p", 0.1),
        Packet(0.1, False, b"b", 0.2),
        Packet(0.2, False, b"b", 0.3),
        Packet(6.0, False, b"p", 5.0),
        Packet(5.1, False, b"b", 5.5),
    ]
    plan = plan_clip(packets, peak_pts=0.0, before_s=0.0, after_s=5.0)
    assert plan is not None
    assert [p.data for p in plan.packets] == [b"i", b"p", b"b", b"b", b"p"]


def test_keyframe_times_cover_the_peak_symmetrically() -> None:
    times = keyframe_times(12.0, count=6, span_s=2.0)
    assert len(times) == 6
    assert times[0] == pytest.approx(10.0)
    assert times[-1] == pytest.approx(14.0)
    assert keyframe_times(3.0, count=1) == [3.0]


def test_clip_is_a_stream_copy_with_six_jpeg_keyframes(
    tmp_path: Path, synthetic_stream: StreamFactory
) -> None:
    packets, info = synthetic_stream()
    peak = 14.0
    result = build_evidence(packets, info, peak, tmp_path)
    assert result is not None
    assert result.plan.pre_s >= 10.0
    assert result.plan.post_s >= 5.0 - 1 / FPS

    with av.open(str(result.clip)) as container:
        stream = container.streams.video[0]
        assert stream.codec_context.name == "h264"
        copied = [bytes(p) for p in container.demux(stream) if p.size]
    assert len(copied) == len(result.plan.packets)
    # Stream copy: the muxer only rewrites NAL framing and parameter sets; a re-encode would
    # change the byte count by far more than this.
    original = sum(len(p.data) for p in result.plan.packets)
    assert abs(sum(map(len, copied)) - original) < 0.03 * original

    with av.open(str(result.clip)) as container:
        frames = list(container.decode(video=0))
    assert len(frames) == len(result.plan.packets)

    assert len(result.keyframes) == 6
    for path in result.keyframes:
        assert path.read_bytes().startswith(JPEG_MAGIC)
    assert set(result.sha256) == {"clip.mp4", *(p.name for p in result.keyframes)}
    assert result.sha256["clip.mp4"] == sha256_hex(result.clip.read_bytes())


def test_clip_starts_on_a_keyframe(tmp_path: Path, synthetic_stream: StreamFactory) -> None:
    packets, info = synthetic_stream(gop=30)
    result = build_evidence(packets, info, 15.0, tmp_path)
    assert result is not None
    with av.open(str(result.clip)) as container:
        first = next(p for p in container.demux(container.streams.video[0]) if p.size)
        assert first.is_keyframe


def test_no_evidence_when_the_ring_has_no_keyframe_before_the_peak(
    tmp_path: Path, synthetic_stream: StreamFactory
) -> None:
    packets, info = synthetic_stream(seconds=4)
    assert build_evidence(packets[5:], info, 0.0, tmp_path) is None
