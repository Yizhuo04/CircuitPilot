import hashlib

import pytest
from app.schemas.dataset import DatasetManifest
from app.services.dataset import (
    evaluate_detections,
    export_yolo,
    grouped_split,
    intersection_over_union,
)
from PIL import Image


def manifest(count=12):
    return DatasetManifest.model_validate(
        {
            "images": [
                {
                    "image_id": f"image-{index}",
                    "sha256": hashlib.sha256(str(index).encode()).hexdigest(),
                    "width": 640,
                    "height": 480,
                    "setup_id": f"setup-{index}",
                    "capture_session_id": f"session-{index}",
                    "consent_for_training": True,
                    "review_status": "reviewed",
                    "boxes": [],
                }
                for index in range(count)
            ]
        }
    )


def test_group_split_preserves_shared_setup_session_and_duplicates():
    data = manifest()
    data.images[1].setup_id = data.images[0].setup_id
    data.images[2].capture_session_id = data.images[1].capture_session_id
    data.images[3].sha256 = data.images[2].sha256
    result = grouped_split(data, seed=42)
    assert result == grouped_split(data, seed=42)
    owners = {
        identifier: split for split, identifiers in result.items() for identifier in identifiers
    }
    assert len({owners[f"image-{index}"] for index in range(4)}) == 1
    assert all(result.values()) and len(owners) == 12


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: setattr(data.images[0], "consent_for_training", False),
        lambda data: setattr(data.images[0], "review_status", "draft"),
        lambda data: data.images.append(data.images[0]),
    ],
)
def test_invalid_dataset_cannot_enter_training_split(mutation):
    data = manifest()
    mutation(data)
    with pytest.raises(ValueError):
        grouped_split(data)


def test_tiny_or_linked_dataset_cannot_pretend_to_have_independent_test_set():
    with pytest.raises(ValueError, match="three independent"):
        grouped_split(manifest(2))
    data = manifest()
    for image in data.images:
        image.setup_id = "one-physical-circuit"
    with pytest.raises(ValueError, match="three independent"):
        grouped_split(data)


def test_yolo_export_preserves_provenance_and_validates_content(tmp_path):
    data = manifest(3)
    source = tmp_path / "source"
    source.mkdir()
    for index, image in enumerate(data.images):
        image.image_path = f"{index}.png"
        Image.new("RGB", (640, 480), (index, 255, 255)).save(source / image.image_path)
        image.sha256 = hashlib.sha256((source / image.image_path).read_bytes()).hexdigest()
    destination = tmp_path / "export"
    result = export_yolo(data, source, destination)
    assert all(len(ids) == 1 for ids in result.values())
    assert (destination / "provenance.json").is_file()
    assert (destination / "dataset.yaml").is_file()
    assert len(list(destination.glob("labels/*/*.txt"))) == 3
    # No overwrite, no tampered bytes, no arbitrary paths.
    with pytest.raises(FileExistsError):
        export_yolo(data, source, destination)
    data.images[0].sha256 = "0" * 64
    with pytest.raises(ValueError, match="hash"):
        export_yolo(data, source, tmp_path / "tampered")
    data.images[0].image_path = "../outside.png"
    with pytest.raises(ValueError, match="within"):
        export_yolo(data, source, tmp_path / "traversal")


def test_detection_metrics_penalize_duplicates_and_missing_parts():
    actual = [
        {"image_id": "one", "class_name": "led", "box": [10, 10, 20, 20]},
        {"image_id": "two", "class_name": "led", "box": [10, 10, 20, 20]},
    ]
    predictions = [
        {"image_id": "one", "class_name": "led", "box": [10, 10, 20, 20], "score": 0.9},
        {"image_id": "one", "class_name": "led", "box": [10, 10, 20, 20], "score": 0.8},
    ]
    report = evaluate_detections(actual, predictions)
    assert report["per_class"]["led"]["precision_at_0_5"] == 0.5
    assert report["per_class"]["led"]["recall_at_0_5"] == 0.5
    assert report["map50"] == 0.5
    assert report["confidence_calibrated"] is False
    assert report["per_class"]["resistor"]["ap50"] is None
    assert evaluate_detections([], [])["map50"] is None
    assert intersection_over_union([0, 0, 10, 10], [20, 20, 10, 10]) == 0
    assert intersection_over_union([0, 0, 10, 10], [0, 0, 10, 10]) == 1


@pytest.mark.parametrize(
    "prediction",
    [
        {"image_id": "one", "class_name": "unknown", "box": [0, 0, 10, 10], "score": 0.5},
        {"image_id": "one", "class_name": "led", "box": [0, 0, -10, 10], "score": 0.5},
        {"image_id": "one", "class_name": "led", "box": [0, float("inf"), 10, 10], "score": 0.5},
        {"image_id": "one", "class_name": "led", "box": [0, 0, 10, 10], "score": 1.1},
    ],
)
def test_metrics_reject_invalid_predictions(prediction):
    with pytest.raises(ValueError):
        evaluate_detections([], [prediction])
