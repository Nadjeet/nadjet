"""The short video sent to the AI verifier (doc 11 TD-01, TD-22).

Verifier: 16 dense frames at 4 fps over the moment ± 2 s plus 4 context frames from -8 s to
+4 s. Sweep: the last 8 s at 2 fps. Frames are decoded from the encoded packet ring, scaled
(768 px / 640 px long side), stamped with their number and time, and encoded as one MP4 sent to
vLLM as a data URL (no file sharing between hosts, no third-party hosting).
"""

import base64
import io
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

import numpy as np

from nadjet_vision.evidence import plan_clip
from nadjet_vision.ingest import BgrFrame, Packet, StreamInfo

DENSE_SPAN_S = 2.0
DENSE_FPS = 4.0
CONTEXT_OFFSETS_S = (-8.0, -5.0, -3.0, 4.0)
VERIFIER_LONG_SIDE = 768
SWEEP_WINDOW_S = 8.0
SWEEP_FPS = 2.0
SWEEP_LONG_SIDE = 640

# 5x7 glyphs for the stamp: digits and the few symbols a label needs.
_GLYPHS = {
    "0": "01110 10001 10011 10101 11001 10001 01110",
    "1": "00100 01100 00100 00100 00100 00100 01110",
    "2": "01110 10001 00001 00010 00100 01000 11111",
    "3": "11110 00001 00001 01110 00001 00001 11110",
    "4": "00010 00110 01010 10010 11111 00010 00010",
    "5": "11111 10000 11110 00001 00001 10001 01110",
    "6": "00110 01000 10000 11110 10001 10001 01110",
    "7": "11111 00001 00010 00100 01000 01000 01000",
    "8": "01110 10001 10001 01110 10001 10001 01110",
    "9": "01110 10001 10001 01111 00001 00010 01100",
    "#": "01010 01010 11111 01010 11111 01010 01010",
    "+": "00000 00100 00100 11111 00100 00100 00000",
    "-": "00000 00000 00000 11111 00000 00000 00000",
    ".": "00000 00000 00000 00000 00000 01100 01100",
    "s": "00000 00000 01111 10000 01110 00001 11110",
    " ": "00000 00000 00000 00000 00000 00000 00000",
}
_BITMAPS = {
    ch: np.array([[c == "1" for c in row] for row in rows.split()], dtype=bool)
    for ch, rows in _GLYPHS.items()
}


@dataclass(frozen=True)
class VerifierVideo:
    data_url: str
    frame_count: int
    frame_times_s: list[float]  # seconds relative to the centre, per frame id


def verifier_times(centre_s: float) -> list[float]:
    """Frame instants of the verifier video (stream clock): dense block plus context."""
    steps = int(2 * DENSE_SPAN_S * DENSE_FPS)
    dense = [centre_s - DENSE_SPAN_S + i / DENSE_FPS for i in range(steps)]
    return sorted([*dense, *(centre_s + o for o in CONTEXT_OFFSETS_S)])


def sweep_times(end_s: float) -> list[float]:
    """Frame instants of a sweep window: the last 8 s at 2 fps, oldest first."""
    count = int(SWEEP_WINDOW_S * SWEEP_FPS)
    return [end_s - SWEEP_WINDOW_S + (i + 1) / SWEEP_FPS for i in range(count)]


