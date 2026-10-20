"""Local object storage adapter. Keys are generated IDs, never caller-controlled paths."""

import hashlib
import io
import os
import tempfile
import warnings
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


class InvalidImage(ValueError):
    pass


class LocalObjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        if not key.endswith(".png") or not key[:-4].isalnum():
            raise ValueError("Invalid object key")
        return self.root / key

    def save_image(self, key: str, data: bytes, limit: int) -> tuple[str, int, int]:
        if not data or len(data) > limit:
            raise InvalidImage("Image is empty or exceeds the upload size limit.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as source:
                    if source.format not in {"PNG", "JPEG"}:
                        raise InvalidImage("Only actual PNG and JPEG images are accepted.")
                    if source.width * source.height > 20_000_000 or min(source.size) < 32:
                        raise InvalidImage(
                            "Image must be at least 32 pixels per side and at most 20 megapixels."
                        )
                    source.load()
                    image = ImageOps.exif_transpose(source).convert("RGB")
                    # Re-encoding strips EXIF/location data and untrusted ancillary chunks.
                    encoded = io.BytesIO()
                    image.save(encoded, format="PNG")
        except (
            UnidentifiedImageError,
            OSError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise InvalidImage("Image cannot be decoded safely.") from exc
        normalized = encoded.getvalue()
        if len(normalized) > limit * 2:
            raise InvalidImage("Decoded image is too large to store.")
        destination = self.path(key)
        handle, temporary = tempfile.mkstemp(dir=self.root, prefix=".upload-")
        try:
            with os.fdopen(handle, "wb") as file:
                file.write(normalized)
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return hashlib.sha256(normalized).hexdigest(), image.width, image.height

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)
