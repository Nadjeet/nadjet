"""Shared fixtures for the vision tests."""

from collections.abc import Callable
from fractions import Fraction

import av
import numpy as np
import pytest

from nadjet_vision.ingest import Packet, StreamInfo

FPS = 10
TIME_BASE_DEN = 90000

StreamFactory = Callable[..., tuple[list[Packet], StreamInfo]]


def make_stream(seconds: int = 22, gop: int = 20) -> tuple[list[Packet], StreamInfo]:
    """Real H.264 packets (libx264, B-frames on) as the RTSP demuxer would hand them over."""
    codec = av.CodecContext.create("libx264", "w")
    codec.width, codec.height, codec.pix_fmt = 160, 96, "yuv420p"
    codec.time_base = Fraction(1, TIME_BASE_DEN)
    codec.framerate = Fraction(FPS, 1)
    codec.gop_size = gop
    codec.options = {"preset": "ultrafast", "bf": "2", "scenecut": "0"}
    codec.open()
    packets: list[av.Packet] = []
    for n in range(seconds * FPS):
        image = np.full((96, 160, 3), (n * 3) % 255, dtype=np.uint8)
        frame = av.VideoFrame.from_ndarray(image, format="bgr24").reformat(format="yuv420p")
        frame.pts = n * TIME_BASE_DEN // FPS
        packets.extend(codec.encode(frame))
    packets.extend(codec.encode(None))
    out = [
        Packet(
            float(p.pts / TIME_BASE_DEN),
            bool(p.is_keyframe),
            bytes(p),
            float(p.dts / TIME_BASE_DEN),
        )
        for p in packets
        if p.pts is not None and p.dts is not None
    ]
    return out, StreamInfo("h264", 160, 96, bytes(codec.extradata or b""), TIME_BASE_DEN)


@pytest.fixture
def synthetic_stream() -> StreamFactory:
    return make_stream
