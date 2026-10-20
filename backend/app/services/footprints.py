"""Narrow reference footprint catalog. Dimensions require physical confirmation."""

from collections.abc import Iterator

from app.schemas.circuit import Component
from app.schemas.layout import ComponentPlacement, FootprintID, Orientation
from app.services.breadboard import Breadboard, UnknownHoleError

DEFAULT_FOOTPRINTS: dict[str, FootprintID] = {
    "resistor": "resistor-axial-7_62",
    "led": "led-2_54",
    "push_button": "button-trench-7_62x5_08",
    "jumper": "jumper-flex",
    "supply_terminal": "supply-terminal-flex",
}


def component_clearance(placement: ComponentPlacement) -> set[str]:
    """Reference body envelope between leads; not a measured part specification."""
    pins = list(placement.pins.values())
    if placement.footprint_id in {"jumper-flex", "supply-terminal-flex"}:
        return set(pins)
    columns = {pin[0] for pin in pins}
    rows = [int(pin[1:]) for pin in pins]
    return {f"{column}{row}" for column in columns for row in range(min(rows), max(rows) + 1)}


def expected_pins(placement: ComponentPlacement) -> dict[str, str] | None:
    """Return exact rigid footprint mapping, or None for a flexible two-lead link.

    Button anchor is the upper E hole, independent of orientation. Pin pairs 1/2
    and 3/4 are internally connected; switching connects these pairs when pressed.
    This explicit reference convention is not a claim about all push buttons.
    """
    if placement.footprint_id in {"jumper-flex", "supply-terminal-flex"}:
        return None
    column = placement.anchor[0]
    if column not in "ABCDEFGHIJ" or not placement.anchor[1:].isdigit():
        raise ValueError("Rigid footprints require a terminal-strip anchor")
    row = int(placement.anchor[1:])
    if placement.footprint_id == "button-trench-7_62x5_08":
        if column != "E":
            raise ValueError("Button reference anchor must be in column E")
        if placement.orientation == 0:
            return {"1": f"E{row}", "2": f"E{row + 2}", "3": f"F{row}", "4": f"F{row + 2}"}
        return {"1": f"F{row + 2}", "2": f"F{row}", "3": f"E{row + 2}", "4": f"E{row}"}
    distance = 3 if placement.footprint_id == "resistor-axial-7_62" else 1
    delta = distance if placement.orientation == 0 else -distance
    names = ("anode", "cathode") if placement.footprint_id == "led-2_54" else ("1", "2")
    return {names[0]: placement.anchor, names[1]: f"{column}{row + delta}"}


def valid_footprint_placements(
    component: Component, board: Breadboard
) -> Iterator[ComponentPlacement]:
    footprint = DEFAULT_FOOTPRINTS[component.type]
    if footprint in {"jumper-flex", "supply-terminal-flex"}:
        # Deterministic baseline: enumerate near-terminal flexible candidates.
        for row in range(1, board.model.terminal_rows):
            yield ComponentPlacement(
                component_id=component.id,
                footprint_id=footprint,
                anchor=f"A{row}",
                pins={component.pins[0]: f"A{row}", component.pins[1]: f"A{row + 1}"},
            )
        return
    columns = "E" if component.type == "push_button" else "ABCDEFGHIJ"
    for row in range(1, board.model.terminal_rows + 1):
        for column in columns:
            for orientation in (0, 180):
                typed_orientation: Orientation = 0 if orientation == 0 else 180
                placement = ComponentPlacement(
                    component_id=component.id,
                    footprint_id=footprint,
                    anchor=f"{column}{row}",
                    orientation=typed_orientation,
                    pins={},
                )
                pins = expected_pins(placement)
                assert pins is not None
                try:
                    for hole in pins.values():
                        board.get_hole(hole)
                except UnknownHoleError:
                    continue
                yield placement.model_copy(update={"pins": pins})
