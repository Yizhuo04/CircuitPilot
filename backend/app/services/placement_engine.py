"""Bounded deterministic greedy placement/routing with an independent release gate."""

import math
import random
from collections import defaultdict

from app.schemas.circuit import Circuit
from app.schemas.layout import (
    AssemblyPlan,
    AssemblyStep,
    ComponentPlacement,
    JumperPlacement,
    Layout,
    SupplyPlacement,
)
from app.services.breadboard import Breadboard
from app.services.circuit_engine import validate_circuit
from app.services.connectivity import circuit_digest, validate_layout
from app.services.electrical import basic_electrical_errors
from app.services.footprints import component_clearance, valid_footprint_placements
from app.services.union_find import UnionFind

PLANNER_VERSION = "greedy-1.0"


class PlanningError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def generate_plan(circuit: Circuit, board: Breadboard, seed: int = 0) -> AssemblyPlan:
    structure = validate_circuit(circuit)
    if not structure.valid:
        raise PlanningError(
            "invalid_circuit", "; ".join(issue.message for issue in structure.errors)
        )
    if len(circuit.components) > 8:
        raise PlanningError(
            "unsupported_size", "The baseline planner supports at most eight components."
        )
    electrical_errors = basic_electrical_errors(circuit)
    if electrical_errors:
        raise PlanningError(electrical_errors[0].code, electrical_errors[0].message)
    # Button contact pairs are ideal conductors even in the unpressed state.
    assignment = {member: net.id for net in circuit.nets for member in net.members}
    for component in circuit.components:
        if component.type == "push_button":
            for first, second in [("1", "2"), ("3", "4")]:
                if assignment[f"{component.id}.{first}"] != assignment[f"{component.id}.{second}"]:
                    raise PlanningError(
                        "button_contact_conflict",
                        "Reference button contact pairs must share a logical net.",
                    )
    last_failure = "No candidate survived the graph validator."
    for attempt in range(12):
        try:
            layout = _attempt(circuit, board, seed + attempt, seed)
        except PlanningError as exc:
            last_failure = str(exc)
            continue
        report = validate_layout(circuit, layout, board)
        if report.valid:
            return AssemblyPlan(layout=layout, validation=report, steps=assembly_steps(layout))
        last_failure = "; ".join(issue.message for issue in report.errors)
    raise PlanningError(
        "search_exhausted", f"Bounded planner did not find a valid layout: {last_failure}"
    )


