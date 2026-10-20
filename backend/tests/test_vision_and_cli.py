import hashlib
import io
import json
import sys
from importlib.resources import files
from types import SimpleNamespace

import numpy as np
import pytest
from app.config import Settings
from app.dataset_cli import download
from app.dataset_cli import main as dataset_main
from app.schemas.circuit import Circuit
from app.schemas.dataset import DatasetManifest
from app.schemas.product import CalibrationPoint, VerificationRequest
from app.services.breadboard import Breadboard, reference_board
from app.services.calibration import CalibrationError, calibrate
from app.services.dataset import CLASSES
from app.services.detection import Detection, LocalYOLODetector, compare_observations
from app.services.placement_engine import generate_plan
from app.services.storage import InvalidImage, LocalObjectStore
from PIL import Image
from pydantic import ValidationError


@pytest.fixture(scope="module")
def vision_plan():
    circuit = Circuit.model_validate_json(
        files("app").joinpath("data/circuits/series_led.json").read_text()
    )
    return generate_plan(circuit, Breadboard(reference_board()))


def reference_points():
    return [
        CalibrationPoint(hole_id=hole, x=x, y=y)
        for hole, x, y in [("A1", 80, 40), ("J1", 540, 40), ("J63", 540, 440), ("A63", 80, 440)]
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda points: setattr(points[0], "x", 640.0),
        lambda points: setattr(points[0], "y", 480.0),
        lambda points: [setattr(point, "x", 640 - point.x) for point in points],
        lambda points: setattr(points[2], "y", 42.0),
    ],
)
def test_bad_calibration_rejected(vision_plan, mutation):
    points = reference_points()
    mutation(points)
    with pytest.raises(CalibrationError):
        calibrate(Breadboard(reference_board()), points, 640, 480, vision_plan)


def test_duplicate_reference_holes_rejected():
    points = [point.model_dump() for point in reference_points()]
    points[1]["hole_id"] = "A1"
    with pytest.raises(ValidationError):
        VerificationRequest(plan_id="plan", image_id="image", calibration_points=points)


def test_detector_observations_remain_uncertain_and_do_not_mutate_plan(vision_plan):
    result = calibrate(Breadboard(reference_board()), reference_points(), 640, 480, vision_plan)
    before = vision_plan.model_dump_json()
    component = vision_plan.layout.components[0]
    points = [result["holes"][hole] for hole in component.pins.values()]
    cx, cy = sum(p["x"] for p in points) / len(points), sum(p["y"] for p in points) / len(points)
    observations = compare_observations(
        vision_plan,
        result,
        [
            Detection("led", 0.73, (cx - 5, cy - 5, 10, 10)),
            Detection("wire_endpoint", 0.65, (79, 39, 2, 2)),
        ],
    )
    assert any(item["type"] == "possible_component_observation" for item in observations)
    assert any(item["type"] == "not_observed_or_occluded" for item in observations)
    endpoint = next(item for item in observations if item["type"] == "possible_wire_endpoint")
    assert endpoint["nearest_hole"] == "A1" and endpoint["confidence_calibrated"] is False
    assert vision_plan.model_dump_json() == before


def test_optional_model_adapter_requires_matching_artifact_provenance(tmp_path, monkeypatch):
    weights = tmp_path / "train/weights/best.pt"
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b"unit-test-double-not-a-trained-model")
    report = {
        "model_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
        "held_out_metrics": {"test_only": True},
    }
    (tmp_path / "training-report.json").write_text(json.dumps(report))
    box = SimpleNamespace(
        xyxy=np.array([[10, 20, 30, 50]]), cls=np.array([1]), conf=np.array([0.73])
    )
    model = SimpleNamespace(
        names=dict(enumerate(CLASSES)), predict=lambda **kwargs: [SimpleNamespace(boxes=[box])]
    )
    monkeypatch.setattr(
        "app.services.detection.importlib.import_module",
        lambda name: SimpleNamespace(YOLO=lambda path: model),
    )
    detector = LocalYOLODetector(tmp_path)
    found = detector.predict(tmp_path / "photo.png")
    assert found == [Detection("led", 0.73, (10, 20, 20, 30))]
    assert detector.version.startswith("yolo-")
    model.names = {0: "unknown-part"}
    with pytest.raises(ValueError, match="class names"):
        LocalYOLODetector(tmp_path)
    report["model_sha256"] = "0" * 64
    (tmp_path / "training-report.json").write_text(json.dumps(report))
    with pytest.raises(ValueError, match="provenance"):
        LocalYOLODetector(tmp_path)


