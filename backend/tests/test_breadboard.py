import json
from pathlib import Path

import pytest
from app.schemas.board import BoardModel
from app.services.breadboard import Breadboard, UnknownHoleError, reference_board
from pydantic import ValidationError


@pytest.fixture
def board():
    return Breadboard(reference_board())


def test_all_terminal_rows_and_center_gap(board):
    for row in range(1, 64):
        assert {hole.id for hole in board.holes_in_group(board.group_for_hole(f"A{row}"))} == {
            f"{column}{row}" for column in "ABCDE"
        }
        assert {hole.id for hole in board.holes_in_group(board.group_for_hole(f"F{row}"))} == {
            f"{column}{row}" for column in "FGHIJ"
        }
        assert not board.are_directly_connected(f"E{row}", f"F{row}")
        if row < 63:
            assert not board.are_directly_connected(f"A{row}", f"A{row + 1}")
    assert board.are_directly_connected("A3", "E3")


def test_explicit_rails_are_split_and_isolated(board):
    for name in ["L_POS", "L_NEG", "R_POS", "R_NEG"]:
        assert board.are_directly_connected(f"{name}_1", f"{name}_25")
        assert board.are_directly_connected(f"{name}_26", f"{name}_50")
        assert not board.are_directly_connected(f"{name}_25", f"{name}_26")
        assert not board.are_directly_connected(f"{name}_1", "A1")
    assert not board.are_directly_connected("L_POS_1", "L_NEG_1")
    assert not board.are_directly_connected("L_POS_1", "R_POS_1")


@pytest.mark.parametrize("hole", ["A0", "A64", "K1", "a3", "A03", "POWER_POS_1", "L_POS_51"])
def test_unknown_holes_raise(board, hole):
    with pytest.raises(UnknownHoleError, match="Unknown hole"):
        board.get_hole(hole)
    with pytest.raises(UnknownHoleError):
        board.are_directly_connected("A1", hole)


def test_unknown_group(board):
    with pytest.raises(ValueError, match="Unknown conductive group"):
        board.holes_in_group("MISSING")


def test_counts_geometry_and_reference_status(board):
    model = board.model
    assert len(model.holes) == 830
    assert len({hole.conductive_group_id for hole in model.holes}) == 126 + 8
    assert len(model.rail_segments) == 8
    assert model.verification_status == "reference_unverified"
    assert model.supported_footprints == []
    assert board.get_hole("E3").position.x < board.get_hole("F3").position.x
    assert board.get_hole("A2").position.y - board.get_hole("A1").position.y == 2.54


def test_callers_cannot_mutate_topology(board):
    board.model.holes.clear()
    hole = board.get_hole("A3")
    hole.conductive_group_id = "BAD"
    board.holes_in_group(board.group_for_hole("A3"))[0].id = "BAD"
    assert board.are_directly_connected("A3", "E3")
    assert len(board.model.holes) == 830


@pytest.mark.parametrize(
    "mutation",
    [
        lambda m: m["holes"].append(m["holes"][0]),
        lambda m: m.update(verification_status="physically_verified"),
        lambda m: m["rail_segments"].append(m["rail_segments"][0]),
        lambda m: m["rail_segments"][0]["hole_ids"].append("MISSING"),
        lambda m: m["rail_segments"][0]["hole_ids"].append("L_POS_1"),
        lambda m: m["rail_segments"][0]["hole_ids"].append("L_POS_26"),
        lambda m: m["rail_segments"][0]["hole_ids"].append("A1"),
        lambda m: m["rail_segments"][0]["hole_ids"].pop(),
        lambda m: m["keep_out_regions"][0].update(maximum={"x": -999.0, "y": -999.0}),
    ],
)
def test_inconsistent_board_models_rejected(mutation):
    model = reference_board().model_dump(mode="json")
    mutation(model)
    with pytest.raises(ValidationError):
        BoardModel.model_validate(model)


def test_board_without_rails_does_not_guess_connections():
    data = reference_board().model_dump(mode="json")
    data["rail_segments"] = []
    data["holes"] = [
        hole for hole in data["holes"] if hole["conductive_group_id"].startswith("STRIP_")
    ]
    board = Breadboard(BoardModel.model_validate(data))
    assert len(board.model.holes) == 630
    with pytest.raises(UnknownHoleError):
        board.get_hole("L_POS_1")


def test_serialized_fixture_matches_generator():
    fixture = Path(__file__).parents[2] / "shared/boards/bb830-reference-r1.json"
    loaded = BoardModel.model_validate_json(fixture.read_text())
    assert loaded == reference_board()
    assert json.loads(loaded.model_dump_json())["terminal_rows"] == 63
