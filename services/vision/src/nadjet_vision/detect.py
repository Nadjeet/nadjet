"""Object detection behind a ``Detector`` protocol (PRD FR-VIS-002, NFR-MAINT-002).

RF-DETR (Apache-2.0, TD-02) is the production detector; tests use a fake. Weights come from
``models.lock.yaml`` and are checksum-verified before loading (TD-25).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from nadjet_vision.config import VisionSettings
from nadjet_vision.ingest import BgrFrame
from nadjet_vision.models import ensure_weights, load_lock

# COCO category ids used by RF-DETR (1-based): vehicles and people only.
TARGET_CLASSES: dict[int, str] = {1: "person", 3: "car", 4: "motorcycle", 6: "bus", 8: "truck"}

Box = tuple[float, float, float, float]  # x1, y1, x2, y2 in pixels


@dataclass(frozen=True)
class Detection:
    box: Box
    class_id: int
    label: str
    confidence: float

    @property
    def height(self) -> float:
        return self.box[3] - self.box[1]

    @property
    def anchor(self) -> tuple[float, float]:
        """Bottom centre of the box: where the object touches the road."""
        return ((self.box[0] + self.box[2]) / 2, self.box[3])

    @property
    def centre(self) -> tuple[float, float]:
        return ((self.box[0] + self.box[2]) / 2, (self.box[1] + self.box[3]) / 2)


class Detector(Protocol):
    model_id: str

    def detect(self, frame: BgrFrame) -> list[Detection]: ...


def filter_detections(
    raw: Iterable[Detection], threshold: float, allowed: dict[int, str] | None = None
) -> list[Detection]:
    """Keep target classes above the confidence threshold with a non-degenerate box."""
    classes = TARGET_CLASSES if allowed is None else allowed
    return [
        d
        for d in raw
        if d.class_id in classes
        and d.confidence >= threshold
        and d.box[2] > d.box[0]
        and d.box[3] > d.box[1]
    ]


class RfDetrDetector:
    """RF-DETR Medium on the GPU. Imports ``rfdetr`` lazily (gpu extra)."""

    def __init__(self, weights: Path, threshold: float, model_id: str) -> None:
        from rfdetr import RFDETRMedium

        self.model_id = model_id
        self._threshold = threshold
        self._model = RFDETRMedium(pretrain_weights=str(weights))
        self._model.optimize_for_inference()

    def detect(self, frame: BgrFrame) -> list[Detection]:
        rgb = frame[:, :, ::-1]  # RF-DETR expects RGB
        result = self._model.predict(rgb, threshold=self._threshold)
        raw = [
            Detection(
                box=(float(b[0]), float(b[1]), float(b[2]), float(b[3])),
                class_id=int(c),
                label=TARGET_CLASSES.get(int(c), str(int(c))),
                confidence=float(p),
            )
            for b, c, p in zip(result.xyxy, result.class_id, result.confidence, strict=True)
        ]
        return filter_detections(raw, self._threshold)


def load_detector(settings: VisionSettings) -> Detector:
    entry = load_lock(settings.models_lock)[settings.detector_model]
    weights = ensure_weights(entry, settings.weights_dir)
    return RfDetrDetector(weights, settings.detector_threshold, entry.id)
