"""Stable error envelope shared by schema and semantic validation."""

from typing import Literal

from pydantic import Field

from app.schemas.common import Contract


class ValidationIssue(Contract):
    code: str
    message: str
    path: list[str | int] = Field(default_factory=list)


class ValidationResult(Contract):
    schema_version: Literal["1.0"] = "1.0"
    valid: bool
    validation_scope: Literal["netlist_structure"] = "netlist_structure"
    ready_to_build: Literal[False] = False
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
