"""Event-level evaluation metrics, ablation configurations and run comparison (doc 04 §5).

Pure functions over alerts recorded while replaying clips: matching, precision/recall/F1, delay,
impact-time error, false alarms per camera-hour and cluster-bootstrap 95 % intervals (resampling
whole clips, seeded so a rerun gives the same interval). ``eval/run_eval.py`` records the alerts;
nothing here reads a clip list or a video.

Counting rules (documented in TD-42):
- Alert time is ``t_fire`` (when the alert was raised); the impact estimate is ``t_peak``.
- A crash clip scores a true positive when a ``collision_candidate``, ``hard_stop`` or sweep
  alert is raised within [impact - 2 s, impact + 10 s] (the earliest one is scored). Further
  crash alerts inside the window are duplicates of the same event, which the API merges into
  one incident (60 s / 50 m): neither true nor false positives. Alerts outside the window, or of
  another trigger, are false positives. No crash alert in the window is a false negative.
- A stalled-vehicle clip has no impact time: any ``stalled_vehicle`` alert is a true positive
  (repeats are duplicates); alerts of other triggers are false positives.
- Alerts on normal or congested clips are false alarms, counted over the camera-hours.
"""

import math
import re
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np

from nadjet_shared.evaluation import (
    AblationRow,
    AiQuality,
    AlertRecord,
    ClipSummary,
    EvaluationResults,
    EventMetrics,
    Interval,
    Metric,
    Percentiles,
    SkippedClip,
)
from nadjet_vision.verdict import VerifyStats

WINDOW_BEFORE_S = 2.0
WINDOW_AFTER_S = 10.0
CRASH_TRIGGERS = frozenset({"collision_candidate", "hard_stop", "ai_sweep"})
COLLISION_RULES = frozenset({"collision_candidate", "hard_stop"})

RULES = "rules"
RULES_VERIFIER = "rules+verifier"
RULES_VERIFIER_SWEEP = "rules+verifier+sweep"
CONFIGS = {
    RULES: "Rule triggers alone: every rule alert counts, the AI is ignored",
    RULES_VERIFIER: "Rule triggers vetoed by the AI verifier when it sees no collision "
    "(or, for stalled and pedestrian alerts, no event)",
    RULES_VERIFIER_SWEEP: "Verified rule alerts plus the sweep's alerts",
}


@dataclass(frozen=True)
class ClipOutcome:
    """Alerts one clip produced, with what the clip is."""

    id: str
    kind: str  # crash | stalled | negative
    duration_s: float
    impact_s: float | None
    alerts: tuple[AlertRecord, ...]


def vetoed(alert: AlertRecord) -> bool:
    """Whether the verifier rejected a rule alert (an unavailable verifier never vetoes)."""
    if alert.source != "rule" or not alert.verifier_available:
        return False
    if alert.trigger in COLLISION_RULES:
        return alert.collision_visible == "no"
    return alert.collision_visible == "no" and alert.ai_status == "possible"


def counts_in(config: str, alert: AlertRecord) -> bool:
    if config == RULES:
        return alert.source == "rule"
    if config == RULES_VERIFIER:
        return alert.source == "rule" and not vetoed(alert)
    if config == RULES_VERIFIER_SWEEP:
        return alert.source == "sweep" or not vetoed(alert)
    raise ValueError(f"unknown configuration {config!r}")


@dataclass(frozen=True)
class ClipScore:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    gt: int = 0
    alerts: int = 0
    negative_alerts: int = 0
    negative_s: float = 0.0
    delay_s: float | None = None
    peak_error_s: float | None = None


