"""Frame selection and the numbered, time-stamped video for the verifier (TD-01, TD-22)."""

import base64
import io

import av
import numpy as np
import pytest

from nadjet_vision.clipvideo import (
    CONTEXT_OFFSETS_S,
    build_sweep_video,
    build_verifier_video,
    scaled_size,
    stamp,
    sweep_times,
    verifier_times,
)

from .conftest import StreamFactory


def test_verifier_frames_are_16_dense_at_4_fps_plus_4_context() -> None:
    times = verifier_times(10.0)
    assert len(times) == 20
    assert times == sorted(times)
    dense = [
        t
        for t in times
        if abs(t - 10.0) < 2.0 + 1e-9 and t not in (10.0 + o for o in CONTEXT_OFFSETS_S)
    ]
    assert len(dense) == 16
    assert dense[1] - dense[0] == pytest.approx(0.25)
    assert (dense[0], dense[-1]) == (pytest.approx(8.0), pytest.approx(11.75))
    assert min(times) == pytest.approx(10.0 - 8.0)
    assert max(times) == pytest.approx(10.0 + 4.0)


def test_sweep_frames_are_the_last_8_s_at_2_fps() -> None:
    times = sweep_times(30.0)
    assert len(times) == 16
    assert times[0] == pytest.approx(22.5)
    assert times[-1] == pytest.approx(30.0)
    assert times[1] - times[0] == pytest.approx(0.5)


def test_scaled_size_keeps_aspect_with_even_sides() -> None:
    assert scaled_size(1920, 1080, 768) == (768, 432)
    assert scaled_size(640, 360, 768) == (640, 360)  # never upscales
    width, height = scaled_size(1279, 719, 640)
    assert width % 2 == 0 and height % 2 == 0 and max(width, height) <= 640


def test_stamp_draws_the_label_without_touching_the_rest() -> None:
    image = np.full((90, 160, 3), 100, dtype=np.uint8)
    out = stamp(image, "#07 +0.25s")
    assert (image == 100).all()  # input untouched
    assert (out[:16, :60] != 100).any()
    assert (out[40:, :] == 100).all()
    assert (out == 255).any()  # glyph pixels


def test_different_labels_give_different_pixels() -> None:
    image = np.zeros((90, 160, 3), dtype=np.uint8)
    assert not np.array_equal(stamp(image, "#01 +0.00s"), stamp(image, "#02 -1.25s"))


def decode(data_url: str) -> list[np.ndarray]:  # type: ignore[type-arg]
    assert data_url.startswith("data:video/mp4;base64,")
    raw = base64.b64decode(data_url.split(",", 1)[1])
    with av.open(io.BytesIO(raw)) as container:
        return [f.to_ndarray(format="bgr24") for f in container.decode(video=0)]


def test_verifier_video_has_one_numbered_frame_per_instant(
    synthetic_stream: StreamFactory,
) -> None:
    packets, info = synthetic_stream()
    video = build_verifier_video(packets, info, centre_s=12.0)
    assert video is not None
    assert video.frame_count == 20
    assert len(video.frame_times_s) == 20
    assert min(video.frame_times_s) == pytest.approx(-8.0, abs=0.2)
    assert max(video.frame_times_s) == pytest.approx(4.0, abs=0.2)
    frames = decode(video.data_url)
    assert len(frames) == 20
    assert frames[0].shape[:2] == (96, 160)
    assert (frames[0][:16, :60] > 200).any()  # the stamp survived H.264


def test_sweep_video_covers_the_last_8_seconds(synthetic_stream: StreamFactory) -> None:
    packets, info = synthetic_stream()
    video = build_sweep_video(packets, info, end_s=20.0)
    assert video is not None
    assert video.frame_count == 16
    assert video.frame_times_s[0] == pytest.approx(-7.5, abs=0.2)
    assert len(decode(video.data_url)) == 16


def test_a_short_ring_gives_fewer_distinct_frames_not_invented_ones(
    synthetic_stream: StreamFactory,
) -> None:
    packets, info = synthetic_stream(seconds=6)
    video = build_verifier_video(packets, info, centre_s=5.0)
    assert video is not None
    assert video.frame_count < 20  # -8 s and +4 s do not exist: they collapse onto the ends
    assert len(set(video.frame_times_s)) == video.frame_count


def test_no_video_without_any_keyframe(synthetic_stream: StreamFactory) -> None:
    packets, info = synthetic_stream(seconds=6)
    assert build_verifier_video([p for p in packets if not p.keyframe], info, 5.0) is None


def test_decode_nearest_flushes_the_decoder_so_the_newest_frames_count(
    synthetic_stream: StreamFactory,
) -> None:
    """B-frames and decoder delay hold the last frames until a flush: without it the sweep's
    newest moment (its window end) would silently map to an older frame."""
    from nadjet_vision.clipvideo import decode_nearest

    packets, info = synthetic_stream(seconds=6, gop=10)
    last = max(p.pts_s for p in packets)
    [(pts, _frame)] = decode_nearest(packets, info, [last])
    assert pts == pytest.approx(last)
