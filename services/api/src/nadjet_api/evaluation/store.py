"""Find the latest evaluation results file (``eval/results/<date>-<git-sha>.json``)."""

import logging
from pathlib import Path

from pydantic import ValidationError

from nadjet_shared.evaluation import EvaluationResults

log = logging.getLogger(__name__)


def latest_results(directory: Path) -> EvaluationResults | None:
    """The valid results file with the newest ``generated_at``; unreadable files are skipped
    (and logged), never served. ``None`` when there is none."""
    best: EvaluationResults | None = None
    for path in sorted(directory.glob("*.json")) if directory.is_dir() else []:
        try:
            results = EvaluationResults.model_validate_json(path.read_text())
        except (OSError, ValidationError):
            log.warning("ignoring invalid evaluation results file %s", path)
            continue
        if best is None or results.generated_at > best.generated_at:
            best = results
    return best
