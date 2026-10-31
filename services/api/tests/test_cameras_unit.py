"""Camera registry unit tests (PRD FR-CAM-001): URL templates and the OpenAPI contract."""

import pytest
from pydantic import ValidationError

from nadjet_api.cameras.models import Camera
from nadjet_api.cameras.routes import camera_out
from nadjet_api.cli import render_openapi
from nadjet_api.config import Settings


def make_camera() -> Camera:
    return Camera(
        id="cam-a1-pk42",
        name="A1 PK42",
        stream_path="cam-a1-pk42",
        lat=36.648,
        lon=3.329,
        road="A1",
        pk_km=42,
        heading_deg=270,
        wilaya="Boumerdès",
        zones=None,
        status="unknown",
        simulated=True,
    )


def test_stream_urls_come_from_the_configured_templates() -> None:
    settings = Settings(
        env="test",
        rtsp_url_template="rtsp://video:8554/{path}",
        whep_url_template="https://video.example/{path}/whep",
        hls_url_template="https://video.example/{path}/index.m3u8",
    )
    stream = camera_out(make_camera(), settings).stream
    assert stream.rtsp_url == "rtsp://video:8554/cam-a1-pk42"
    assert stream.whep_url == "https://video.example/cam-a1-pk42/whep"
    assert stream.hls_url == "https://video.example/cam-a1-pk42/index.m3u8"


def test_default_urls_match_the_local_mediamtx_ports() -> None:
    stream = camera_out(make_camera(), Settings(env="test")).stream
    assert stream.rtsp_url == "rtsp://localhost:8554/cam-a1-pk42"
    assert stream.whep_url == "http://localhost:8889/cam-a1-pk42/whep"
    assert stream.hls_url == "http://localhost:8888/cam-a1-pk42/index.m3u8"


def test_openapi_lists_camera_routes() -> None:
    schema = render_openapi()
    assert '"/cameras"' in schema
    assert '"/cameras/{camera_id}"' in schema


@pytest.mark.parametrize(
    "template", ["http://{host}/{path}", "rtsp://localhost:8554/cam", "http://x/{path"]
)
def test_bad_url_templates_fail_at_startup(template: str) -> None:
    with pytest.raises(ValidationError, match="URL template"):
        Settings(rtsp_url_template=template)
    with pytest.raises(ValidationError, match="URL template"):
        Settings(hls_url_template=template)