def _attempt(circuit: Circuit, board: Breadboard, attempt_seed: int, seed: int) -> Layout:
    rng = random.Random(attempt_seed)
    intended = {member: net.id for net in circuit.nets for member in net.members}
    used: set[str] = set()
    blocked: set[str] = set()
    group_net: dict[str, str] = {}
    net_holes: dict[str, list[str]] = defaultdict(list)
    supply: SupplyPlacement | None = None
    if circuit.supply is not None:
        supply = SupplyPlacement(positive_hole="L_POS_1", negative_hole="L_NEG_1")
        for hole, net in [
            (supply.positive_hole, circuit.supply.positive_net),
            (supply.negative_hole, circuit.supply.negative_net),
        ]:
            used.add(hole)
            group_net[board.group_for_hole(hole)] = net
            net_holes[net].append(hole)
    order = {"push_button": 0, "supply_terminal": 1, "led": 2, "resistor": 3, "jumper": 4}
    placements: list[ComponentPlacement] = []
    for component in sorted(circuit.components, key=lambda c: (order[c.type], c.id)):
        candidates = list(valid_footprint_placements(component, board))
        rng.shuffle(candidates)
        best: ComponentPlacement | None = None
        best_score = math.inf
        for candidate in candidates:
            clearance = component_clearance(candidate)
            if clearance & (used | blocked):
                continue
            candidate_groups: dict[str, str] = {}
            score = 0.0
            conflict = False
            for pin, hole in candidate.pins.items():
                net = intended[f"{component.id}.{pin}"]
                group = board.group_for_hole(hole)
                if group in group_net and group_net[group] != net:
                    conflict = True
                    break
                if group in candidate_groups and candidate_groups[group] != net:
                    conflict = True
                    break
                candidate_groups[group] = net
                score -= 100 if group_net.get(group) == net else 0
                position = board.get_hole(hole).position
                if net_holes.get(net):
                    score += min(_distance(board, hole, other) for other in net_holes[net])
                else:
                    score += position.y * 0.3 + abs(position.x) * 0.1
            if not conflict and score < best_score:
                best, best_score = candidate, score
        if best is None:
            raise PlanningError(
                "placement_exhausted", f"No collision-free candidate for {component.id}."
            )
        placements.append(best)
        blocked.update(component_clearance(best) - set(best.pins.values()))
        for pin, hole in best.pins.items():
            used.add(hole)
            net = intended[f"{component.id}.{pin}"]
            group_net[board.group_for_hole(hole)] = net
            net_holes[net].append(hole)

    graph = UnionFind()
    for placement in placements:
        component = next(c for c in circuit.components if c.id == placement.component_id)
        pairs = (
            [("1", "2")]
            if component.type == "jumper"
            else ([("1", "2"), ("3", "4")] if component.type == "push_button" else [])
        )
        for first, second in pairs:
            graph.union(
                board.group_for_hole(placement.pins[first]),
                board.group_for_hole(placement.pins[second]),
            )
    group_holes: dict[str, list[str]] = defaultdict(list)
    for board_hole in board.model.holes:
        group_holes[board_hole.conductive_group_id].append(board_hole.id)
    jumpers: list[JumperPlacement] = []
    for logical_net in circuit.nets:
        while True:
            roots = {graph.find(board.group_for_hole(hole)) for hole in net_holes[logical_net.id]}
            if len(roots) <= 1:
                break
            free: dict[str, list[str]] = defaultdict(list)
            for group, holes in group_holes.items():
                root = graph.find(group)
                if root in roots:
                    free[root].extend(h for h in holes if h not in used and h not in blocked)
            options: list[tuple[float, str, str]] = []
            root_list = sorted(roots)
            for index, first in enumerate(root_list):
                for second in root_list[index + 1 :]:
                    for start in free[first]:
                        for end in free[second]:
                            options.append((_distance(board, start, end), start, end))
            if not options:
                raise PlanningError(
                    "routing_exhausted", f"No free routing holes for net {logical_net.id}."
                )
            length, start, end = min(options)
            used.update([start, end])
            graph.union(board.group_for_hole(start), board.group_for_hole(end))
            jumpers.append(
                JumperPlacement(
                    id=f"W{len(jumpers) + 1}",
                    net_id=logical_net.id,
                    start=start,
                    end=end,
                    length_mm=round(length + 10, 2),
                    color="red"
                    if logical_net.role == "power"
                    else "black"
                    if logical_net.role == "ground"
                    else "blue",
                )
            )
            if len(jumpers) > 10:
                raise PlanningError("routing_exhausted", "Layout exceeds the ten-jumper MVP limit.")
    return Layout(
        circuit_sha256=circuit_digest(circuit),
        board_model_id=board.model.model_id,
        board_revision=board.model.revision,
        planner_version=PLANNER_VERSION,
        seed=seed,
        components=placements,
        jumpers=jumpers,
        supply=supply,
    )


def _distance(board: Breadboard, first: str, second: str) -> float:
    a, b = board.get_hole(first).position, board.get_hole(second).position
    return math.hypot(a.x - b.x, a.y - b.y)


def assembly_steps(layout: Layout) -> list[AssemblyStep]:
    steps = [
        AssemblyStep(
            sequence=1,
            kind="safety",
            title="Disconnect all power",
            instruction=(
                "This is a reference layout. Confirm the board and part "
                "dimensions before physical assembly. Keep the supply "
                "disconnected."
            ),
        )
    ]
    for component in layout.components:
        mapping = ", ".join(f"{pin} → {hole}" for pin, hole in component.pins.items())
        steps.append(
            AssemblyStep(
                sequence=len(steps) + 1,
                kind="component",
                title=f"Place {component.component_id}",
                component_id=component.component_id,
                instruction=f"Reference pin mapping: {mapping}. Match named pins and orientation.",
                holes=list(component.pins.values()),
            )
        )
    for wire in layout.jumpers:
        steps.append(
            AssemblyStep(
                sequence=len(steps) + 1,
                kind="jumper",
                title=f"Add {wire.id} ({wire.net_id})",
                instruction=(
                    f"Connect {wire.start} to {wire.end}; suggested color {wire.color}. "
                    "Keep power disconnected."
                ),
                holes=[wire.start, wire.end],
            )
        )
    if layout.supply is not None:
        steps.append(
            AssemblyStep(
                sequence=len(steps) + 1,
                kind="supply",
                title="Map supply terminals",
                instruction=(
                    f"Positive → {layout.supply.positive_hole}; "
                    f"negative → {layout.supply.negative_hole}. "
                    "Do not energize this unverified reference layout."
                ),
                holes=[layout.supply.positive_hole, layout.supply.negative_hole],
            )
        )
    steps.append(
        AssemblyStep(
            sequence=len(steps) + 1,
            kind="review",
            title="Review before any physical build",
            instruction=(
                "The graph check passed. Physical continuity, polarity, "
                "current limiting, and part ratings still require "
                "independent confirmation. A photograph cannot prove these."
            ),
        )
    )
    return steps
