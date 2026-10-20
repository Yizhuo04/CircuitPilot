"""Compare intended and actual partitions of electrical terminals in both directions."""

import hashlib
import json
from collections import Counter, defaultdict

from app.schemas.circuit import Circuit
from app.schemas.layout import Layout, LayoutValidationResult
from app.schemas.validation import ValidationIssue
from app.services.breadboard import Breadboard, UnknownHoleError
from app.services.circuit_engine import validate_circuit
from app.services.electrical import basic_electrical_errors
from app.services.footprints import DEFAULT_FOOTPRINTS, component_clearance, expected_pins
from app.services.union_find import UnionFind


def circuit_digest(circuit: Circuit) -> str:
    encoded = json.dumps(circuit.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def validate_layout(circuit: Circuit, layout: Layout, board: Breadboard) -> LayoutValidationResult:
    errors = list(validate_circuit(circuit).errors)
    if not errors:
        errors.extend(basic_electrical_errors(circuit))

    def error(code: str, message: str, *path: str | int) -> None:
        errors.append(ValidationIssue(code=code, message=message, path=list(path)))

    if layout.circuit_sha256 != circuit_digest(circuit):
        error("circuit_version_mismatch", "Layout was generated for a different circuit.")
    model = board.model
    if (layout.board_model_id, layout.board_revision) != (model.model_id, model.revision):
        error("board_version_mismatch", "Layout and selected board revision disagree.")
    components = {component.id: component for component in circuit.components}
    counts = Counter(placement.component_id for placement in layout.components)
    for identifier in sorted(components.keys() - counts.keys()):
        error("missing_component", f"Component {identifier!r} has no placement.")
    for identifier, count in counts.items():
        if count > 1:
            error("duplicate_placement", f"Component {identifier!r} is placed more than once.")
    used: dict[str, str] = {}
    terminals: dict[str, str] = {}
    graph = UnionFind()
    for board_hole in model.holes:
        graph.find(board_hole.conductive_group_id)

    def occupy(hole: str, owner: str) -> bool:
        try:
            board.get_hole(hole)
        except UnknownHoleError:
            error("unknown_hole", f"{owner}: hole {hole!r} does not exist.")
            return False
        if hole in used:
            error("hole_occupied", f"{hole} is occupied by both {used[hole]} and {owner}.")
        used[hole] = owner
        return True

    def join(first: str, second: str) -> None:
        graph.union(board.group_for_hole(first), board.group_for_hole(second))

    for placement in layout.components:
        component = components.get(placement.component_id)
        if component is None:
            error("unknown_component", f"Unknown placed component {placement.component_id!r}.")
            continue
        if placement.footprint_id != DEFAULT_FOOTPRINTS[component.type]:
            error("unsupported_footprint", f"Footprint does not match {component.type!r}.")
        if set(placement.pins) != set(component.pins):
            error(
                "placement_pin_mismatch", f"{component.id}: placed pins do not match circuit pins."
            )
        try:
            expected = expected_pins(placement)
            if expected is not None and placement.pins != expected:
                error("footprint_geometry", f"{component.id}: pins violate footprint/orientation.")
            if expected is None and placement.anchor not in placement.pins.values():
                error("footprint_geometry", f"{component.id}: flexible anchor must be a lead hole.")
        except ValueError as exc:
            error("footprint_geometry", str(exc))
        good: dict[str, str] = {}
        for pin, hole in placement.pins.items():
            if occupy(hole, f"{component.id}.{pin}"):
                terminals[f"{component.id}.{pin}"] = hole
                good[pin] = hole
        if component.type == "jumper" and {"1", "2"} <= good.keys():
            join(good["1"], good["2"])
        elif component.type == "push_button":
            for first, second in [("1", "2"), ("3", "4")]:
                if {first, second} <= good.keys():
                    join(good[first], good[second])
        # Resistors, LEDs and supply polarity terminals are deliberately NOT unioned.

    wire_ids: set[str] = set()
    net_ids = {net.id for net in circuit.nets}
    for wire in layout.jumpers:
        if wire.id in wire_ids:
            error("duplicate_jumper", f"Repeated jumper ID {wire.id!r}.")
        wire_ids.add(wire.id)
        if wire.net_id not in net_ids:
            error("unknown_jumper_net", f"Jumper {wire.id} references an unknown net.")
        start_ok = occupy(wire.start, f"{wire.id}.start")
        end_ok = occupy(wire.end, f"{wire.id}.end")
        if start_ok and end_ok:
            join(wire.start, wire.end)

    intended = {member: net.id for net in circuit.nets for member in net.members}
    if circuit.supply is not None:
        if layout.supply is None:
            error("missing_supply_placement", "Supply terminal locations are required.")
        else:
            for polarity, hole, net in [
                ("positive", layout.supply.positive_hole, circuit.supply.positive_net),
                ("negative", layout.supply.negative_hole, circuit.supply.negative_net),
            ]:
                terminal = f"$supply.{polarity}"
                if occupy(hole, terminal):
                    terminals[terminal] = hole
                    intended[terminal] = net
                    group = board.group_for_hole(hole)
                    for segment in model.rail_segments:
                        if segment.conductive_group_id == group and segment.label != (
                            "+" if polarity == "positive" else "-"
                        ):
                            error("rail_polarity", f"{polarity} supply conflicts with rail label.")
    elif layout.supply is not None:
        error("unexpected_supply", "Passive circuit must not introduce a supply.")

    terminal_groups = {
        terminal: graph.find(board.group_for_hole(hole)) for terminal, hole in terminals.items()
    }
    net_groups: dict[str, set[str]] = defaultdict(set)
    group_nets: dict[str, set[str]] = defaultdict(set)
    for terminal, net in intended.items():
        if terminal not in terminal_groups:
            error("missing_terminal", f"Terminal {terminal!r} has no valid physical location.")
            continue
        group = terminal_groups[terminal]
        net_groups[net].add(group)
        group_nets[group].add(net)
    for net, groups in sorted(net_groups.items()):
        if len(groups) > 1:
            error("disconnected_net", f"Net {net!r} is split across {sorted(groups)}.")
    for group, nets in sorted(group_nets.items()):
        if len(nets) > 1:
            error("shorted_nets", f"Physical group {group!r} shorts nets {sorted(nets)}.")
    for wire in layout.jumpers:
        try:
            group = graph.find(board.group_for_hole(wire.start))
        except UnknownHoleError:
            continue
        if group_nets.get(group) != {wire.net_id}:
            error("jumper_net_mismatch", f"Jumper {wire.id!r} is not on its declared logical net.")

    envelopes: dict[str, str] = {}
    for placement in layout.components:
        try:
            expected = expected_pins(placement)
            if expected is None or placement.pins != expected:
                continue
            for hole in component_clearance(placement):
                owner = used.get(hole)
                if owner and not owner.startswith(placement.component_id + "."):
                    error(
                        "body_clearance",
                        f"{placement.component_id} body obstructs {owner} at {hole}.",
                    )
                if hole in envelopes and envelopes[hole] != placement.component_id:
                    error("body_clearance", f"Component body envelopes overlap at {hole}.")
                envelopes[hole] = placement.component_id
        except ValueError:
            continue

    return LayoutValidationResult(
        valid=not errors,
        board_physically_verified=model.verification_status == "physically_verified",
        errors=errors,
        terminal_groups=terminal_groups,
        warnings=[
            ValidationIssue(
                code="reference_footprints",
                message="Footprint dimensions and pin numbering require physical confirmation.",
            ),
            ValidationIssue(
                code="electrical_analysis_pending",
                message=(
                    "Graph equivalence does not establish part ratings, "
                    "current limiting, or electrical safety."
                ),
            ),
            ValidationIssue(code="disconnect_power", message="Disconnect power before wiring."),
        ]
        + (
            [
                ValidationIssue(
                    code="unverified_board",
                    message="This board topology and geometry have not been physically measured.",
                )
            ]
            if model.verification_status != "physically_verified"
            else []
        ),
    )
