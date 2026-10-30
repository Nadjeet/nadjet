"""Latest evaluation results file selection (FR-KPI-003)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nadjet_api.evaluation.store import latest_results
from nadjet_shared.evaluation import AblationRow, EvaluationResults


def results(day: int, sha: str = "abc") -> EvaluationResults:
    return EvaluationResults(
        generated_at=datetime(2026, 10, day, 12, tzinfo=UTC), git_sha=sha, dirty=False, seed=0,
        bootstrap_samples=10, window_before_s=2, window_after_s=10, models={}, clips=[],
        camera_hours=0, meets_camera_hour_target=False,
        ablation=[AblationRow(name="rules", description="d", not_run_reason="none yet")],
    )  # fmt: skip


def write(directory: Path, name: str, content: EvaluationResults | str) -> None:
    text = content if isinstance(content, str) else content.model_dump_json()
    (directory / name).write_text(text)


def test_no_directory_or_no_file_means_no_results(tmp_path: Path) -> None:
    assert latest_results(tmp_path / "missing") is None
    assert latest_results(tmp_path) is None


def test_the_newest_run_wins_by_its_own_date_not_by_file_name(tmp_path: Path) -> None:
    write(tmp_path, "2026-10-29-zzz.json", results(29, "zzz"))
    write(tmp_path, "2026-10-30-aaa.json", results(30, "aaa"))
    write(tmp_path, "2026-10-01-mmm.json", results(1, "mmm"))
    latest = latest_results(tmp_path)
    assert latest is not None and latest.git_sha == "aaa"


def test_a_misnamed_file_still_counts_by_its_content(tmp_path: Path) -> None:
    write(tmp_path, "2026-10-30-old.json", results(5, "old"))
    write(tmp_path, "notes.json", results(20, "new"))
    latest = latest_results(tmp_path)
    assert latest is not None and latest.git_sha == "new"


def test_invalid_and_foreign_files_are_ignored_not_served(
    tmp_path: Path,
    caplog: "pytest.LogCaptureFixture",
) -> None:
    write(tmp_path, "good.json", results(10, "good"))
    write(tmp_path, "broken.json", "{not json")
    write(tmp_path, "wrong.json", '{"schema_version": 1}')
    (tmp_path / "2026-10-30-x.md").write_text("# summary")
    caplog.set_level("WARNING")
    latest = latest_results(tmp_path)
    assert latest is not None and latest.git_sha == "good"
    assert "broken.json" in caplog.text and "wrong.json" in caplog.text
