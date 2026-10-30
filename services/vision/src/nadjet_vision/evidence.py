"""Evidence clip and keyframes from the encoded packet ring (PRD FR-VIS-005, TD-16).

The clip is a stream copy: the ring's H.264 packets are remuxed into an MP4 without decoding or
re-encoding, starting on a keyframe. Keyframes (JPEG) are decoded from that clip. Hashes are
computed here for the transfer check; the API recomputes them and chains them (TD-16).
"""

import hashlib
import io
from collections.abc import Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

from nadjet_vision.ingest import Packet, StreamInfo

JPEG_MAGIC = b"\xff\xd8"


@dataclass(frozen=True)
class ClipPlan:
    """Packets chosen for one clip and how much of the wanted window they really cover."""

    packets: list[Packet]
    start_pts: float
    pre_s: float  # seconds before the peak the clip actually holds
    post_s: float  # seconds after the peak


@dataclass(frozen=True)
class EvidenceFiles:
    clip: Path
    keyframes: list[Path]
    sha256: dict[str, str]
    plan: ClipPlan = field(repr=False)


def _decode_order(packet: Packet) -> float:
    return packet.dts_s if packet.dts_s is not None else packet.pts_s


def plan_clip(
    packets: Sequence[Packet], peak_pts: float, before_s: float = 10.0, after_s: float = 5.0
) -> ClipPlan | None:
    """Pick the packets for a clip around ``peak_pts``: from the last keyframe at or before
    ``peak - before_s`` (the earliest keyframe when the ring is shorter) to ``peak + after_s``.

    Returns ``None`` when the ring holds no keyframe at or before the peak.
    """
    keyframes = [i for i, p in enumerate(packets) if p.keyframe and p.pts_s <= peak_pts]
    if not keyframes:
        return None
    wanted = [i for i in keyframes if packets[i].pts_s <= peak_pts - before_s]
    first = wanted[-1] if wanted else keyframes[0]
    chosen = [p for p in packets[first:] if _decode_order(p) <= peak_pts + after_s]
    start = chosen[0].pts_s
    end = max(p.pts_s for p in chosen)
    return ClipPlan(chosen, start, pre_s=peak_pts - start, post_s=max(0.0, end - peak_pts))


def keyframe_times(peak_s: float, count: int = 6, span_s: float = 2.0) -> list[float]:
    """``count`` instants evenly spread over ``peak ± span`` (FR-VIS-005: 6 around the peak)."""
    if count == 1:
        return [peak_s]
    step = 2 * span_s / (count - 1)
    return [peak_s - span_s + i * step for i in range(count)]


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_clip(plan: ClipPlan, info: StreamInfo, path: Path) -> None:
    """Remux the planned packets into ``path`` (MP4) without re-encoding."""
    import av  # gpu extra, imported lazily like the other PyAV users

    base = Fraction(1, info.time_base_den)
    origin = _decode_order(plan.packets[0])
    template = av.open(io.BytesIO(info.template)) if info.template else None
    try:
        with av.open(str(path), "w", format="mp4") as output:
            if template is not None:
                # Exact source parameters (SPS/PPS, profile, B-frames): a true stream copy.
                stream: Any = output.add_stream_from_template(template.streams.video[0])
            else:
                # No keyframe seen yet: best effort, works when SPS/PPS are in-band.
                stream = output.add_stream(info.codec)
                context = stream.codec_context
                context.width, context.height = info.width, info.height
                context.pix_fmt = "yuv420p"
                if info.extradata:
                    context.extradata = info.extradata
            stream.time_base = base
            _mux(output, stream, plan, base, origin)
    finally:
        if template is not None:
            template.close()


def _mux(output: Any, stream: Any, plan: ClipPlan, base: Fraction, origin: float) -> None:
    import av

    for item in plan.packets:
        packet = av.Packet(item.data)
        packet.stream = stream
        packet.time_base = base
        packet.pts = round((item.pts_s - origin) / base)
        packet.dts = round((_decode_order(item) - origin) / base)
        if item.keyframe:
            packet.is_keyframe = True
        output.mux(packet)


def encode_jpeg(frame: Any) -> bytes:
    """JPEG bytes of one decoded PyAV frame."""
    import av

    context = av.CodecContext.create("mjpeg", "w")
    context.width, context.height = frame.width, frame.height
    context.pix_fmt = "yuvj420p"
    context.time_base = Fraction(1, 1)
    context.options = {"qmin": "2", "qmax": "5"}
    context.open()
    converted = frame.reformat(format="yuvj420p")
    converted.pts = 0
    packets = [*context.encode(converted), *context.encode(None)]
    return b"".join(bytes(p) for p in packets)


def extract_keyframes(clip: Path, peak_offset_s: float, count: int = 6) -> list[bytes]:
    """The decoded frames nearest to ``keyframe_times`` (clip-relative seconds) as JPEG."""
    import av

    targets = keyframe_times(peak_offset_s, count)
    best: list[tuple[float, Any] | None] = [None] * len(targets)
    origin: float | None = None
    with av.open(str(clip)) as container:
        for frame in container.decode(video=0):
            if frame.pts is None:
                continue
            seconds = float(frame.pts * frame.time_base)
            origin = seconds if origin is None else origin
            relative = seconds - origin
            for i, target in enumerate(targets):
                distance = abs(relative - target)
                current = best[i]
                if current is None or distance < current[0]:
                    best[i] = (distance, frame.reformat(format="yuvj420p"))
            if relative > targets[-1] + 1.0:
                break
    return [encode_jpeg(item[1]) for item in best if item is not None]


def build_evidence(
    packets: Sequence[Packet],
    info: StreamInfo,
    peak_pts: float,
    dest: Path,
    *,
    before_s: float = 10.0,
    after_s: float = 5.0,
    keyframes: int = 6,
) -> EvidenceFiles | None:
    """Write ``clip.mp4`` and ``keyframe-N.jpg`` into ``dest`` and hash them."""
    plan = plan_clip(packets, peak_pts, before_s, after_s)
    if plan is None:
        return None
    dest.mkdir(parents=True, exist_ok=True)
    clip = dest / "clip.mp4"
    write_clip(plan, info, clip)
    paths: list[Path] = []
    for n, data in enumerate(extract_keyframes(clip, peak_pts - plan.start_pts, keyframes), 1):
        path = dest / f"keyframe-{n}.jpg"
        path.write_bytes(data)
        paths.append(path)
    digests = {p.name: sha256_hex(p.read_bytes()) for p in [clip, *paths]}
    return EvidenceFiles(clip, paths, digests, plan)
