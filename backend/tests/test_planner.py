from importlib.resources import files

import pytest
from app.schemas.circuit import Circuit
from app.services.breadboard import Breadboard, reference_board
from app.services.connectivity import validate_layout
from app.services.electrical import basic_electrical_errors
from app.services.placement_engine import PlanningError, generate_plan


@pytest.mark.parametrize("name", ["series_led", "led_button", "parallel_leds"])
@pytest.mark.parametrize("seed", [0, 1, 11])
def test_reference_circuits_generate_valid_deterministic_plans(name, seed):
    circuit = Circuit.model_validate_json(
        files("app").joinpath(f"data/circuits/{name}.json").read_text()
    )
    board = Breadboard(reference_board())
    before = circuit.model_dump_json()
    plan = generate_plan(circuit, board, seed)
    assert plan == generate_plan(circuit, board, seed)
    assert validate_layout(circuit, plan.layout, board).valid
    assert plan.validation.valid and not plan.validation.ready_to_build
    assert plan.reference_only
    assert len(plan.layout.jumpers) <= 10
    assert plan.steps[0].kind == "safety"
    assert plan.steps[-1].kind == "review"
    assert [s.sequence for s in plan.steps] == list(range(1, len(plan.steps) + 1))
    assert circuit.model_dump_json() == before
    for step in plan.steps:
        for hole in step.holes:
            board.get_hole(hole)


def test_reversed_led_rejected(series_led):
    series_led["nets"][1]["members"][1] = "D1.cathode"
    series_led["nets"][2]["members"][0] = "D1.anode"
    circuit = Circuit.model_validate(series_led)
    assert "reversed_led" in {e.code for e in basic_electrical_errors(circuit)}
    with pytest.raises(PlanningError, match="reversed"):
        generate_plan(circuit, Breadboard(reference_board()))


def test_resistor_elsewhere_does_not_prove_current_limiting(series_led):
    # LED directly across supply, resistor connected elsewhere: presence is insufficient.
    series_led["nets"][0]["members"].append("D1.anode")
    series_led["nets"][1]["members"].remove("D1.anode")
    with pytest.raises(PlanningError) as failure:
        generate_plan(Circuit.model_validate(series_led), Breadboard(reference_board()))
    assert failure.value.code == "missing_current_limiting"


def test_pressed_button_cannot_short_supply(series_led):
    series_led["components"].append(
        {"id": "SW1", "type": "push_button", "pins": ["1", "2", "3", "4"]}
    )
    series_led["nets"][0]["members"].extend(["SW1.1", "SW1.2"])
    series_led["nets"][2]["members"].extend(["SW1.3", "SW1.4"])
    with pytest.raises(PlanningError) as failure:
        generate_plan(Circuit.model_validate(series_led), Breadboard(reference_board()))
    assert failure.value.code == "ideal_supply_short"


def test_invalid_circuit_cannot_enter_planner(series_led):
    series_led["nets"][0]["members"].append("UNKNOWN.1")
    with pytest.raises(PlanningError) as failure:
        generate_plan(Circuit.model_validate(series_led), Breadboard(reference_board()))
    assert failure.value.code == "invalid_circuit"


def test_planner_reports_bounded_search_failure(series_led, monkeypatch):
    monkeypatch.setattr(
        "app.services.placement_engine.valid_footprint_placements", lambda *args: iter(())
    )
    with pytest.raises(PlanningError) as failure:
        generate_plan(Circuit.model_validate(series_led), Breadboard(reference_board()))
    assert failure.value.code == "search_exhausted"


def test_generated_layout_is_rejected_when_independent_gate_fails(series_led, monkeypatch):
    from app.schemas.layout import LayoutValidationResult
    from app.schemas.validation import ValidationIssue

    monkeypatch.setattr(
        "app.services.placement_engine.validate_layout",
        lambda *args: LayoutValidationResult(
            valid=False,
            errors=[ValidationIssue(code="deliberate_gate_failure", message="Test gate rejected.")],
        ),
    )
    with pytest.raises(PlanningError, match="Test gate rejected"):
        generate_plan(Circuit.model_validate(series_led), Breadboard(reference_board()))
