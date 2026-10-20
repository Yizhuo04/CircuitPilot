"""Structural netlist integrity. No analog or physical safety claims."""

from collections import Counter

from app.schemas.circuit import Circuit
from app.schemas.validation import ValidationIssue, ValidationResult


def validate_circuit(circuit: Circuit) -> ValidationResult:
    errors: list[ValidationIssue] = []

    def error(code: str, message: str, *path: str | int) -> None:
        errors.append(ValidationIssue(code=code, message=message, path=list(path)))

    for field, ids in [
        ("components", [component.id for component in circuit.components]),
        ("nets", [net.id for net in circuit.nets]),
    ]:
        for identifier, count in Counter(ids).items():
            if count > 1:
                error("duplicate_id", f"Duplicate {field} ID {identifier!r}.", field)

    declared = {
        f"{component.id}.{pin}" for component in circuit.components for pin in component.pins
    }
    assignment: dict[str, str] = {}
    for index, net in enumerate(circuit.nets):
        seen: set[str] = set()
        for member_index, member in enumerate(net.members):
            path = ("nets", index, "members", member_index)
            if member not in declared:
                error("unknown_pin", f"Pin {member!r} is not declared.", *path)
            if member in seen:
                error("duplicate_member", f"Pin {member!r} repeats within {net.id!r}.", *path)
            seen.add(member)
            if member in assignment and assignment[member] != net.id:
                error(
                    "pin_in_multiple_nets",
                    f"Pin {member!r} belongs to both {assignment[member]!r} and {net.id!r}.",
                    *path,
                )
            assignment[member] = net.id

    for member in sorted(declared - assignment.keys()):
        error("unassigned_pin", f"Pin {member!r} has no net assignment.", "components")

    for component in circuit.components:
        if component.type == "jumper":
            first = assignment.get(f"{component.id}.1")
            second = assignment.get(f"{component.id}.2")
            if first is not None and second is not None and first != second:
                error(
                    "jumper_net_conflict",
                    f"Ideal conductor {component.id!r} cannot join distinct logical nets.",
                    "components",
                )

    nets = {net.id: net for net in circuit.nets}
    if circuit.supply is None:
        if any(net.role in {"power", "ground"} for net in circuit.nets) or any(
            component.type == "supply_terminal" for component in circuit.components
        ):
            error("missing_supply", "Power/ground nets require explicit supply mapping.", "supply")
    else:
        supply = circuit.supply
        if supply.positive_net == supply.negative_net:
            error("supply_short", "Supply terminals must reference distinct nets.", "supply")
        for field, net_id, role in [
            ("positive_net", supply.positive_net, "power"),
            ("negative_net", supply.negative_net, "ground"),
        ]:
            if net_id not in nets:
                error(
                    "unknown_supply_net", f"Supply net {net_id!r} does not exist.", "supply", field
                )
            elif nets[net_id].role != role:
                error(
                    "supply_role",
                    f"Supply net {net_id!r} must have role {role!r}.",
                    "supply",
                    field,
                )
        for net in circuit.nets:
            if net.role in {"power", "ground"} and net.id not in {
                supply.positive_net,
                supply.negative_net,
            }:
                error("unmapped_supply_net", f"Supply net {net.id!r} is unmapped.", "nets")
        for component in circuit.components:
            if component.type == "supply_terminal":
                for pin, expected in [
                    ("positive", supply.positive_net),
                    ("negative", supply.negative_net),
                ]:
                    if assignment.get(f"{component.id}.{pin}") != expected:
                        error(
                            "supply_polarity",
                            f"{component.id}.{pin} must be on {expected!r}.",
                            "components",
                        )

    warnings = [
        ValidationIssue(
            code="structure_only",
            message="Structural checks do not verify physical wiring, device polarity, "
            "LED current limiting, or electrical safety. "
            "This endpoint does not validate a physical assembly plan.",
        ),
        ValidationIssue(
            code="disconnect_power",
            message="Disconnect power before wiring. Use a low-voltage, current-limited supply.",
        ),
    ]
    if any(component.type == "led" for component in circuit.components):
        warnings.append(
            ValidationIssue(
                code="led_analysis_pending",
                message="LED polarity and a suitable series current-limiting resistor "
                "still require electrical analysis; resistor presence alone is insufficient.",
            )
        )
    return ValidationResult(valid=not errors, errors=errors, warnings=warnings)
