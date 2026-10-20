"""Real-data preparation and object detection metrics; no fabricated model results."""

import hashlib
import json
import random
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from PIL import Image

from app.schemas.dataset import DatasetManifest
from app.services.union_find import UnionFind

CLASSES = ["resistor", "led", "push_button", "wire_endpoint", "board_outline"]


def grouped_split(manifest: DatasetManifest, seed: int = 0) -> dict[str, list[str]]:
    if len({image.image_id for image in manifest.images}) != len(manifest.images):
        raise ValueError("Image IDs must be unique.")
    groups = UnionFind()
    for image in manifest.images:
        if not image.consent_for_training or image.review_status != "reviewed":
            raise ValueError(
                "Every image requires explicit training consent and reviewed annotations."
            )
        key = f"image:{image.image_id}"
        for related in [
            f"setup:{image.setup_id}",
            f"session:{image.capture_session_id}",
            f"hash:{image.sha256}",
        ]:
            groups.union(key, related)
        for box in image.boxes:
            if box.x + box.width > image.width or box.y + box.height > image.height:
                raise ValueError("Annotation box falls outside its image.")
    clusters: dict[str, list[str]] = defaultdict(list)
    for image in manifest.images:
        clusters[groups.find(f"image:{image.image_id}")].append(image.image_id)
    ordered = sorted(clusters.values(), key=lambda ids: sorted(ids))
    if len(ordered) < 3:
        raise ValueError(
            "At least three independent setup/session groups are needed for train/validation/test."
        )
    random.Random(seed).shuffle(ordered)
    validation_count = max(1, round(len(ordered) * 0.15))
    test_count = max(1, round(len(ordered) * 0.15))
    training_count = len(ordered) - validation_count - test_count
    result: dict[str, list[str]] = {"train": [], "val": [], "test": []}
    for index, members in enumerate(ordered):
        split = (
            "train"
            if index < training_count
            else "val"
            if index < training_count + validation_count
            else "test"
        )
        result[split].extend(sorted(members))
    return result


