"""Narrow topology rules, distinct from simulation and physical safety validation."""

import heapq
import math
from collections import defaultdict

from app.schemas.circuit import Circuit
from app.schemas.validation import ValidationIssue


def basic_electrical_errors(circuit: Circuit) -> list[ValidationIssue]:
    if circuit.supply is None:
        return []
    assignment = {member: net.id for net in circuit.nets for member in net.members}
    edges: dict[str, list[tuple[str, float]]] = defaultdict(list)
    errors: list[ValidationIssue] = []
    for component in circuit.components:
        if component.type not in {"resistor", "jumper", "push_button"}:
            continue
        first, second = ("1", "3") if component.type == "push_button" else ("1", "2")
        a, b = assignment.get(f"{component.id}.{first}"), assignment.get(f"{component.id}.{second}")
        if a is None or b is None:
            continue
        edge_resistance = component.value_ohms if component.type == "resistor" else 0.0
        edges[a].append((b, edge_resistance))
        edges[b].append((a, edge_resistance))

    def resistance(start: str, target: str, blocked: str | None = None) -> float:
        # A branch path must not pass through the opposite supply terminal and
        # re-enter through an unrelated branch; that would hide reversed LEDs.
        if start == blocked or target == blocked:
            return math.inf
        pending = [(0.0, start)]
        visited: set[str] = set()
        while pending:
            distance, net = heapq.heappop(pending)
            if net == target:
                return distance
            if net in visited:
                continue
            visited.add(net)
            for other, value in edges[net]:
                if other not in visited and other != blocked:
                    heapq.heappush(pending, (distance + value, other))
        return math.inf

    positive, negative = circuit.supply.positive_net, circuit.supply.negative_net
    if resistance(positive, negative) == 0:
        errors.append(
            ValidationIssue(
                code="ideal_supply_short",
                message=(
                    "An ideal-conductor path can short the supply (including a pressed button)."
                ),
            )
        )
    for component in circuit.components:
        if component.type != "led":
            continue
        anode = assignment.get(f"{component.id}.anode")
        cathode = assignment.get(f"{component.id}.cathode")
        if anode is None or cathode is None:
            continue
        forward = resistance(positive, anode, negative) + resistance(cathode, negative, positive)
        backward = resistance(positive, cathode, negative) + resistance(anode, negative, positive)
        if forward == 0:
            errors.append(
                ValidationIssue(
                    code="missing_current_limiting",
                    message=f"{component.id} has a supply path with no series resistance.",
                )
            )
        elif not math.isfinite(forward) and math.isfinite(backward):
            errors.append(
                ValidationIssue(
                    code="reversed_led",
                    message=(
                        f"{component.id} is reversed relative to the supply "
                        "in the supported series topology."
                    ),
                )
            )
        elif not math.isfinite(forward):
            errors.append(
                ValidationIssue(
                    code="unsupported_led_topology",
                    message=(
                        f"{component.id}: no supported supply-to-LED series path was found. "
                        "Multi-LED series chains and complex active networks "
                        "require a richer electrical model."
                    ),
                )
            )
    return errors
