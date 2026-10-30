from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from nadjet_camsim.cli import main
from nadjet_camsim.config import Catalogue, load_catalogue, render_mediamtx

REPO_CATALOGUE = Path(__file__).resolve().parents[3] / "data" / "cameras.yaml"

CAMERA = {
    "id": "cam-a1-pk42",
    "name": "A1 PK42",
    "video": "crash.mp4",
    "clip_id": "demo-crash-01",
    "geo": {"lat": 36.648, "lon": 3.329},
    "road": "A1",
    "pk_km": 42,
    "heading_deg": 270,
    "wilaya": "Boumerdès",
}


def catalogue(*cameras: dict[str, object]) -> Catalogue:
    return Catalogue.model_validate({"cameras": list(cameras)})


def test_repository_catalogue_is_valid() -> None:
    assert load_catalogue(REPO_CATALOGUE).cameras


def test_render_publishes_existing_videos_unmodified(tmp_path: Path) -> None:
    (tmp_path / "crash.mp4").write_bytes(b"\x00")
    config, skipped = render_mediamtx(catalogue(CAMERA), tmp_path)
    assert skipped == []
    command = config["paths"]["cam-a1-pk42"]["runOnInit"]
    assert "-stream_loop -1" in command
    assert "-c copy" in command  # no re-encoding: frames are not modified
    assert "/videos/crash.mp4" in command
    actions = {p["action"] for p in config["authInternalUsers"][0]["permissions"]}
    assert {"read", "api"} <= actions


def test_render_skips_cameras_without_video(tmp_path: Path) -> None:
    config, skipped = render_mediamtx(catalogue(CAMERA), tmp_path)
    assert skipped == ["cam-a1-pk42"]
    assert "cam-a1-pk42" not in config["paths"]


@pytest.mark.parametrize(
    "change",
    [{"id": "Cam A1"}, {"geo": {"lat": 48.8, "lon": 2.3}}, {"heading_deg": 400}],
)
def test_invalid_cameras_are_rejected(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        catalogue({**CAMERA, **change})


def test_duplicate_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="unique"):
        catalogue(CAMERA, CAMERA)


def test_cli_writes_config(tmp_path: Path) -> None:
    cams = tmp_path / "cameras.yaml"
    cams.write_text(yaml.safe_dump({"cameras": [CAMERA]}))
    (tmp_path / "videos").mkdir()
    (tmp_path / "videos" / "crash.mp4").write_bytes(b"\x00")
    out = tmp_path / "mediamtx.yml"
    assert (
        main(
            [
                "--cameras",
                str(cams),
                "--videos",
                str(tmp_path / "videos"),
                "render",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    assert "cam-a1-pk42" in yaml.safe_load(out.read_text())["paths"]


def test_cli_fails_on_invalid_catalogue(tmp_path: Path) -> None:
    cams = tmp_path / "cameras.yaml"
    cams.write_text("cameras: [{id: x}]")
    assert main(["--cameras", str(cams), "render", "--out", str(tmp_path / "o.yml")]) == 1


def test_frozen_publisher_is_not_dropped_by_the_read_timeout(tmp_path: Path) -> None:
    """FR-CAM-004: a SIGSTOP'd publisher sends nothing; the 10 s default turned freeze into outage."""
    config, _ = render_mediamtx(catalogue(CAMERA), tmp_path)
    assert config["readTimeout"] == "1h"
