"""Shared fixtures for the vision tests."""

import io
from collections.abc import Callable
from fractions import Fraction

import av
import numpy as np
import pytest

from nadjet_vision.ingest import Packet, StreamInfo, codec_template

FPS = 10
TIME_BASE_DEN = 90000

StreamFactory = Callable[..., tuple[list[Packet], StreamInfo]]


def make_stream(seconds: int = 22, gop: int = 20) -> tuple[list[Packet], StreamInfo]:
    """Real H.264 packets (libx264, B-frames on) as the RTSP demuxer hands them over.

    The packets go through an MP4 first, so SPS/PPS travel out of band in ``extradata``,
    like an RTSP camera's SDP: a clip only decodes if its muxer keeps the source parameters.
    """
    source = io.BytesIO()
    with av.open(source, "w", format="mp4") as output:
        stream = output.add_stream("libx264", rate=FPS)
        stream.width, stream.height, stream.pix_fmt = 160, 96, "yuv420p"
        stream.codec_context.gop_size = gop
        stream.codec_context.options = {"preset": "ultrafast", "bf": "2", "scenecut": "0"}
        for n in range(seconds * FPS):
            image = np.full((96, 160, 3), (n * 3) % 255, dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(image, format="bgr24")
            output.mux(stream.encode(frame))
        output.mux(stream.encode(None))
    source.seek(0)
    out: list[Packet] = []
    template = b""
    with av.open(source) as container:
        video = container.streams.video[0]
        scale = Fraction(TIME_BASE_DEN) * video.time_base
        for p in container.demux(video):
            if p.pts is None or p.dts is None:
                continue
            if p.is_keyframe and not template:
                template = codec_template(video, p)
            out.append(
                Packet(
                    float(p.pts * video.time_base),
                    bool(p.is_keyframe),
                    bytes(p),
                    float(p.dts * video.time_base),
                )
            )
        extradata = bytes(video.codec_context.extradata or b"")
        assert scale  # time_base is exact
        den = int(1 / video.time_base)
    return out, StreamInfo("h264", 160, 96, extradata, den, template)


@pytest.fixture
def synthetic_stream() -> StreamFactory:
    return make_stream
