"""Pure rules of the hospital pre-alert view (FR-HSP-001, FR-INC-008). No I/O."""

from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timedelta

TAGS = ("red", "yellow", "green", "black")


def victim_counts(tags: Iterable[str]) -> dict[str, int]:
    """Victims per START tag and in total; unknown tags still count in the total."""
    counted = Counter(tags)
    counts = {tag: counted.get(tag, 0) for tag in TAGS}
    counts["total"] = sum(counted.values())
    return counts


def expected_arrival(dispatched_at: datetime, eta_s: float) -> datetime:
    """When the ambulance is due: the dispatch time plus the stored road ETA."""
    return dispatched_at + timedelta(seconds=eta_s)
