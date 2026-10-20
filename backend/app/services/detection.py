"""Optional local detector adapter. Observations never overwrite planned coordinates."""

import hashlib
import importlib
import json
import math
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.schemas.layout import AssemblyPlan
from app.services.dataset import CLASSES


@dataclass(frozen=True)
class Detection:
    class_name: str
    score: float
    box: tuple[float, float, float, float]

    @property
    def center(self) -> tuple[float, float]:
        x, y, width, height = self.box
        return x + width / 2, y + height / 2


class Detector(Protocol):
    version: str

    def predict(self, image_path: Path) -> list[Detection]: ...


class LocalYOLODetector:
    def __init__(self, directory: Path) -> None:
        report = json.loads((directory / "training-report.json").read_text())
        weights = directory / "train/weights/best.pt"
        actual = hashlib.sha256(weights.read_bytes()).hexdigest()
        if report.get("model_sha256") != actual or not report.get("held_out_metrics"):
            raise ValueError(
                "Detector weights require matching provenance and held-out evaluation metadata."
            )
        # Operators configure trusted local model files; user uploads cannot select weights.
        module = importlib.import_module("ultralytics")
        self._model: Any = module.YOLO(str(weights))
        if set(self._model.names.values()) != set(CLASSES):
            raise ValueError("Detector class names do not match the CircuitPilot dataset contract.")
        self.version = "yolo-" + actual[:16]
        self._lock = threading.Lock()

    def predict(self, image_path: Path) -> list[Detection]:
        with self._lock:
            results = self._model.predict(source=str(image_path), conf=0.15, verbose=False)
        detections = []
        for result in results:
            for box in result.boxes:
                left, top, right, bottom = [float(value) for value in box.xyxy[0].tolist()]
                detections.append(
                    Detection(
                        class_name=self._model.names[int(box.cls[0])],
                        score=float(box.conf[0]),
                        box=(left, top, right - left, bottom - top),
                    )
                )
        return detections


def compare_observations(
    plan: AssemblyPlan, result: dict[str, Any], detections: list[Detection]
) -> list[dict[str, Any]]:
    holes = result["holes"]
    pitch = math.hypot(holes["A1"]["x"] - holes["A2"]["x"], holes["A1"]["y"] - holes["A2"]["y"])
    available = list(detections)
    observations: list[dict[str, Any]] = []
    for component in plan.layout.components:
        prefix = component.footprint_id.split("-")[0]
        name = {"button": "push_button", "resistor": "resistor", "led": "led"}.get(prefix)
        if name is None:
            continue
        points = [holes[hole] for hole in component.pins.values()]
        center = (
            sum(point["x"] for point in points) / len(points),
            sum(point["y"] for point in points) / len(points),
        )
        candidates = [
            (math.dist(center, detection.center), index, detection)
            for index, detection in enumerate(available)
            if detection.class_name == name
        ]
        candidate = min(candidates, key=lambda item: item[0]) if candidates else None
        if candidate is not None and candidate[0] <= pitch * 4:
            _, index, detection = candidate
            available.pop(index)
            observations.append(
                {
                    "type": "possible_component_observation",
                    "component_id": component.component_id,
                    "score": detection.score,
                    "confidence_calibrated": False,
                    "box": list(detection.box),
                    "message": (
                        f"A possible {name} was detected near {component.component_id}. "
                        "Its terminal holes and electrical connections remain unverified."
                    ),
                }
            )
        else:
            observations.append(
                {
                    "type": "not_observed_or_occluded",
                    "component_id": component.component_id,
                    "message": (
                        f"{component.component_id} was not observed near its expected position. "
                        "It may be missing, occluded, misaligned, or missed by the detector."
                    ),
                }
            )
    for detection in detections:
        if detection.class_name != "wire_endpoint":
            continue
        hole_id, point = min(
            holes.items(),
            key=lambda item: math.dist(detection.center, (item[1]["x"], item[1]["y"])),
        )
        distance = math.dist(detection.center, (point["x"], point["y"]))
        observations.append(
            {
                "type": "possible_wire_endpoint",
                "nearest_hole": hole_id,
                "score": detection.score,
                "confidence_calibrated": False,
                "distance_pixels": round(distance, 2),
                "message": (
                    f"A possible wire endpoint is near {hole_id}. "
                    "Bounding-box centers do not prove insertion into that hole or continuity."
                ),
            }
        )
    return observations
