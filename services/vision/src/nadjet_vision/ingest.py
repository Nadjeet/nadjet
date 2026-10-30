"""Stream ingest: 5 fps frame sampling by PTS, latest-frame queue, packet ring (FR-VIS-001/006).

The PyAV reader runs in a thread (``read_stream``); everything else here is plain logic that
tests drive with synthetic timestamps.
"""

import io
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

from nadjet_vision.config import VisionSettings

BgrFrame = NDArray[np.uint8]
# FFmpeg >= 5 calls the socket timeout `timeout` (µs); `stimeout` is silently ignored. Without it
# a frozen camera (RTSP session open, no frames) blocks decode forever and never reconnects.
RTSP_OPTIONS = {"rtsp_transport": "tcp", "timeout": "5000000"}
OPEN_TIMEOUT_S = (5.0, 5.0)  # (open, read) seconds, enforced by PyAV


@dataclass(frozen=True)
class Packet:
    """One encoded video packet, kept for evidence clips."""

    pts_s: float
    keyframe: bool
    data: bytes
    dts_s: float | None = None  # decode order; ``None`` means equal to ``pts_s``


@dataclass(frozen=True)
class StreamInfo:
    """What a muxer needs to copy the ring's packets into an MP4 without re-encoding."""

    codec: str
    width: int
    height: int
    extradata: bytes
    time_base_den: int  # packet timestamps are multiples of 1 / time_base_den seconds
    # A tiny Matroska file (source codec parameters + one keyframe) used as the muxer's stream
    # template. RTSP cameras send SPS/PPS out of band (SDP): copying only `extradata` into a
    # freshly opened encoder lets the encoder write its own avcC and the clip stops decoding.
    template: bytes = b""


def codec_template(stream: Any, keyframe: Any) -> bytes:
    """Matroska bytes carrying ``stream``'s exact codec parameters (and ``keyframe``)."""
    import av

    buffer = io.BytesIO()
    with av.open(buffer, "w", format="matroska") as output:
        out_stream = output.add_stream_from_template(stream)
        packet = av.Packet(bytes(keyframe))
        packet.stream = out_stream
        packet.time_base = stream.time_base
        packet.pts = packet.dts = 0
        packet.is_keyframe = True
        output.mux(packet)  # Matroska writes nothing until a packet is muxed
    return buffer.getvalue()


@dataclass(frozen=True)
class SampledFrame:
    pts_s: float
    image: BgrFrame
    decode_ms: float  # time spent decoding this frame's packet
    captured_at: float = field(default_factory=time.time)  # wall clock (epoch s) at decode


class PacketRing:
    """The last ``window_s`` seconds of encoded packets, always starting on a keyframe.

    A clip can only be decoded from a keyframe, so trimming never drops the newest keyframe
    that is at least ``window_s`` old: the buffer may hold slightly more than the window.
    """

    def __init__(self, window_s: float = 15.0, max_packets: int = 15 * 120) -> None:
        self._window_s = window_s
        # Hard cap: a stream without keyframes could otherwise never be trimmed.
        self._packets: deque[Packet] = deque(maxlen=max_packets)
        self._lock = threading.Lock()
        self.stream: StreamInfo | None = None

    def clear(self) -> None:
        """Forget the previous RTSP session (its packets cannot be mixed into a clip)."""
        with self._lock:
            self._packets.clear()

    def append(self, packet: Packet) -> None:
        with self._lock:
            if self._packets and packet.pts_s < self._packets[-1].pts_s:
                self._packets.clear()  # timestamp reset after a reconnect
            self._packets.append(packet)
            self._trim(packet.pts_s)

    def _trim(self, now_s: float) -> None:
        cutoff = now_s - self._window_s
        keyframes = [i for i, p in enumerate(self._packets) if p.keyframe and p.pts_s <= cutoff]
        if keyframes:
            for _ in range(keyframes[-1]):
                self._packets.popleft()

    def snapshot(self) -> list[Packet]:
        with self._lock:
            return list(self._packets)

    def duration_s(self) -> float:
        with self._lock:
            if len(self._packets) < 2:
                return 0.0
            return self._packets[-1].pts_s - self._packets[0].pts_s


class FrameSampler:
    """Pick frames at ``fps`` from the stream clock (PTS), whatever the source frame rate."""

    def __init__(self, fps: float = 5.0) -> None:
        self._interval = 1.0 / fps
        self._next_due: float | None = None

    def accept(self, pts_s: float) -> bool:
        if self._next_due is None or pts_s + 1.0 < self._next_due - self._interval:
            self._next_due = pts_s  # first frame, or the clock jumped back (reconnect)
        if pts_s + 1e-6 >= self._next_due:
            self._next_due += self._interval
            if self._next_due <= pts_s:  # fell behind (long gap): do not burst
                self._next_due = pts_s + self._interval
            return True
        return False


class LatestFrameQueue[T]:
    """Bounded hand-off between reader and analysis threads: when full, the oldest item is
    dropped so the analysis always sees the latest frame (FR-VIS-001, NFR-PERF-001)."""

    def __init__(self, maxsize: int = 2) -> None:
        self._items: deque[T] = deque()
        self._maxsize = maxsize
        self._cond = threading.Condition()
        self.dropped = 0

    def put(self, item: T) -> None:
        with self._cond:
            if len(self._items) >= self._maxsize:
                self._items.popleft()
                self.dropped += 1
            self._items.append(item)
            self._cond.notify()

    def get(self, timeout: float | None = None) -> T | None:
        with self._cond:
            if not self._items:
                self._cond.wait(timeout)
            return self._items.popleft() if self._items else None

    def __len__(self) -> int:
        with self._cond:
            return len(self._items)


def iter_frames(
    url: str,
    stop: Callable[[], bool],
    *,
    sampler: FrameSampler,
    ring: PacketRing,
    on_open: Callable[[], None] | None = None,
) -> Iterator[SampledFrame]:
    """Blocking PyAV reader: demux, keep packets, decode and yield sampled frames."""
    import av  # gpu extra, imported lazily so local tools and tests do not need it

    with av.open(url, options=RTSP_OPTIONS, timeout=OPEN_TIMEOUT_S) as container:
        ring.clear()
        if on_open is not None:
            on_open()
        stream = container.streams.video[0]
        base: Any = stream.time_base
        context: Any = stream.codec_context
        ring.stream = StreamInfo(
            codec=str(context.name),
            width=int(context.width),
            height=int(context.height),
            extradata=bytes(context.extradata or b""),
            time_base_den=round(1 / base),
        )
        for packet in container.demux(stream):
            if stop():
                return
            if packet.dts is None or packet.pts is None:
                continue  # flush packet
            ptime = float(packet.pts * base)
            if packet.is_keyframe and ring.stream is not None and not ring.stream.template:
                ring.stream = replace(ring.stream, template=codec_template(stream, packet))
            ring.append(
                Packet(ptime, bool(packet.is_keyframe), bytes(packet), float(packet.dts * base))
            )
            started = time.perf_counter()
            for frame in packet.decode():
                pts = float(frame.pts * base) if frame.pts is not None else ptime
                if sampler.accept(pts):
                    decode_ms = (time.perf_counter() - started) * 1000
                    image = cast(BgrFrame, frame.to_ndarray(format="bgr24"))
                    yield SampledFrame(pts, image, decode_ms, time.time())


def make_ingest(settings: VisionSettings) -> tuple[FrameSampler, PacketRing]:
    return FrameSampler(settings.sample_fps), PacketRing(settings.evidence_buffer_s)