def export_yolo(
    manifest: DatasetManifest, source_root: Path, destination: Path, seed: int = 0
) -> dict[str, list[str]]:
    splits = grouped_split(manifest, seed)
    images = {image.image_id: image for image in manifest.images}
    root = source_root.resolve()
    # Verify every input before creating an export directory or copying data.
    paths: dict[str, Path] = {}
    for image in manifest.images:
        if image.image_path is None:
            raise ValueError("Download each authenticated image first; image_path is required.")
        path = (root / image.image_path).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Dataset image path must remain within the source directory.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != image.sha256:
            raise ValueError("Photo hash does not match its provenance manifest.")
        with Image.open(path) as actual:
            if actual.format != "PNG" or actual.size != (image.width, image.height):
                raise ValueError("Dataset photo format or dimensions disagree with the manifest.")
            actual.verify()
        paths[image.image_id] = path
    destination.mkdir(parents=True, exist_ok=False)
    for split, identifiers in splits.items():
        image_directory, label_directory = (
            destination / "images" / split,
            destination / "labels" / split,
        )
        image_directory.mkdir(parents=True)
        label_directory.mkdir(parents=True)
        for index, identifier in enumerate(identifiers):
            image = images[identifier]
            filename = f"{index:06d}"
            shutil.copyfile(paths[identifier], image_directory / (filename + ".png"))
            labels = [
                f"{CLASSES.index(box.class_name)} {(box.x + box.width / 2) / image.width:.8f} "
                f"{(box.y + box.height / 2) / image.height:.8f} "
                f"{box.width / image.width:.8f} {box.height / image.height:.8f}"
                for box in image.boxes
            ]
            (label_directory / (filename + ".txt")).write_text(
                "\n".join(labels) + ("\n" if labels else "")
            )
    config = (
        f"path: {json.dumps(str(destination.resolve()))}\n"
        "train: images/train\nval: images/val\ntest: images/test\nnames:\n"
    )
    config += "".join(f"  {index}: {name}\n" for index, name in enumerate(CLASSES))
    (destination / "dataset.yaml").write_text(config)
    provenance = {
        "schema_version": "1.0",
        "seed": seed,
        "split_unit": "connected setup/session/content-hash groups",
        "splits": splits,
        "manifest": manifest.model_dump(mode="json"),
    }
    (destination / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    return splits


def intersection_over_union(first: list[float], second: list[float]) -> float:
    # Pixel-space [x, y, width, height].
    left, top = max(first[0], second[0]), max(first[1], second[1])
    right, bottom = (
        min(first[0] + first[2], second[0] + second[2]),
        min(first[1] + first[3], second[1] + second[3]),
    )
    overlap = max(0.0, right - left) * max(0.0, bottom - top)
    union = first[2] * first[3] + second[2] * second[3] - overlap
    return overlap / union if union else 0.0


def evaluate_detections(
    truth: list[dict[str, Any]], predictions: list[dict[str, Any]]
) -> dict[str, Any]:
    """Per-class AP@0.5, precision/recall at score >=0.5, and detection ECE.

    Inputs must be restricted to the held-out setup/session test partition. Empty
    classes have undefined AP and are excluded from mean AP, never counted as perfect.
    """
    for row in truth + predictions:
        if row.get("class_name") not in CLASSES or len(row.get("box", [])) != 4:
            raise ValueError("Unknown class or malformed [x,y,width,height] box.")
        if not all(
            isinstance(x, (int, float)) and x == x and abs(x) != float("inf") for x in row["box"]
        ):
            raise ValueError("Boxes require finite numeric coordinates.")
        if row["box"][2] <= 0 or row["box"][3] <= 0:
            raise ValueError("Boxes require positive width and height.")
    for prediction in predictions:
        if not 0 <= prediction.get("score", -1) <= 1:
            raise ValueError("Prediction scores must lie in [0,1].")
    metrics: dict[str, Any] = {}
    calibration: list[tuple[float, int]] = []
    for name in CLASSES:
        actual = [row for row in truth if row["class_name"] == name]
        predicted = sorted(
            [row for row in predictions if row["class_name"] == name], key=lambda row: -row["score"]
        )
        matched: set[int] = set()
        outcomes = []
        for prediction in predicted:
            candidates = [
                (intersection_over_union(prediction["box"], row["box"]), index)
                for index, row in enumerate(actual)
                if index not in matched and row["image_id"] == prediction["image_id"]
            ]
            overlap, index = max(candidates, default=(0.0, -1))
            correct = int(overlap >= 0.5)
            if correct:
                matched.add(index)
            outcomes.append((prediction["score"], correct))
            calibration.append((prediction["score"], correct))
        positive = 0
        recalls, precisions = [0.0], [0.0]
        for index, (_, correct) in enumerate(outcomes):
            positive += correct
            recalls.append(positive / len(actual) if actual else 0.0)
            precisions.append(positive / (index + 1))
        recalls.append(1.0)
        precisions.append(0.0)
        for index in range(len(precisions) - 2, -1, -1):
            precisions[index] = max(precisions[index], precisions[index + 1])
        ap = (
            sum(
                (recalls[index] - recalls[index - 1]) * precisions[index]
                for index in range(1, len(recalls))
                if recalls[index] != recalls[index - 1]
            )
            if actual
            else None
        )
        selected = [correct for score, correct in outcomes if score >= 0.5]
        metrics[name] = {
            "ground_truth_count": len(actual),
            "prediction_count": len(predicted),
            "ap50": ap,
            "precision_at_0_5": sum(selected) / len(selected) if selected else 0.0,
            "recall_at_0_5": sum(selected) / len(actual) if actual else None,
        }
    averages = [value["ap50"] for value in metrics.values() if value["ap50"] is not None]
    ece = 0.0
    for index in range(10):
        bucket = [
            (score, correct) for score, correct in calibration if min(int(score * 10), 9) == index
        ]
        if bucket:
            ece += (
                abs(
                    sum(score for score, _ in bucket) / len(bucket)
                    - sum(correct for _, correct in bucket) / len(bucket)
                )
                * len(bucket)
                / len(calibration)
            )
    return {
        "iou_threshold": 0.5,
        "per_class": metrics,
        "map50": sum(averages) / len(averages) if averages else None,
        "detection_ece_10_bins": ece if calibration else None,
        "confidence_calibrated": False,
        "note": (
            "Scores are not calibrated probabilities. This evaluator "
            "does not establish physical or electrical correctness."
        ),
    }
