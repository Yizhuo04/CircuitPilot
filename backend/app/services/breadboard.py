"""Direct conductive topology only. Functional components never merge groups here."""

from collections import defaultdict
from typing import Literal

from app.schemas.board import BoardModel, Hole, Point, RailSegment, Region


class UnknownHoleError(ValueError):
    """A coordinate does not exist on this particular board revision."""


class Breadboard:
    def __init__(self, model: BoardModel) -> None:
        # Retain a private validated snapshot; callers cannot mutate the topology.
        self._model = BoardModel.model_validate(model.model_dump(mode="python"))
        self._holes = {hole.id: hole for hole in self._model.holes}
        grouped: dict[str, list[Hole]] = defaultdict(list)
        for hole in self._model.holes:
            grouped[hole.conductive_group_id].append(hole)
        self._groups = {group: tuple(holes) for group, holes in grouped.items()}

    @property
    def model(self) -> BoardModel:
        return self._model.model_copy(deep=True)

    def get_hole(self, hole_id: str) -> Hole:
        try:
            return self._holes[hole_id].model_copy(deep=True)
        except KeyError:
            raise UnknownHoleError(f"Unknown hole {hole_id!r} on {self._model.model_id}") from None

    def group_for_hole(self, hole_id: str) -> str:
        return self.get_hole(hole_id).conductive_group_id

    def are_directly_connected(self, first: str, second: str) -> bool:
        return self.group_for_hole(first) == self.group_for_hole(second)

    def holes_in_group(self, group_id: str) -> tuple[Hole, ...]:
        try:
            return tuple(hole.model_copy(deep=True) for hole in self._groups[group_id])
        except KeyError:
            raise ValueError(f"Unknown conductive group {group_id!r}") from None


def reference_board() -> BoardModel:
    """630 strip holes plus 200 explicitly segmented reference rail holes.

    This synthetic geometry is not a measurement of any manufacturer's board.
    Rail continuity is defined by the fixture, never inferred from labels.
    """
    pitch = 2.54
    holes = [
        Hole(
            id=f"{column}{row}",
            position=Point(x=(index + (2 if index >= 5 else 0)) * pitch, y=(row - 1) * pitch),
            conductive_group_id=f"STRIP_{'L' if index < 5 else 'R'}_{row}",
        )
        for row in range(1, 64)
        for index, column in enumerate("ABCDEFGHIJ")
    ]
    rails: list[RailSegment] = []
    # Each of four 50-hole rails is explicitly split into two isolated 25-hole groups.
    rail_definitions: list[tuple[str, Literal["+", "-"], float]] = [
        ("L_POS", "+", -4 * pitch),
        ("L_NEG", "-", -2 * pitch),
        ("R_POS", "+", 13 * pitch),
        ("R_NEG", "-", 15 * pitch),
    ]
    for name, label, x in rail_definitions:
        for segment, start, stop in [("TOP", 1, 26), ("BOTTOM", 26, 51)]:
            group = f"RAIL_{name}_{segment}"
            members = []
            for index in range(start, stop):
                hole_id = f"{name}_{index}"
                members.append(hole_id)
                holes.append(
                    Hole(
                        id=hole_id,
                        position=Point(x=x, y=(index - 1) * pitch),
                        conductive_group_id=group,
                    )
                )
            rails.append(
                RailSegment(id=group, label=label, conductive_group_id=group, hole_ids=members)
            )
    return BoardModel(
        model_id="bb830-reference",
        revision="r1",
        verification_status="reference_unverified",
        pitch_mm=pitch,
        terminal_rows=63,
        terminal_columns=list("ABCDEFGHIJ"),
        holes=holes,
        rail_segments=rails,
        keep_out_regions=[
            Region(
                id="CENTER_TRENCH",
                minimum=Point(x=4.5 * pitch, y=-pitch),
                maximum=Point(x=6.5 * pitch, y=63 * pitch),
            )
        ],
    )