def test_storage_validates_format_and_strips_metadata(tmp_path):
    store = LocalObjectStore(tmp_path)
    for key in ["../escape.png", "bad/name.png", "secret.txt"]:
        with pytest.raises(ValueError):
            store.path(key)
    with pytest.raises(InvalidImage):
        store.save_image("image.png", b"", 100)
    gif = io.BytesIO()
    Image.new("RGB", (100, 100)).save(gif, format="GIF")
    with pytest.raises(InvalidImage, match="PNG and JPEG"):
        store.save_image("image.png", gif.getvalue(), 1024 * 1024)
    jpeg = io.BytesIO()
    source = Image.new("RGB", (80, 60), "red")
    exif = Image.Exif()
    exif[270] = "private metadata"
    source.save(jpeg, format="JPEG", exif=exif)
    _, width, height = store.save_image("image.png", jpeg.getvalue(), 1024 * 1024)
    assert (width, height) == (80, 60)
    with Image.open(store.path("image.png")) as normalized:
        assert normalized.getexif() == {}
    store.delete("image.png")
    assert not store.path("image.png").exists()


def test_production_settings_fail_closed():
    with pytest.raises(ValidationError, match="secure cookies"):
        Settings(environment="production")
    with pytest.raises(ValidationError, match="PostgreSQL"):
        Settings(environment="production", cookie_secure=True, auto_create_schema=False)
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            environment="production",
            cookie_secure=True,
            auto_create_schema=False,
            database_url="postgresql+psycopg://localhost/test",
        )
    settings = Settings(
        environment="production",
        cookie_secure=True,
        auto_create_schema=False,
        database_url="postgresql+psycopg://localhost/test",
        allowed_origins=["https://app.example.com"],
    )
    assert settings.cookie_secure


def test_dataset_downloader_and_export_cli(tmp_path, monkeypatch):
    payload = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(payload, format="PNG")
    image_bytes = payload.getvalue()
    manifest = DatasetManifest.model_validate(
        {
            "images": [
                {
                    "image_id": "image1",
                    "sha256": hashlib.sha256(image_bytes).hexdigest(),
                    "width": 64,
                    "height": 64,
                    "setup_id": "setup1",
                    "capture_session_id": "session1",
                    "consent_for_training": True,
                    "review_status": "reviewed",
                    "boxes": [],
                    "content_url": "/api/v1/images/00000000-0000-0000-0000-000000000001/content",
                }
            ]
        }
    )
    monkeypatch.setattr("app.dataset_cli.getpass.getpass", lambda prompt: "unit-test-password")
    requests = []

    def fake_open(request, timeout):
        requests.append(request)
        return io.BytesIO(
            b'{"access_token":"unit-test-session"}'
            if request.full_url.endswith("/auth/login")
            else image_bytes
        )

    monkeypatch.setattr("app.dataset_cli.urlopen", fake_open)
    output = tmp_path / "download"
    download(manifest, "http://127.0.0.1:8000", "test@example.com", output)
    assert (output / "manifest.json").exists()
    assert (output / manifest.images[0].image_path).read_bytes() == image_bytes
    assert requests[1].get_header("Authorization") == "Bearer unit-test-session"
    with pytest.raises(ValueError, match="HTTPS"):
        download(manifest, "http://remote.example.com", "test@example.com", tmp_path / "unsafe")
    calls = []
    monkeypatch.setattr(
        "app.dataset_cli.export_yolo", lambda *args: calls.append(args) or {"train": ["one"]}
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["dataset", "export-yolo", str(output / "manifest.json"), str(tmp_path / "yolo")],
    )
    dataset_main()
    assert calls[0][1] == output
