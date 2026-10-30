"""Response-time durations and their aggregates (FR-KPI-001/002). Pure, no I/O."""

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

# name -> (start, end); "event" is the incident's event_time, the others are the first
# `created` event or the first `status_changed` event moving to that status.
METRICS: dict[str, tuple[str, str]] = {
    "detection_s": ("event", "created"),
    "verification_s": ("created", "verified"),
    "acknowledge_s": ("dispatched", "acknowledged"),
    "scene_s": ("dispatched", "on_scene"),
    "hospital_s": ("dispatched", "at_hospital"),
}


@dataclass(frozen=True)
class Stats:
    n: int
    median_s: float | None
    p90_s: float | None


def milestones(
    event_time: datetime, events: Iterable[tuple[str, dict[str, object], datetime]]
) -> dict[str, datetime]:
    """First time each milestone was reached, from the incident's ``(kind, payload, ts)`` events."""
    reached: dict[str, datetime] = {"event": event_time}
    for kind, payload, ts in sorted(events, key=lambda e: e[2]):
        name = "created" if kind == "created" else str(payload.get("to", "")) or None
        if kind in ("created", "status_changed") and name:
            reached.setdefault(name, ts)
    return reached


def durations(reached: dict[str, datetime]) -> dict[str, float | None]:
    """Seconds per metric; ``None`` when a milestone is missing or out of order."""
    out: dict[str, float | None] = {}
    for name, (start, end) in METRICS.items():
        value = None
        if start in reached and end in reached:
            seconds = (reached[end] - reached[start]).total_seconds()
            value = seconds if seconds >= 0 else None
        out[name] = value
    return out


def percentile(values: Sequence[float], q: float) -> float | None:
    """Linear-interpolated percentile (``q`` in 0..100), the same as numpy's default."""
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * q / 100
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def stats(values: Sequence[float]) -> Stats:
    return Stats(len(values), percentile(values, 50), percentile(values, 90))


def aggregate(rows: Iterable[dict[str, float | None]]) -> dict[str, Stats]:
    """Median and p90 of every metric over the rows that have it."""
    columns: dict[str, list[float]] = {name: [] for name in METRICS}
    for row in rows:
        for name, value in row.items():
            if value is not None:
                columns[name].append(value)
    return {name: stats(values) for name, values in columns.items()}


def group_by[T](items: Iterable[T], keys: Callable[[T], Iterable[str]]) -> dict[str, list[T]]:
    """Bucket ``items`` under every key ``keys`` returns (an item may be in several buckets)."""
    groups: dict[str, list[T]] = defaultdict(list)
    for item in items:
        for key in keys(item):
            groups[key].append(item)
    return dict(groups)


def false_alarm_rate(false_positives: int, total: int) -> float | None:
    return false_positives / total if total else None


def period_key(at: datetime, period: str) -> str:
    """Bucket label: ``2026-10-30`` (day), ``2026-W44`` (week) or ``2026-10`` (month)."""
    if period == "month":
        return at.strftime("%Y-%m")
    if period == "week":
        year, week, _ = at.isocalendar()
        return f"{year}-W{week:02d}"
    return at.strftime("%Y-%m-%d")
