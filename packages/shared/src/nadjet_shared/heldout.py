"""Held-out clip list (``eval/heldout.json``, PRD FR-VIS-022).

Demo clips must be listed here and are never used for tuning. Annotations (impact time and
region) are filled in by a human who watched the clip; ``pending`` marks clips not yet annotated.
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from nadjet_shared.catalogue import Catalogue, CatalogueError

Event = Literal["crash", "heavy_congestion", "stalled_vehicle", "normal"]


class HeldoutClip(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    role: Literal["demo", "eval"]
    event: Event
    source_dataset: str
    source_clip: str | None = Field(default=None, description="File or id inside the dataset")
    licence: str
    licence_url: str
    annotation_status: Literal["pending", "annotated"] = "pending"
    impact_time_s: float | None = Field(default=None, ge=0)
    impact_region: tuple[float, float, float, float] | None = Field(
        default=None, description="x, y, width, height in the normalised frame (pixels)"
    )

    @model_validator(mode="after")
    def _annotation_matches_event(self) -> "HeldoutClip":
        if self.event != "crash" and (self.impact_time_s is not None or self.impact_region):
            raise ValueError(f"{self.id}: only crash clips have an impact time and region")
        if self.annotation_status == "annotated":
            if not self.source_clip:
                raise ValueError(f"{self.id}: annotated clips must name their source_clip")
            if self.event == "crash" and (self.impact_time_s is None or not self.impact_region):
                raise ValueError(
                    f"{self.id}: annotated crash needs impact_time_s and impact_region"
                )
        return self


class Heldout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clips: list[HeldoutClip]

    @model_validator(mode="after")
    def _unique_ids(self) -> "Heldout":
        ids = [c.id for c in self.clips]
        if len(ids) != len(set(ids)):
            raise ValueError("held-out clip ids must be unique")
        return self


def load_heldout(path: Path) -> Heldout:
    try:
        return Heldout.model_validate(json.loads(path.read_text()))
    except (ValidationError, json.JSONDecodeError) as exc:
        raise CatalogueError(f"invalid held-out list {path}: {exc}") from exc


def check_demo_clips(catalogue: Catalogue, heldout: Heldout) -> None:
    """Every camera's clip must be a ``demo`` clip of the held-out list (FR-VIS-022)."""
    roles = {c.id: c.role for c in heldout.clips}
    for camera in catalogue.cameras:
        if roles.get(camera.clip_id) != "demo":
            raise CatalogueError(
                f"camera {camera.id}: clip_id {camera.clip_id!r} is not a demo clip in the "
                "held-out list"
            )
