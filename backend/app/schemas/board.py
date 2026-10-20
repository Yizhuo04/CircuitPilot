"""Explicit board geometry and conductive groups, independent of circuit nets."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.schemas.common import Contract, Identifier, PositiveNumber


class Point(Contract):
    x: Annotated[float, Field(allow_inf_nan=False)]
    y: Annotated[float, Field(allow_inf_nan=False)]


class Region(Contract):
    id: Identifier
    minimum: Point
    maximum: Point

    @model_validator(mode="after")
    def ordered_bounds(self) -> "Region":
        if self.minimum.x >= self.maximum.x or self.minimum.y >= self.maximum.y:
            raise ValueError("region minimum must precede maximum on both axes")
        return self


class Hole(Contract):
    id: Identifier
    position: Point
    conductive_group_id: Identifier


class RailSegment(Contract):
    id: Identifier
    label: Literal["+", "-"]
    conductive_group_id: Identifier
    hole_ids: Annotated[list[Identifier], Field(min_length=1)]


class BoardModel(Contract):
    model_id: Identifier
    revision: Identifier
    verification_status: Literal["reference_unverified", "physically_verified"]
    verification_evidence: str | None = None
    coordinate_units: Literal["mm"] = "mm"
    pitch_mm: PositiveNumber
    terminal_rows: Annotated[int, Field(gt=0)]
    terminal_columns: list[str]
    holes: Annotated[list[Hole], Field(min_length=1)]
    rail_segments: list[RailSegment] = Field(default_factory=list)
    keep_out_regions: list[Region] = Field(default_factory=list)
    supported_footprints: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def integrity(self) -> "BoardModel":
        holes = {hole.id: hole for hole in self.holes}
        if len(holes) != len(self.holes):
            raise ValueError("hole IDs must be unique")
        if self.verification_status == "physically_verified" and not self.verification_evidence:
            raise ValueError("physical verification requires recorded measurement evidence")
        ids = [segment.id for segment in self.rail_segments]
        groups = [segment.conductive_group_id for segment in self.rail_segments]
        if len(set(ids)) != len(ids) or len(set(groups)) != len(groups):
            raise ValueError("rail segment IDs and conductive groups must be unique")
        used: set[str] = set()
        for segment in self.rail_segments:
            if len(set(segment.hole_ids)) != len(segment.hole_ids):
                raise ValueError("rail segment repeats a hole")
            for hole_id in segment.hole_ids:
                if hole_id not in holes or hole_id in used:
                    raise ValueError("rail hole is unknown or assigned to multiple segments")
                if holes[hole_id].conductive_group_id != segment.conductive_group_id:
                    raise ValueError("rail segment and hole conductive groups disagree")
                used.add(hole_id)
            actual = {
                h.id for h in self.holes if h.conductive_group_id == segment.conductive_group_id
            }
            if actual != set(segment.hole_ids):
                raise ValueError("rail segment must enumerate every hole in its conductive group")
        return self
