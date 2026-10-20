"""Generate or check public JSON contracts and the synthetic board fixture."""

import argparse
import json
from pathlib import Path

from app.schemas.board import BoardModel
from app.schemas.circuit import Circuit
from app.schemas.validation import ValidationResult
from app.services.breadboard import reference_board


def artifacts() -> dict[str, str]:
    data = {
        "circuit_schema.json": Circuit.model_json_schema(),
        "board_schema.json": BoardModel.model_json_schema(),
        "validation_schema.json": ValidationResult.model_json_schema(),
        "boards/bb830-reference-r1.json": reference_board().model_dump(mode="json"),
    }
    return {
        name: json.dumps(value, indent=2, sort_keys=True) + "\n" for name, value in data.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("shared"))
    arguments = parser.parse_args()
    for name, expected in artifacts().items():
        path = arguments.output / name
        if arguments.check:
            if not path.is_file() or path.read_text() != expected:
                parser.exit(1, f"Generated artifact out of date: {path}\n")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected)


if __name__ == "__main__":
    main()
