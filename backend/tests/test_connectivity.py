from copy import deepcopy

import pytest
from app.schemas.circuit import Circuit
from app.schemas.layout import ComponentPlacement, JumperPlacement, Layout, SupplyPlacement
from app.services.breadboard import Breadboard, reference_board
from app.services.connectivity import circuit_digest, validate_layout
from app.services.footprints import valid_footprint_placements
from app.services.union_find import UnionFind


@pytest.fixture
def physical_case(series_led):
    circuit = Circuit.model_validate(series_led)
    board = Breadboard(reference_board())
    layout = Layout(
        circuit_sha256=circuit_digest(circuit),
        board_model_id=board.model.model_id,
        board_revision=board.model.revision,
        components=[
            ComponentPlacement(
                component_id="R1",
                footprint_id="resistor-axial-7_62",
                anchor="A1",
                pins={"1": "A1", "2": "A4"},
            ),
            ComponentPlacement(
                component_id="D1",
                footprint_id="led-2_54",
                anchor="B8",
                pins={"anode": "B8", "cathode": "B9"},
            ),
        ],
        jumpers=[JumperPlacement(id="W1", net_id="N1", start="C4", end="C8")],
        supply=SupplyPlacement(positive_hole="C1", negative_hole="C9"),
    )
    return circuit, layout, board


def codes(result):
    return {error.code for error in result.errors}


def test_known_correct_layout_and_functional_terminals_stay_distinct(physical_case):
    circuit, layout, board = physical_case
    report = validate_layout(circuit, layout, board)
    assert report.valid, report.errors
    assert not report.ready_to_build
    assert not report.electrically_verified
    assert report.terminal_groups["R1.1"] != report.terminal_groups["R1.2"]
    assert report.terminal_groups["D1.anode"] != report.terminal_groups["D1.cathode"]
    assert report.terminal_groups["R1.2"] == report.terminal_groups["D1.anode"]


def test_missing_jumper_fails(physical_case):
    circuit, layout, board = physical_case
    layout.jumpers.clear()
    assert "disconnected_net" in codes(validate_layout(circuit, layout, board))


def test_distinct_net_short_fails(physical_case):
    circuit, layout, board = physical_case
    layout.jumpers.append(JumperPlacement(id="BAD", net_id="VCC", start="D1", end="D9"))
    report = validate_layout(circuit, layout, board)
    assert {"shorted_nets", "jumper_net_mismatch"} <= codes(report)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda p: p.update(circuit_sha256="0" * 64), "circuit_version_mismatch"),
        (lambda p: p.update(board_revision="r2"), "board_version_mismatch"),
        (lambda p: p["components"].pop(), "missing_component"),
        (lambda p: p["components"].append(deepcopy(p["components"][0])), "duplicate_placement"),
        (lambda p: p["components"][0].update(component_id="UNKNOWN"), "unknown_component"),
        (lambda p: p["components"][0].update(footprint_id="led-2_54"), "unsupported_footprint"),
        (lambda p: p["components"][0]["pins"].update(extra="Z1"), "placement_pin_mismatch"),
        (lambda p: p["components"][1].update(orientation=180), "footprint_geometry"),
        (lambda p: p["components"][0].update(anchor="L_POS_1"), "footprint_geometry"),
        (lambda p: p["components"][1]["pins"].update(anode="A4"), "hole_occupied"),
        (lambda p: p["jumpers"][0].update(end="A64"), "unknown_hole"),
        (lambda p: p["jumpers"].append(deepcopy(p["jumpers"][0])), "duplicate_jumper"),
        (lambda p: p["jumpers"][0].update(net_id="MISSING"), "unknown_jumper_net"),
        (lambda p: p.update(supply=None), "missing_supply_placement"),
        (lambda p: p["supply"].update(positive_hole="L_NEG_1"), "rail_polarity"),
    ],
)
def test_invalid_layout_regressions(physical_case, change, expected):
    circuit, layout, board = physical_case
    data = layout.model_dump(mode="json")
    change(data)
    report = validate_layout(circuit, Layout.model_validate(data), board)
    assert not report.valid
    assert expected in codes(report)


def test_center_trench_is_not_a_connection(physical_case):
    circuit, layout, board = physical_case
    layout.jumpers[0].end = "F8"
    assert "disconnected_net" in codes(validate_layout(circuit, layout, board))


def test_rails_are_not_implicitly_bridged(physical_case):
    circuit, layout, board = physical_case
    layout.supply.positive_hole = "L_POS_26"
    layout.jumpers.append(JumperPlacement(id="W2", net_id="VCC", start="D1", end="L_POS_1"))
    assert "disconnected_net" in codes(validate_layout(circuit, layout, board))
    layout.jumpers.append(JumperPlacement(id="W3", net_id="VCC", start="L_POS_2", end="L_POS_27"))
    assert validate_layout(circuit, layout, board).valid


def test_union_invariant_under_order_and_direction():
    edges = [("A", "B"), ("C", "D"), ("B", "D"), ("Q", "R")]
    first, second = UnionFind(), UnionFind()
    for a, b in edges:
        first.union(a, b)
    for b, a in reversed(edges):
        second.union(a, b)
    assert {key: first.find(key) for key in "ABCDQRZ"} == {
        key: second.find(key) for key in "ABCDQRZ"
    }
    assert first.find("A") != first.find("Q")
    assert first.find("Z") == "Z"


def test_footprints_do_not_escape_board(physical_case):
    circuit, _, board = physical_case
    for component in circuit.components:
        placements = list(valid_footprint_placements(component, board))
        assert placements
        for placement in placements:
            assert len(set(placement.pins.values())) == len(component.pins)
            for hole in placement.pins.values():
                board.get_hole(hole)
