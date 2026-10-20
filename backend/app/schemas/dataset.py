"""Dataset provenance and leakage-safe split inputs."""

from typing import Annotated, Literal

from pydantic import Field

from app.schemas.common import Contract
from app.schemas.product import AnnotationBox


class DatasetImage(Contract):
    image_id: Annotated[str, Field(min_length=1, max_length=100)]
    sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]
    setup_id: Annotated[str, Field(min_length=1, max_length=100)]
    capture_session_id: Annotated[str, Field(min_length=1, max_length=100)]
    consent_for_training: bool
    review_status: Literal["draft", "reviewed"]
    boxes: list[AnnotationBox]
    content_url: str | None = None
    image_path: str | None = None


class DatasetManifest(Contract):
    schema_version: Literal["1.0"] = "1.0"
    images: Annotated[list[DatasetImage], Field(max_length=10000)]
    note: str = ""
