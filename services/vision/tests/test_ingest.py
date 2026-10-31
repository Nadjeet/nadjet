"""Frame sampling, latest-frame queue and evidence packet ring (FR-VIS-001, FR-VIS-006)."""

import threading
from itertools import pairwise

from nadjet_vision.ingest import FrameSampler, LatestFrameQueue, Packet, PacketRing


def test_sampler_picks_five_frames_per_second_from_a_25_fps_stream() -> None:
    sampler = FrameSampler(fps=5.0)
    picked = [i for i in range(100) if sampler.accept(i / 25)]  # 4 s of 25 fps
    assert len(picked) == 20
    gaps = {round((b - a) / 25, 2) for a, b in pairwise(picked)}
    assert gaps == {0.2}


def test_sampler_does_not_burst_after_a_gap_and_resets_on_clock_jump() -> None:
    sampler = FrameSampler(fps=5.0)
    assert sampler.accept(0.0)
    assert sampler.accept(10.0)  # 10 s gap: one frame, no catch-up burst
    assert not sampler.accept(10.05)
    assert sampler.accept(0.0)  # PTS restarted after a reconnect
    assert sampler.accept(0.2)


def test_queue_drops_the_oldest_frame_when_full() -> None:
    queue: LatestFrameQueue[int] = LatestFrameQueue(maxsize=2)
    for i in range(5):
        queue.put(i)
    assert len(queue) == 2
    assert queue.dropped == 3
    assert [queue.get(), queue.get()] == [3, 4]
    assert queue.get(timeout=0.01) is None


def test_queue_wakes_a_waiting_consumer() -> None:
    queue: LatestFrameQueue[str] = LatestFrameQueue()
    result: list[str | None] = []
    consumer = threading.Thread(target=lambda: result.append(queue.get(timeout=2)))
    consumer.start()
    queue.put("frame")
    consumer.join()
    assert result == ["frame"]


def packets(seconds: int, keyframe_every: int = 2) -> list[Packet]:
    return [Packet(float(t), t % keyframe_every == 0, b"x") for t in range(seconds)]


def test_ring_keeps_about_fifteen_seconds_starting_on_a_keyframe() -> None:
    ring = PacketRing(window_s=15)
    for packet in packets(60):
        ring.append(packet)
    snapshot = ring.snapshot()
    assert snapshot[0].keyframe
    assert 15 <= ring.duration_s() <= 17
    assert snapshot[-1].pts_s == 59


def test_ring_never_trims_below_the_window_without_a_keyframe() -> None:
    ring = PacketRing(window_s=5)
    ring.append(Packet(0.0, True, b"k"))
    for t in range(1, 30):
        ring.append(Packet(float(t), False, b"p"))  # no later keyframe: keep the old one
    assert ring.snapshot()[0].pts_s == 0.0


def test_ring_resets_when_timestamps_restart() -> None:
    ring = PacketRing(window_s=15)
    for packet in packets(10):
        ring.append(packet)
    ring.append(Packet(0.0, True, b"new"))
    assert len(ring.snapshot()) == 1


def test_ring_keeps_packets_whose_pts_goes_back_with_b_frames() -> None:
    """Decode order has non-monotonic PTS (I P B B); only a DTS going back is a restart."""
    ring = PacketRing(window_s=100)
    order = [(0.0, 0.0), (0.3, 0.1), (0.1, 0.2), (0.2, 0.3), (0.6, 0.4), (0.4, 0.5), (0.5, 0.6)]
    for i, (pts, dts) in enumerate(order):
        ring.append(Packet(pts, i == 0, b"x", dts))
    assert len(ring.snapshot()) == len(order)
    ring.append(Packet(0.0, True, b"new", 0.0))  # a reconnect: DTS goes back
    assert [p.data for p in ring.snapshot()] == [b"new"]
