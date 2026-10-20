"""Download consented manifest images and export a leakage-safe YOLO dataset."""

import argparse
import getpass
import json
import re
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.schemas.dataset import DatasetManifest
from app.services.dataset import export_yolo


def download(manifest: DatasetManifest, api_url: str, email: str, destination: Path) -> None:
    parsed = urlparse(api_url)
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
    ):
        raise ValueError("Use HTTPS for remote credentials; HTTP is allowed only for localhost.")
    password = getpass.getpass("CircuitPilot password (not stored): ")
    login = Request(
        api_url.rstrip("/") + "/api/v1/auth/login",
        data=json.dumps({"email": email, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(login, timeout=30) as response:
        token = json.load(response)["access_token"]
    destination.mkdir(parents=True, exist_ok=False)
    for index, image in enumerate(manifest.images):
        if not image.consent_for_training or image.review_status != "reviewed":
            raise ValueError(
                "Download requires reviewed annotations and explicit training consent."
            )
        if image.content_url is None or not re.fullmatch(
            r"/api/v1/images/[a-f0-9-]{36}/content", image.content_url
        ):
            raise ValueError("Manifest contains an unexpected photo URL.")
        request = Request(
            api_url.rstrip("/") + image.content_url, headers={"Authorization": "Bearer " + token}
        )
        with urlopen(request, timeout=60) as response:
            data = response.read(20 * 1024 * 1024 + 1)
        if len(data) > 20 * 1024 * 1024:
            raise ValueError("Downloaded image exceeds the safety limit.")
        filename = f"image-{index:06d}.png"
        (destination / filename).write_bytes(data)
        image.image_path = filename
    (destination / "manifest.json").write_text(manifest.model_dump_json(indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    fetch = subparsers.add_parser("download")
    fetch.add_argument("manifest", type=Path)
    fetch.add_argument("destination", type=Path)
    fetch.add_argument("--api-url", default="http://127.0.0.1:8000")
    fetch.add_argument("--email", required=True)
    export = subparsers.add_parser("export-yolo")
    export.add_argument("manifest", type=Path)
    export.add_argument("destination", type=Path)
    export.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    manifest = DatasetManifest.model_validate_json(args.manifest.read_text())
    if args.command == "download":
        download(manifest, args.api_url, args.email, args.destination)
    else:
        splits = export_yolo(manifest, args.manifest.parent, args.destination, args.seed)
        print(json.dumps({split: len(images) for split, images in splits.items()}))


if __name__ == "__main__":
    main()
