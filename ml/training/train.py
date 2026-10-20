"""Optional real-data detector training. No weights or dataset download is implicit."""

import argparse
import hashlib
import json
from pathlib import Path

from app.schemas.dataset import DatasetManifest
from app.services.dataset import grouped_split


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dataset", type=Path, help="Export directory containing dataset.yaml and provenance.json"
    )
    parser.add_argument(
        "--weights",
        type=Path,
        required=True,
        help="Trusted local, appropriately licensed starting weights",
    )
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.weights.is_file() or not args.dataset.joinpath("dataset.yaml").is_file():
        parser.error("Existing local weights and an exported dataset are required.")
    provenance = json.loads(args.dataset.joinpath("provenance.json").read_text())
    manifest = DatasetManifest.model_validate(provenance["manifest"])
    if grouped_split(manifest, provenance["seed"]) != provenance["splits"]:
        parser.error("Dataset provenance is inconsistent or leaks between splits.")
    if args.epochs < 1 or args.epochs > 1000:
        parser.error("epochs must be in [1,1000]")
    try:
        from ultralytics import YOLO
    except ImportError:
        parser.error("Install the optional training environment described in ml/README.md first.")
    model = YOLO(str(args.weights))
    model.train(
        data=str(args.dataset.resolve() / "dataset.yaml"),
        epochs=args.epochs,
        seed=args.seed,
        deterministic=True,
        project=str(args.output),
        name="train",
        exist_ok=False,
    )
    # Train/val are used for fitting and model selection; evaluate test only afterward.
    best = args.output / "train/weights/best.pt"
    held_out = YOLO(str(best)).val(data=str(args.dataset.resolve() / "dataset.yaml"), split="test")
    report = {
        "schema_version": "1.0",
        "model_sha256": hashlib.sha256(best.read_bytes()).hexdigest(),
        "seed": args.seed,
        "epochs": args.epochs,
        "dataset_provenance_sha256": hashlib.sha256(
            (args.dataset / "provenance.json").read_bytes()
        ).hexdigest(),
        "held_out_metrics": held_out.results_dict,
        "confidence_calibrated": False,
        "electrically_verified": False,
    }
    (args.output / "training-report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