def stamp(image: BgrFrame, text: str) -> BgrFrame:
    """Draw ``text`` (white on black) at the top left; the digits are 5x7 bitmaps."""
    scale = max(2, image.shape[1] // 160)
    out = image.copy()
    width = len(text) * 6 * scale + 2 * scale
    out[: 9 * scale, :width] = 0
    for n, ch in enumerate(text):
        bitmap = _BITMAPS.get(ch.lower(), _BITMAPS[" "])
        big = np.kron(bitmap, np.ones((scale, scale), dtype=bool))
        x, y = scale + n * 6 * scale, scale
        out[y : y + big.shape[0], x : x + big.shape[1]][big] = 255
    return out


def scaled_size(width: int, height: int, long_side: int) -> tuple[int, int]:
    """Even dimensions (yuv420p) with the long side at most ``long_side``."""
    factor = min(1.0, long_side / max(width, height))
    return max(2, round(width * factor / 2) * 2), max(2, round(height * factor / 2) * 2)


def decode_nearest(
    packets: Sequence[Packet], info: StreamInfo, targets_s: Sequence[float]
) -> list[tuple[float, Any]]:
    """Decode ``packets`` (from a keyframe) and keep the frame nearest to each target.

    Returns ``(pts_s, frame)`` for the distinct frames chosen, in time order. Targets outside
    the decoded span get the nearest end frame (duplicates collapse to one).
    """
    import av

    base = Fraction(1, info.time_base_den)
    decoder: Any = av.CodecContext.create(info.codec, "r")
    if info.extradata:
        decoder.extradata = info.extradata
    best: list[tuple[float, float, Any] | None] = [None] * len(targets_s)
    for item in packets:
        packet = av.Packet(item.data)
        packet.time_base = base
        packet.pts = round(item.pts_s / base)
        packet.dts = round((item.dts_s if item.dts_s is not None else item.pts_s) / base)
        for frame in decoder.decode(packet):
            if frame.pts is None:
                continue
            seconds = float(frame.pts * base)
            for i, target in enumerate(targets_s):
                distance = abs(seconds - target)
                current = best[i]
                if current is None or distance < current[0]:
                    best[i] = (distance, seconds, frame)
    chosen: dict[float, Any] = {}
    for entry in best:
        if entry is not None:
            chosen[entry[1]] = entry[2]
    return sorted(chosen.items())


def encode_video(images: Sequence[BgrFrame], fps: float) -> bytes:
    """One H.264 MP4 of ``images`` (all the same even size) at ``fps``."""
    import av

    height, width = images[0].shape[:2]
    buffer = io.BytesIO()
    with av.open(buffer, "w", format="mp4") as output:
        stream: Any = output.add_stream("libx264", rate=Fraction(fps).limit_denominator(100))
        stream.width, stream.height, stream.pix_fmt = width, height, "yuv420p"
        stream.options = {"preset": "veryfast", "crf": "26"}
        for image in images:
            frame = av.VideoFrame.from_ndarray(image, format="bgr24")
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode(None):
            output.mux(packet)
    return buffer.getvalue()


def _video(
    packets: Sequence[Packet],
    info: StreamInfo,
    times: Sequence[float],
    centre_s: float,
    long_side: int,
    fps: float,
) -> VerifierVideo | None:
    first, last = min(times), max(times)
    plan = plan_clip(packets, last, before_s=last - first, after_s=0.0)
    if plan is None:
        return None
    frames = decode_nearest(plan.packets, info, times)
    if not frames:
        return None
    width, height = scaled_size(info.width, info.height, long_side)
    images: list[BgrFrame] = []
    relative: list[float] = []
    for n, (seconds, frame) in enumerate(frames):
        scaled: Any = frame.reformat(width=width, height=height, format="bgr24")
        rel = seconds - centre_s
        images.append(stamp(scaled.to_ndarray(), f"#{n:02d} {rel:+.2f}s"))
        relative.append(rel)
    data = base64.b64encode(encode_video(images, fps)).decode()
    return VerifierVideo(f"data:video/mp4;base64,{data}", len(images), relative)


def build_verifier_video(
    packets: Sequence[Packet], info: StreamInfo, centre_s: float
) -> VerifierVideo | None:
    """Video for one rule candidate around ``centre_s`` (stream clock)."""
    # Frames after the newest packet cannot exist yet: the nearest end frame stands in.
    return _video(packets, info, verifier_times(centre_s), centre_s, VERIFIER_LONG_SIDE, DENSE_FPS)


def build_sweep_video(
    packets: Sequence[Packet], info: StreamInfo, end_s: float
) -> VerifierVideo | None:
    """Video of the last 8 s before ``end_s`` for the AI sweep."""
    return _video(packets, info, sweep_times(end_s), end_s, SWEEP_LONG_SIDE, SWEEP_FPS)
