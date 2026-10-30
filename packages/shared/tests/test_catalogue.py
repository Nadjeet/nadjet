"""Catalogue, zones and held-out list validation (PRD FR-CAM-001, FR-VIS-022)."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from nadjet_shared.catalogue import Catalogue, CatalogueError, Zones, load_catalogue, load_zones
from nadjet_shared.heldout import Heldout, check_demo_clips, load_heldout

ROOT = Path(__file__).resolve().parents[3]

SQUARE = [[10, 10], [100, 10], [100, 100], [10, 100], [10, 10]]
ZONES: dict[str, Any] = {
    "frame": {"width": 1280, "height": 720},
    "live_lanes": [SQUARE],
    "carriageway": SQUARE,
}
CAMERA: dict[str, Any] = {
    "id": "cam-a1-pk42",
    "name": "A1 PK42",
    "video": "crash.mp4",
    "clip_id": "demo-crash-01",
    "geo": {"lat": 36.648, "lon": 3.329},
    "road": "A1",
    "wilaya": "Boumerdès",
}
CLIP: dict[str, Any] = {
    "id": "demo-crash-01",
    "role": "demo",
    "event": "crash",
    "source_dataset": "TAD",
    "licence": "research-only",
    "licence_url": "https://example.org/licence",
}


def zones(**change: Any) -> Zones:
    return Zones.model_validate({**ZONES, **change})


def test_valid_zones_are_accepted() -> None:
    assert zones().carriageway[0] == (10, 10)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"carriageway": [[10, 10], [100, 10], [10, 10]]}, "at least 4 points"),
        ({"carriageway": [[10, 10], [100, 10], [100, 100], [10, 100], [11, 10]]}, "not closed"),
        ({"live_lanes": [[[0, 0], [2000, 0], [2000, 50], [0, 0]]]}, "outside"),
        ({"carriageway": [[0, 0], [5, 5], [9, 9], [0, 0]]}, "zero area"),
        ({"live_lanes": []}, "at least 1 item"),
        ({"frame": {"width": 0, "height": 720}}, "greater than 0"),
    ],
)
def test_invalid_zones_are_rejected_with_a_clear_error(
    change: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        zones(**change)


def test_zones_file_error_names_the_file(tmp_path: Path) -> None:
    bad = tmp_path / "cam-x.json"
    bad.write_text(json.dumps({**ZONES, "carriageway": SQUARE[:4]}))
    with pytest.raises(CatalogueError, match=r"(?s)cam-x\.json.*not closed"):
        load_zones(bad)


def test_catalogue_loads_zones_by_camera_id(tmp_path: Path) -> None:
    cams = tmp_path / "cameras.yaml"
    cams.write_text(json.dumps({"cameras": [CAMERA]}))  # JSON is valid YAML
    (tmp_path / "zones").mkdir()
    (tmp_path / "zones" / "cam-a1-pk42.json").write_text(json.dumps(ZONES))
    assert load_catalogue(cams).cameras[0].zones is not None


def test_camera_without_zones_file_has_none(tmp_path: Path) -> None:
    cams = tmp_path / "cameras.yaml"
    cams.write_text(json.dumps({"cameras": [CAMERA]}))
    assert load_catalogue(cams).cameras[0].zones is None


def test_repository_data_is_consistent() -> None:
    catalogue = load_catalogue(ROOT / "data" / "cameras.yaml")
    assert all(c.zones for c in catalogue.cameras)
    check_demo_clips(catalogue, load_heldout(ROOT / "eval" / "heldout.json"))


def test_demo_clip_missing_from_heldout_is_rejected() -> None:
    catalogue = Catalogue.model_validate({"cameras": [CAMERA]})
    other = Heldout.model_validate({"clips": [{**CLIP, "id": "other"}]})
    with pytest.raises(CatalogueError, match="not a demo clip"):
        check_demo_clips(catalogue, other)


def test_eval_clip_cannot_be_a_demo_clip() -> None:
    catalogue = Catalogue.model_validate({"cameras": [CAMERA]})
    with pytest.raises(CatalogueError):
        check_demo_clips(catalogue, Heldout.model_validate({"clips": [{**CLIP, "role": "eval"}]}))


@pytest.mark.parametrize(
    "change",
    [
        {"annotation_status": "annotated", "source_clip": "a.mp4"},  # crash without impact
        {"annotation_status": "annotated", "impact_time_s": 3, "impact_region": [1, 2, 3, 4]},
        {"event": "normal", "impact_time_s": 3},
    ],
)
def test_incomplete_annotations_are_rejected(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Heldout.model_validate({"clips": [{**CLIP, **change}]})


def test_annotated_crash_is_accepted_and_ids_must_be_unique() -> None:
    annotated = {
        **CLIP,
        "annotation_status": "annotated",
        "source_clip": "a.mp4",
        "impact_time_s": 4.5,
        "impact_region": [10, 20, 30, 40],
    }
    assert Heldout.model_validate({"clips": [annotated]}).clips[0].impact_time_s == 4.5
    with pytest.raises(ValidationError, match="unique"):
        Heldout.model_validate({"clips": [CLIP, CLIP]})
