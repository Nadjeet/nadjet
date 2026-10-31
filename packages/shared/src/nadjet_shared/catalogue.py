"""Camera catalogue (``data/cameras.yaml``) and per-camera zones (``data/zones/<id>.json``).

Shared by the simulator (``nadjet_camsim``) and the API camera registry (PRD FR-CAM-001,
FR-ADM-001). Zone polygons are in image coordinates of the frame size the zones file declares.
"""

import re
from itertools import pairwise
from pathlib import Path
from typing import Annotated, Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

PATH_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")

Point = Annotated[tuple[float, float], Field(description="(x, y) in image pixels")]
MIN_RING_POINTS = 4  # a triangle plus the closing point


class CatalogueError(ValueError):
    """The catalogue or a zones file is unreadable or invalid (message names the file)."""


class Frame(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: int = Field(gt=0)
    height: int = Field(gt=0)


def _area(ring: list[Point]) -> float:
    """Absolute polygon area (shoelace formula)."""
    twice = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in pairwise(ring))
    return abs(twice) / 2


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _segments_cross(p1: Point, p2: Point, q1: Point, q2: Point) -> bool:
    """Proper crossing of two segments (shared end points do not count)."""
    d1, d2 = _cross(q1, q2, p1), _cross(q1, q2, p2)
    d3, d4 = _cross(p1, p2, q1), _cross(p1, p2, q2)
    return d1 * d2 < 0 and d3 * d4 < 0


def _self_intersects(ring: list[Point]) -> bool:
    edges = list(pairwise(ring))
    for i, (a1, a2) in enumerate(edges):
        for j in range(i + 2, len(edges)):
            if i == 0 and j == len(edges) - 1:
                continue  # first and last edges meet at the closing point
            if _segments_cross(a1, a2, *edges[j]):
                return True
    return False


class Zones(BaseModel):
    """Live lanes and carriageway of one camera. Each polygon ring must be explicitly closed."""

    model_config = ConfigDict(extra="forbid")

    frame: Frame
    live_lanes: list[list[Point]] = Field(min_length=1)
    carriageway: list[Point]

    @model_validator(mode="after")
    def _valid_polygons(self) -> "Zones":
        rings = {f"live_lanes[{i}]": r for i, r in enumerate(self.live_lanes)}
        rings["carriageway"] = self.carriageway
        for name, ring in rings.items():
            if len(ring) < MIN_RING_POINTS:
                raise ValueError(f"{name}: needs at least {MIN_RING_POINTS} points (closed ring)")
            if ring[0] != ring[-1]:
                raise ValueError(f"{name}: polygon is not closed (last point must equal first)")
            for x, y in ring:
                if not (0 <= x <= self.frame.width and 0 <= y <= self.frame.height):
                    raise ValueError(
                        f"{name}: point ({x}, {y}) is outside the "
                        f"{self.frame.width}x{self.frame.height} frame"
                    )
            if _area(ring) == 0:
                raise ValueError(f"{name}: polygon has zero area")
            if _self_intersects(ring):
                raise ValueError(f"{name}: polygon edges cross each other (self-intersecting)")
        return self


class GeoPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: float = Field(ge=18.9, le=37.2, description="Inside Algeria's bounding box")
    lon: float = Field(ge=-8.7, le=12.0)


class Camera(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    video: str = Field(description="File name inside the videos directory")
    clip_id: str = Field(description="Id of the clip in eval/heldout.json (FR-VIS-022)")
    geo: GeoPoint
    road: str
    pk_km: float | None = None
    heading_deg: float = Field(default=0, ge=0, lt=360)
    wilaya: str
    zones: Zones | None = Field(default=None, description="Loaded from data/zones/<id>.json")
    triggers: dict[str, float] = Field(
        default_factory=dict,
        description="Per-camera trigger thresholds overriding the doc 11 §6 defaults (FR-VIS-004)",
    )

    @field_validator("id")
    @classmethod
    def valid_path_name(cls, value: str) -> str:
        if not PATH_NAME.match(value):
            raise ValueError("id must be lowercase letters, digits and dashes (MediaMTX path)")
        return value


class Catalogue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cameras: list[Camera]

    @field_validator("cameras")
    @classmethod
    def unique_ids(cls, cameras: list[Camera]) -> list[Camera]:
        ids = [c.id for c in cameras]
        if len(ids) != len(set(ids)):
            raise ValueError("camera ids must be unique")
        return cameras


def load_zones(path: Path) -> Zones:
    try:
        return Zones.model_validate_json(path.read_text())
    except ValidationError as exc:
        raise CatalogueError(f"invalid zones file {path}: {exc}") from exc


def load_catalogue(path: Path, zones_dir: Path | None = None) -> Catalogue:
    """Load the catalogue; each camera gets the zones in ``<zones_dir>/<id>.json`` if present."""
    raw: dict[str, Any] = yaml.safe_load(path.read_text())
    zones_dir = zones_dir if zones_dir is not None else path.parent / "zones"
    catalogue = Catalogue.model_validate(raw)
    for camera in catalogue.cameras:
        zones_file = zones_dir / f"{camera.id}.json"
        if zones_file.is_file():
            camera.zones = load_zones(zones_file)
    return catalogue
