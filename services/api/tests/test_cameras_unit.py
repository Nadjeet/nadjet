"""Camera registry unit tests (PRD FR-CAM-001): URL templates and the OpenAPI contract."""

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
    )
    stream = camera_out(make_camera(), settings).stream
    assert stream.rtsp_url == "rtsp://video:8554/cam-a1-pk42"
    assert stream.whep_url == "https://video.example/cam-a1-pk42/whep"


def test_default_urls_match_the_local_mediamtx_ports() -> None:
    stream = camera_out(make_camera(), Settings(env="test")).stream
    assert stream.rtsp_url == "rtsp://localhost:8554/cam-a1-pk42"
    assert stream.whep_url == "http://localhost:8889/cam-a1-pk42/whep"


def test_openapi_lists_camera_routes() -> None:
    schema = render_openapi()
    assert '"/cameras"' in schema
    assert '"/cameras/{camera_id}"' in schema
