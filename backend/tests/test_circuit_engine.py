from copy import deepcopy
from pathlib import Path

import pytest
from app.schemas.circuit import Circuit
from app.services.circuit_engine import validate_circuit
from pydantic import ValidationError

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("name", ["series_led", "led_button"])
def test_valid_reference_circuits(name):
    circuit = Circuit.model_validate_json((FIXTURES / f"{name}.json").read_text())
    result = validate_circuit(circuit)
    assert result.valid
    assert not result.ready_to_build
    assert result.validation_scope == "netlist_structure"
    assert {warning.code for warning in result.warnings} == {
        "structure_only",
        "disconnect_power",
        "led_analysis_pending",
    }


def test_invalid_fixture_reports_unknown_and_conflicting_pins():
    circuit = Circuit.model_validate_json((FIXTURES / "invalid_netlist.json").read_text())
    result = validate_circuit(circuit)
    assert not result.valid
    assert {issue.code for issue in result.errors} >= {"unknown_pin", "pin_in_multiple_nets"}


@pytest.mark.parametrize("field", ["components", "nets"])
def test_duplicate_ids(series_led, field):
    series_led[field].append(deepcopy(series_led[field][0]))
    result = validate_circuit(Circuit.model_validate(series_led))
    assert "duplicate_id" in {issue.code for issue in result.errors}


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda c: c["nets"][0]["members"].append("R1.1"), "duplicate_member"),
        (lambda c: c["nets"][1]["members"].append("R1.1"), "pin_in_multiple_nets"),
        (lambda c: c["nets"][1]["members"].append("R1.99"), "unknown_pin"),
        (lambda c: c["nets"][1]["members"].remove("R1.2"), "unassigned_pin"),
        (lambda c: c.pop("supply"), "missing_supply"),
        (lambda c: c["supply"].update(positive_net="MISSING"), "unknown_supply_net"),
        (lambda c: c["supply"].update(negative_net="VCC"), "supply_short"),
        (lambda c: c["nets"][0].update(role="signal"), "supply_role"),
        (lambda c: c["nets"][1].update(role="power"), "unmapped_supply_net"),
    ],
)
def test_integrity_errors(series_led, mutation, expected):
    mutation(series_led)
    result = validate_circuit(Circuit.model_validate(series_led))
    assert not result.valid
    assert expected in {issue.code for issue in result.errors}
    assert all(issue.path for issue in result.errors)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c: c.update(schema_version="2.0"),
        lambda c: c.update(name="   "),
        lambda c: c.update(units="imperial"),
        lambda c: c.update(unrecognized_field=True),
        lambda c: c["components"][0].update(type="transistor"),
        lambda c: c["components"][0].update(value_ohms=0),
        lambda c: c["components"][0].update(value_ohms=-1),
        lambda c: c["components"][0].update(value_ohms=float("nan")),
        lambda c: c["components"][0].update(value_ohms=float("inf")),
        lambda c: c["components"][0].update(value_ohms="220"),
        lambda c: c["components"][0].update(value_ohms=True),
        lambda c: c["components"][0].pop("value_ohms"),
        lambda c: c["components"][0].update(pins=["1", "1"]),
        lambda c: c["components"][0].update(footprint_ref="unverified"),
        lambda c: c["components"][1].update(pins=["positive", "negative"]),
        lambda c: c["components"][1].update(orientation=180),
        lambda c: c["nets"][0].update(members=[]),
        lambda c: c["nets"][0].update(members=["R1.1.extra"]),
        lambda c: c["supply"].update(voltage_v=13),
        lambda c: c["supply"].update(current_limit_ma=501),
        lambda c: c["supply"].update(current_limit_ma=0),
    ],
)
def test_unsupported_or_malformed_values_rejected(series_led, mutation):
    mutation(series_led)
    with pytest.raises(ValidationError):
        Circuit.model_validate(series_led)


def test_passive_circuit_without_supply():
    circuit = Circuit.model_validate(
        {
            "schema_version": "1.0",
            "name": "Passive resistor",
            "components": [
                {"id": "R1", "type": "resistor", "value_ohms": 1000, "pins": ["1", "2"]}
            ],
            "nets": [{"id": "A", "members": ["R1.1"]}, {"id": "B", "members": ["R1.2"]}],
        }
    )
    result = validate_circuit(circuit)
    assert result.valid
    assert "led_analysis_pending" not in {warning.code for warning in result.warnings}


def test_explicit_supply_terminal_polarity(series_led):
    series_led["components"].append(
        {"id": "P1", "type": "supply_terminal", "pins": ["positive", "negative"]}
    )
    series_led["nets"][0]["members"].append("P1.positive")
    series_led["nets"][2]["members"].append("P1.negative")
    assert validate_circuit(Circuit.model_validate(series_led)).valid
    series_led["nets"][0]["members"][-1] = "P1.negative"
    series_led["nets"][2]["members"][-1] = "P1.positive"
    result = validate_circuit(Circuit.model_validate(series_led))
    assert "supply_polarity" in {issue.code for issue in result.errors}


def test_validation_does_not_mutate_input(series_led):
    circuit = Circuit.model_validate(series_led)
    before = circuit.model_dump_json()
    first = validate_circuit(circuit)
    assert validate_circuit(circuit) == first
    assert circuit.model_dump_json() == before


def test_jumper_cannot_short_distinct_nets(series_led):
    series_led["components"].append({"id": "W1", "type": "jumper", "pins": ["1", "2"]})
    series_led["nets"][0]["members"].append("W1.1")
    series_led["nets"][2]["members"].append("W1.2")
    result = validate_circuit(Circuit.model_validate(series_led))
    assert "jumper_net_conflict" in {issue.code for issue in result.errors}
    series_led["nets"][2]["members"].remove("W1.2")
    series_led["nets"][0]["members"].append("W1.2")
    assert validate_circuit(Circuit.model_validate(series_led)).valid


def test_supply_terminal_requires_supply_even_without_power_roles(series_led):
    series_led.pop("supply")
    for net in series_led["nets"]:
        net["role"] = "signal"
    series_led["components"].append(
        {"id": "P1", "type": "supply_terminal", "pins": ["positive", "negative"]}
    )
    series_led["nets"][0]["members"].append("P1.positive")
    series_led["nets"][2]["members"].append("P1.negative")
    result = validate_circuit(Circuit.model_validate(series_led))
    assert "missing_supply" in {issue.code for issue in result.errors}