def score_clip(
    clip: ClipOutcome,
    config: str,
    before_s: float = WINDOW_BEFORE_S,
    after_s: float = WINDOW_AFTER_S,
) -> ClipScore:
    alerts = sorted((a for a in clip.alerts if counts_in(config, a)), key=lambda a: a.t_fire)
    if clip.kind == "negative":
        return ClipScore(
            fp=len(alerts),
            alerts=len(alerts),
            negative_alerts=len(alerts),
            negative_s=clip.duration_s,
        )
    if clip.kind == "stalled":
        hits = [a for a in alerts if a.trigger == "stalled_vehicle"]
        return ClipScore(
            tp=bool(hits), fn=not hits, fp=len(alerts) - len(hits), gt=1, alerts=len(alerts)
        )
    if clip.impact_s is None:
        raise ValueError(f"crash clip {clip.id!r} has no impact time")
    low, high = clip.impact_s - before_s, clip.impact_s + after_s
    hits = [a for a in alerts if low <= a.t_fire <= high and a.trigger in CRASH_TRIGGERS]
    if not hits:
        return ClipScore(fn=1, fp=len(alerts), gt=1, alerts=len(alerts))
    first = hits[0]
    return ClipScore(
        tp=1,
        fp=len(alerts) - len(hits),
        gt=1,
        alerts=len(alerts),
        delay_s=first.t_fire - clip.impact_s,
        peak_error_s=first.t_peak - clip.impact_s,
    )


def _ratio(num: float, den: float) -> float | None:
    return num / den if den > 0 else None


def _summary(scores: Sequence[ClipScore]) -> dict[str, float | None]:
    tp, fp, fn = (sum(getattr(s, k) for s in scores) for k in ("tp", "fp", "fn"))
    precision, recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall > 0
        else None
    )
    delays = [s.delay_s for s in scores if s.delay_s is not None]
    errors = [s.peak_error_s for s in scores if s.peak_error_s is not None]
    hours = sum(s.negative_s for s in scores) / 3600
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "median_delay_s": statistics.median(delays) if delays else None,
        "mean_peak_error_s": statistics.fmean(errors) if errors else None,
        "false_alarms_per_camera_hour": _ratio(sum(s.negative_alerts for s in scores), hours),
    }


def bootstrap(
    scores: Sequence[ClipScore], samples: int, seed: int
) -> dict[str, tuple[float, float] | None]:
    """Percentile 95 % intervals by resampling whole clips (seeded, so reruns agree)."""
    if not scores:
        return {k: None for k in _summary([])}
    rng = np.random.default_rng(seed)
    draws: dict[str, list[float]] = {k: [] for k in _summary([])}
    for _ in range(samples):
        picks = rng.integers(0, len(scores), size=len(scores))
        for key, value in _summary([scores[i] for i in picks]).items():
            if value is not None:
                draws[key].append(value)
    out: dict[str, tuple[float, float] | None] = {}
    for key, values in draws.items():
        out[key] = (
            (float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5)))
            if len(values) >= max(2, samples // 10)
            else None
        )
    return out


def evaluate(
    clips: Sequence[ClipOutcome],
    config: str,
    *,
    samples: int = 1000,
    seed: int = 0,
    before_s: float = WINDOW_BEFORE_S,
    after_s: float = WINDOW_AFTER_S,
) -> EventMetrics:
    scores = [score_clip(c, config, before_s, after_s) for c in clips]
    point = _summary(scores)
    intervals = bootstrap(scores, samples, seed)

    def metric(name: str) -> Metric:
        ci = intervals.get(name)
        return Metric(value=point[name], ci=Interval(low=ci[0], high=ci[1]) if ci else None)

    return EventMetrics(
        ground_truth=sum(s.gt for s in scores),
        alerts=sum(s.alerts for s in scores),
        true_positives=sum(s.tp for s in scores),
        false_positives=sum(s.fp for s in scores),
        false_negatives=sum(s.fn for s in scores),
        camera_hours=sum(s.negative_s for s in scores) / 3600,
        precision=metric("precision"),
        recall=metric("recall"),
        f1=metric("f1"),
        median_delay_s=metric("median_delay_s"),
        mean_peak_error_s=metric("mean_peak_error_s"),
        false_alarms_per_camera_hour=metric("false_alarms_per_camera_hour"),
    )


def wilson(successes: int, total: int, z: float = 1.96) -> Metric:
    """A share with its Wilson 95 % interval (``None`` value when nothing was counted)."""
    if total == 0:
        return Metric()
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return Metric(value=p, ci=Interval(low=max(0.0, centre - half), high=min(1.0, centre + half)))


