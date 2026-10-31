"""The evaluation script's clip planning, guard and comparison (FR-VIS-022)."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from nadjet_shared.catalogue import load_catalogue
from nadjet_shared.heldout import Heldout, HeldoutClip, load_heldout

ROOT = Path(__file__).resolve().parents[3]


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_eval", ROOT / "eval" / "run_eval.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_eval = load_script()


def clip(id: str, event: str = "crash", **extra: object) -> HeldoutClip:
    return HeldoutClip(
        id=id, role="eval", event=event, source_dataset="d", licence="l", licence_url="u", **extra
    )  # type: ignore[arg-type]


def annotated(id: str) -> HeldoutClip:
    return clip(
        id, annotation_status="annotated", source_clip="f.mp4",
        impact_time_s=12.0, impact_region=(1, 2, 3, 4),
    )  # fmt: skip


def test_the_repo_catalogue_and_tuning_files_pass_the_guard() -> None:
    assert run_eval.tuning_violations(load_heldout(ROOT / "eval/heldout.json")) == []


def test_clip_kinds() -> None:
    assert run_eval.kind_of(clip("a")) == "crash"
    assert run_eval.kind_of(clip("b", "heavy_congestion")) == "negative"
    assert run_eval.kind_of(clip("c", "normal")) == "negative"
    assert run_eval.kind_of(clip("d", "stalled_vehicle")) == "stalled"


def test_clips_are_planned_or_skipped_with_a_reason(tmp_path: Path) -> None:
    catalogue = load_catalogue(ROOT / "data/cameras.yaml")
    camera = catalogue.cameras[0]
    videos, eval_videos = tmp_path / "videos", tmp_path / "eval"
    videos.mkdir()
    eval_videos.mkdir()
    (videos / camera.video).write_bytes(b"x")
    (eval_videos / "extra-neg.mp4").write_bytes(b"x")
    heldout = Heldout(
        clips=[
            annotated(camera.clip_id),  # camera clip with its video present
            clip("pending-crash"),  # crash not annotated
            clip("extra-neg", "normal"),  # no camera of its own: needs --camera
            clip("no-video", "normal"),
        ]
    )
    plans, skipped = run_eval.plan_clips(
        heldout, catalogue, videos, eval_videos, fallback_camera=camera.id
    )
    assert [(p.clip.id, p.video.name) for p in plans] == [
        (camera.clip_id, camera.video),
        ("extra-neg", "extra-neg.mp4"),
    ]
    assert {s.id: s.reason for s in skipped} == {
        "pending-crash": "crash annotation pending",
        "no-video": f"video missing: {eval_videos / 'no-video.mp4'}",
    }
    _, without_camera = run_eval.plan_clips(heldout, catalogue, videos, eval_videos)
    assert "no camera zones (pass --camera)" in {s.reason for s in without_camera}


def test_a_tuning_file_that_names_a_clip_stops_the_run(tmp_path: Path) -> None:
    (tmp_path / "data/tuning").mkdir(parents=True)
    (tmp_path / "data/tuning/cam.yaml").write_text("stalled_s: 30  # tuned on demo-crash-01\n")
    (tmp_path / "data/cameras.yaml").write_text("cameras: []\n")
    found = run_eval.tuning_violations(Heldout(clips=[clip("demo-crash-01")]), tmp_path)
    assert found == ["data/tuning/cam.yaml: demo-crash-01"]


def test_a_camera_with_overrides_on_an_evaluation_clip_stops_the_run(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data/cameras.yaml").write_text(
        "cameras:\n  - {id: cam-a, clip_id: demo-crash-01, triggers: {stalled_s: 30}}\n"
    )
    found = run_eval.tuning_violations(Heldout(clips=[clip("demo-crash-01")]), tmp_path)
    assert found == ["camera cam-a (clip demo-crash-01) has trigger overrides"]


def test_main_without_scorable_clips_exits_2_and_says_why(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = run_eval.main(["--no-ai", "--videos", "/nonexistent", "--demo-videos", "/nonexistent"])
    out = capsys.readouterr().out
    assert code == 2
    assert "No clip can be scored" in out and "crash annotation pending" in out


def test_compare_exits_0_for_a_file_against_itself_and_1_for_different_runs(
    tmp_path: Path,
) -> None:
    from .test_evaluation import alert, assembled, crash, results

    first = assembled()
    a = tmp_path / "a.json"
    a.write_text(first.model_dump_json())
    assert run_eval.main(["--compare", str(a), str(a)]) == 0

    good = results([crash(10.0, alert(13.0), id=str(i)) for i in range(20)])
    bad = results([crash(10.0, alert(50.0), id=str(i)) for i in range(20)])
    (tmp_path / "g.json").write_text(good.model_dump_json())
    (tmp_path / "b.json").write_text(bad.model_dump_json())
    assert run_eval.main(["--compare", str(tmp_path / "g.json"), str(tmp_path / "b.json")]) == 1
    assert json.loads((tmp_path / "g.json").read_text())["schema_version"] == 1
