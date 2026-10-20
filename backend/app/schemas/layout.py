"""Versioned physical placements. Reference layouts are never safety certificates."""

from typing import Annotated, Literal

from pydantic import Field

from app.schemas.common import Contract, Identifier
from app.schemas.validation import ValidationIssue

Orientation = Literal[0, 180]
FootprintID = Literal[
    "resistor-axial-7_62",
    "led-2_54",
    "button-trench-7_62x5_08",
    "jumper-flex",
    "supply-terminal-flex",
]


class ComponentPlacement(Contract):
    component_id: Identifier
    footprint_id: FootprintID
    anchor: Identifier
    orientation: Orientation = 0
    pins: dict[str, Identifier]


class JumperPlacement(Contract):
    id: Identifier
    net_id: Identifier
    start: Identifier
    end: Identifier
    color: Literal["red", "black", "blue", "green", "yellow"] = "blue"
    length_mm: Annotated[float | None, Field(gt=0, allow_inf_nan=False)] = None


class SupplyPlacement(Contract):
    positive_hole: Identifier
    negative_hole: Identifier


class Layout(Contract):
    schema_version: Literal["1.0"] = "1.0"
    circuit_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    board_model_id: Identifier
    board_revision: Identifier
    planner_version: str = "manual-1"
    seed: int = 0
    components: Annotated[list[ComponentPlacement], Field(max_length=64)]
    jumpers: Annotated[list[JumperPlacement], Field(max_length=128)] = Field(default_factory=list)
    supply: SupplyPlacement | None = None


class LayoutValidationResult(Contract):
    valid: bool
    validation_scope: Literal["physical_connectivity"] = "physical_connectivity"
    ready_to_build: bool = False
    board_physically_verified: bool = False
    footprints_physically_verified: bool = False
    electrically_verified: Literal[False] = False
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    terminal_groups: dict[str, str] = Field(default_factory=dict)


class AssemblyStep(Contract):
    sequence: int
    kind: Literal["safety", "component", "jumper", "supply", "review"]
    title: str
    instruction: str
    holes: list[str] = Field(default_factory=list)
    component_id: str | None = None


class AssemblyPlan(Contract):
    schema_version: Literal["1.0"] = "1.0"
    layout: Layout
    validation: LayoutValidationResult
    steps: list[AssemblyStep]
    reference_only: bool = True