def ai_quality(stats: VerifyStats) -> AiQuality:
    tried = stats.answered + stats.invalid
    return AiQuality(
        verifications=stats.answered,
        valid_first_try=wilson(stats.valid_first_try, tried),
        dropped_citation_share=wilson(stats.findings_dropped, stats.findings_total),
        cannot_judge_share=wilson(stats.cannot_judge, stats.answered),
        unavailable=stats.unavailable,
    )


def percentiles(values: Sequence[float]) -> Percentiles:
    if not values:
        return Percentiles(count=0)
    return Percentiles(
        count=len(values),
        p50=float(np.percentile(values, 50)),
        p95=float(np.percentile(values, 95)),
    )


# ------------------------------------------------------------------ reproducibility


def _agrees(a: Metric, b: Metric) -> bool:
    if a.value is None or b.value is None:
        return a.value is None and b.value is None
    if a.ci is None or b.ci is None:
        return math.isclose(a.value, b.value, abs_tol=1e-9)
    return a.ci.low <= b.value <= a.ci.high and b.ci.low <= a.value <= b.ci.high


def compare_runs(first: EvaluationResults, second: EvaluationResults) -> list[str]:
    """Metrics of two runs that do not agree within each other's interval (empty = reproducible)."""
    names = ("precision", "recall", "f1", "median_delay_s", "mean_peak_error_s")
    rows = {r.name: r for r in second.ablation}
    problems: list[str] = []
    for row in first.ablation:
        other = rows.get(row.name)
        if other is None or (row.metrics is None) != (other.metrics is None):
            problems.append(f"{row.name}: present in only one run")
            continue
        if row.metrics is None or other.metrics is None:
            continue
        for name in (*names, "false_alarms_per_camera_hour"):
            if not _agrees(getattr(row.metrics, name), getattr(other.metrics, name)):
                problems.append(f"{row.name}.{name}: runs disagree beyond the interval")
    return problems


# ------------------------------------------------------------------ tuning guard


def tuning_references(clip_ids: Sequence[str], files: Mapping[str, str]) -> list[str]:
    """``file: id`` for every evaluation clip id that a tuning file mentions."""
    found: list[str] = []
    for name, text in sorted(files.items()):
        for clip_id in clip_ids:
            if re.search(rf"(?<![\w-]){re.escape(clip_id)}(?![\w-])", text):
                found.append(f"{name}: {clip_id}")
    return found


def tuned_camera_clips(cameras: Sequence[Mapping[str, Any]], clip_ids: Sequence[str]) -> list[str]:
    """Cameras with per-camera trigger overrides whose clip is an evaluation clip: those
    overrides could have been tuned on it (FR-VIS-022)."""
    return [
        f"camera {c['id']} (clip {c['clip_id']}) has trigger overrides"
        for c in cameras
        if c.get("triggers") and c.get("clip_id") in clip_ids
    ]


# ------------------------------------------------------------------ results file

BOXES_NOT_RUN = (
    "TQ-06 is open: boxes drawn on the verifier frames are not implemented (the verifier "
    "gets timestamps only), so there is nothing to compare"
)


