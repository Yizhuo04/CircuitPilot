"""Evaluate pixel-space detection JSON, separately from electrical verification."""

import argparse
import json
from pathlib import Path

from app.services.dataset import evaluate_detections


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("truth", type=Path)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate_detections(
        json.loads(args.truth.read_text()), json.loads(args.predictions.read_text())
    )
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
