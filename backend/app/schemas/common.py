"""Shared validation policy for externally supplied data."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")]
PositiveNumber = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class Contract(BaseModel):
    """Reject misspellings, coercion, and unsupported fields rather than guessing."""

    model_config = ConfigDict(extra="forbid", strict=True)