def build_results(
    *,
    outcomes: Sequence[ClipOutcome],
    skipped: Sequence[SkippedClip],
    stats: VerifyStats | None,
    latency_ms: Mapping[str, Sequence[float]],
    git_sha: str,
    dirty: bool,
    seed: int,
    samples: int,
    models: Mapping[str, str],
    generated_at: datetime,
) -> EvaluationResults:
    """Assemble the results file from the replayed clips (``stats`` None = AI was switched off)."""
    ai = stats is not None
    ablation: list[AblationRow] = []
    for name, description in CONFIGS.items():
        if name != RULES and not ai:
            ablation.append(
                AblationRow(name=name, description=description, not_run_reason="AI switched off")
            )
            continue
        metrics = evaluate(outcomes, name, samples=samples, seed=seed)
        ablation.append(AblationRow(name=name, description=description, metrics=metrics))
    ablation.append(
        AblationRow(
            name="boxes on vs off",
            description="Drawn boxes on the verifier frames, on vs off (TQ-06)",
            not_run_reason=BOXES_NOT_RUN,
        )
    )
    hours = sum(c.duration_s for c in outcomes if c.kind == "negative") / 3600
    crashes = sum(c.kind == "crash" for c in outcomes)
    limitations = [
        f"{len(outcomes)} clips scored ({crashes} crash): intervals are wide, read them as such",
        "Public datasets are research-only; clips are used for evaluation and demo only",
        "Detection delay is stream time between the annotated impact and the alert, "
        "without network and queue time",
    ]
    if hours < 1.0:
        limitations.append(
            f"Only {hours:.2f} camera-hours of normal and congested footage "
            "(target: at least 1): the false-alarm rate is not yet meaningful"
        )
    if skipped:
        limitations.append(f"{len(skipped)} clips were not scored: see skipped_clips")
    return EvaluationResults(
        generated_at=generated_at,
        git_sha=git_sha,
        dirty=dirty,
        seed=seed,
        bootstrap_samples=samples,
        window_before_s=WINDOW_BEFORE_S,
        window_after_s=WINDOW_AFTER_S,
        models=dict(models),
        clips=[
            ClipSummary(
                id=c.id,
                kind=c.kind,
                duration_s=c.duration_s,
                impact_s=c.impact_s,
                alerts=list(c.alerts),
            )
            for c in outcomes
        ],
        skipped_clips=list(skipped),
        camera_hours=hours,
        meets_camera_hour_target=hours >= 1.0,
        ablation=ablation,
        ai_quality=ai_quality(stats) if stats is not None else None,
        latency_ms={name: percentiles(values) for name, values in latency_ms.items()},
        limitations=limitations,
    )


def _fmt(metric: Metric, digits: int = 2) -> str:
    if metric.value is None:
        return "n/a"
    text = f"{metric.value:.{digits}f}"
    if metric.ci is not None:
        text += f" [{metric.ci.low:.{digits}f}, {metric.ci.high:.{digits}f}]"
    return text


def render_markdown(results: EvaluationResults) -> str:
    """Human summary of a results file (values with their 95 % intervals)."""
    lines = [
        f"# Evaluation {results.generated_at:%Y-%m-%d} ({results.git_sha}"
        f"{', dirty' if results.dirty else ''})",
        "",
        f"Clips scored: {len(results.clips)}, skipped: {len(results.skipped_clips)}. "
        f"Negative footage: {results.camera_hours:.2f} camera-hours. "
        f"Bootstrap: {results.bootstrap_samples} resamples of clips, seed {results.seed}; "
        "brackets are 95 % intervals.",
        "",
        "| Configuration | Precision | Recall | F1 | Median delay (s) | Peak error (s) "
        "| False alarms / camera-hour |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in results.ablation:
        if row.metrics is None:
            lines.append(f"| {row.name} | not run: {row.not_run_reason} | | | | | |")
            continue
        m = row.metrics
        lines.append(
            f"| {row.name} | {_fmt(m.precision)} | {_fmt(m.recall)} | {_fmt(m.f1)} | "
            f"{_fmt(m.median_delay_s, 1)} | {_fmt(m.mean_peak_error_s, 1)} | "
            f"{_fmt(m.false_alarms_per_camera_hour)} |"
        )
    if results.ai_quality is not None:
        q = results.ai_quality
        lines += [
            "",
            f"AI quality over {q.verifications} answers ({q.unavailable} unavailable): "
            f"valid JSON first try {_fmt(q.valid_first_try)}, findings dropped for invalid "
            f"citations {_fmt(q.dropped_citation_share)}, "
            f"cannot judge {_fmt(q.cannot_judge_share)}.",
        ]
    if results.latency_ms:
        lines += ["", "| Stage | Count | p50 (ms) | p95 (ms) |", "|---|---|---|---|"]
        for name, p in sorted(results.latency_ms.items()):
            p50 = "n/a" if p.p50 is None else f"{p.p50:.0f}"
            p95 = "n/a" if p.p95 is None else f"{p.p95:.0f}"
            lines.append(f"| {name} | {p.count} | {p50} | {p95} |")
    if results.skipped_clips:
        lines += ["", "Skipped:", *(f"- {s.id}: {s.reason}" for s in results.skipped_clips)]
    lines += ["", "Limitations:", *(f"- {text}" for text in results.limitations), ""]
    return "\n".join(lines)
