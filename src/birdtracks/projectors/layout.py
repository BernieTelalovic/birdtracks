"""Display-only layout and serialization for projector graphs."""

from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction
from math import hypot

from .projector import NodePort, Projector
from .display_graph import compile_display_graph
from .permutation_node import PermutationNode
from .style import load_projector_style
from .symmetrisers import Antisymmetriser

Style = Mapping[str, float | str]


def default_positions(
    projector: Projector, style: Style | None = None
) -> dict[str, dict[str, float]]:
    """Return deterministic initial node positions, separate from algebra state."""
    geometry = _geometry(style)
    inputs, _outputs = _fixed_boundaries(projector)
    input_strands, output_strands = _strand_side_labels(projector, inputs)
    port_orders, _sign = _crossing_reduced_port_orders(projector)
    return _positions_for_orders(
        projector, geometry, port_orders, input_strands, output_strands
    )


def _positions_for_orders(
    projector: Projector,
    geometry: Style,
    port_orders: dict[int, dict[str, list[int]]],
    input_strands: Mapping[NodePort, int],
    output_strands: Mapping[NodePort, int],
) -> dict[str, dict[str, float]]:
    positions: dict[str, dict[str, float]] = {}
    rank = {label: index for index, label in enumerate(sorted(projector.support))}
    display_layers = compile_display_graph(projector).operator_columns
    for layer_index, layer in enumerate(display_layers):
        ordered = _crossing_reduced_order(
            projector, layer, input_strands, output_strands, rank
        )
        starts = _block_starts(
            projector,
            ordered,
            port_orders,
            rank,
            input_strands,
            output_strands,
        )
        for node_index in ordered:
            line_count = max(1, len(projector.nodes[node_index].support))
            positions[str(node_index)] = {
                "x": float(
                    geometry["first_layer_x"]
                    + geometry["layer_step"] * layer_index
                ),
                "y": float(
                    geometry["top_line_level"]
                    + (starts[node_index] + (line_count - 1) / 2)
                    * geometry["level_spacing"]
                ),
            }
    node_layers = _node_layers(projector)
    for node_index, node in enumerate(projector.nodes):
        if str(node_index) in positions:
            continue
        line_count = max(1, len(node.support))
        positions[str(node_index)] = {
            "x": float(
                geometry["first_layer_x"]
                + geometry["layer_step"] * node_layers[node_index]
            ),
            "y": float(
                geometry["top_line_level"]
                + (line_count - 1) / 2 * geometry["level_spacing"]
            ),
        }
    return positions


def detangle(projector: Projector) -> Projector:
    """Return an equal projector with locally optimized internal line order.

    The graph topology and fixed boundary attachments are never modified.  A
    deterministic adjacent-swap search first minimizes total visible wire
    displacement, then maximizes straight segments and minimizes crossings.  Any
    odd antisymmetriser port permutation is absorbed into the exact displayed
    coefficient.
    """
    if not isinstance(projector, Projector):
        raise TypeError("detangle expects a Projector")
    if not projector.nodes:
        return projector

    orders = {
        index: {
            "input": list(sides["input"]),
            "output": list(sides["output"]),
        }
        for index, sides in projector.port_orders.items()
    }
    score = _detangle_score(projector, orders)
    # Each accepted adjacent swap strictly improves the finite layout score,
    # so this terminates without an arbitrary iteration cutoff.
    while True:
        best_score = score
        best_orders: dict[int, dict[str, list[int]]] | None = None
        for index, node in enumerate(projector.nodes):
            if len(node.support) < 2:
                continue
            for side in ("input", "output"):
                for position in range(len(orders[index][side]) - 1):
                    candidate = {
                        key: {
                            "input": list(value["input"]),
                            "output": list(value["output"]),
                        }
                        for key, value in orders.items()
                    }
                    order = candidate[index][side]
                    order[position], order[position + 1] = (
                        order[position + 1],
                        order[position],
                    )
                    candidate_score = _detangle_score(projector, candidate)
                    if candidate_score < best_score:
                        best_score = candidate_score
                        best_orders = candidate
        if best_orders is None:
            break
        orders = best_orders
        score = best_score

    unit = Projector(
        projector.nodes,
        projector.connections,
        input_boundary=projector.input_boundary,
        output_boundary=projector.output_boundary,
        port_orders=orders,
    )
    result = unit * (
        projector.canonical_coefficient
        / unit.canonical_coefficient
    )
    if result != projector:  # Defensive invariant: layout may never alter topology.
        raise AssertionError("detangling changed the projector's algebraic value")
    return result


def _compiled_display_state(
    projector: Projector, geometry: dict[str, object]
) -> dict[str, object]:
    """Compile disposable strand routing using the supplied geometry."""
    display = compile_display_graph(projector)
    geometry["right_boundary"] = (
        float(geometry["first_layer_x"])
        + float(geometry["layer_step"]) * max(0, len(projector.layers) - 1)
        + float(geometry["operator_width"]) / 2
        + float(geometry["step"]) / 2
    )
    if display.pure_permutation:
        # A little extra room makes dense crossings readable, but the complete
        # corridor never exceeds the footprint of two adjacent operators.
        base = 2.0 * float(geometry["step"])
        cap = 1.2 * base
        corridor_width = min(cap, base + 0.05 * base * display.crossing_count)
        corridor_widths = [corridor_width]
        geometry["right_boundary"] = float(geometry["left_boundary"]) + corridor_width
    else:
        corridor_width = None
        complexities = display.corridor_complexities
        corridor_widths = [
            float(geometry["step"])
            * (1.0 + 0.2 * min(1.0, complexity / 6.0))
            for complexity in complexities
        ]
        # The boundary-to-operator transitions are permutations too.  Their
        # own traced complexity is often zero, which used to overwrite the
        # visual widening selected for a dense interior corridor and made the
        # first/last crossings look squeezed.  Give both edge transitions the
        # widest effective corridor used by this display graph.
        if corridor_widths:
            widest_corridor = max(corridor_widths)
            corridor_widths[0] = widest_corridor
            corridor_widths[-1] = widest_corridor
        geometry["right_boundary"] = (
            float(geometry["left_boundary"])
            + len(display.operator_columns) * float(geometry["operator_width"])
            + sum(corridor_widths)
        )
    return {
        **display.as_dict(),
        "corridor_width": corridor_width,
        "corridor_widths": corridor_widths,
    }


def widget_graph(
    projector: Projector, style: Style | None = None
) -> dict[str, object]:
    """Serialize immutable topology into JSON-compatible widget state."""
    geometry = _geometry(style)
    display_state = _compiled_display_state(projector, geometry)
    inputs, outputs = _fixed_boundaries(projector)
    port_orders, port_swap_sign = _crossing_reduced_port_orders(projector)
    display_coefficient = projector.coefficient * port_swap_sign
    node_layers = _node_layers(projector)
    positions = default_positions(projector, geometry)
    input_strands, output_strands = _strand_side_labels(projector, inputs)
    boundary_labels = sorted({label for label, _port in inputs + outputs})
    free_levels = _free_levels(
        projector,
        positions,
        node_layers,
        input_strands,
        boundary_labels,
        geometry,
    )
    return {
        "display": display_state,
        "base_coefficient": {
            "numerator": str(display_coefficient.numerator),
            "denominator": str(display_coefficient.denominator),
        },
        "coefficient": {
            "numerator": str(display_coefficient.numerator),
            "denominator": str(display_coefficient.denominator),
        },
        "port_swap_sign": port_swap_sign,
        "layer_count": len(projector.layers),
        "geometry": geometry,
        "nodes": [
            {
                "index": index,
                "layer": node_layers[index],
                "kind": "antisymmetriser"
                if isinstance(node, Antisymmetriser) and len(node.support) > 1
                else "permutation"
                if isinstance(node, PermutationNode) or len(node.support) == 1
                else "symmetriser",
                "labels": sorted(node.support),
                "input_labels": port_orders[index]["input"],
                "output_labels": port_orders[index]["output"],
                "mapping": (
                    [[label, node.permutation(label)] for label in sorted(node.support)]
                    if isinstance(node, PermutationNode)
                    else None
                    if len(node.support) > 1
                    else [[label, label] for label in sorted(node.support)]
                ),
            }
            for index, node in enumerate(projector.nodes)
        ],
        "connections": [
            {
                "source": _port_data(connection.source),
                "target": _port_data(connection.target),
                "boundary_label": output_strands.get(
                    connection.source, connection.source.label
                ),
            }
            for connection in projector.connections
        ],
        "external_inputs": [
            {"boundary_label": label, "port": _port_data(port)}
            for label, port in inputs
        ],
        "external_outputs": [
            {"boundary_label": label, "port": _port_data(port)}
            for label, port in outputs
        ],
        "boundary_labels": boundary_labels,
        "free_levels": free_levels,
    }


def validated_positions(
    projector: Projector,
    positions: Mapping[int | str, tuple[float, float] | Mapping[str, float]],
    style: Style | None = None,
) -> dict[str, dict[str, float]]:
    """Validate optional user positions and fill unspecified nodes."""
    result = default_positions(projector, style)
    for raw_index, raw_position in positions.items():
        try:
            index = int(raw_index)
        except (TypeError, ValueError) as exc:
            raise TypeError("position keys must be node indices") from exc
        if isinstance(raw_index, bool) or str(index) not in result:
            raise ValueError(f"position references unknown node {raw_index!r}")
        if isinstance(raw_position, Mapping):
            try:
                x, y = raw_position["x"], raw_position["y"]
            except KeyError as exc:
                raise ValueError("mapped positions require x and y") from exc
        else:
            try:
                x, y = raw_position
            except (TypeError, ValueError) as exc:
                raise TypeError("positions must be (x, y) pairs") from exc
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise TypeError("position coordinates must be numbers")
        if isinstance(y, bool) or not isinstance(y, (int, float)):
            raise TypeError("position coordinates must be numbers")
        # Horizontal coordinates are fixed by layer; custom layout only moves
        # an operator between vertical levels.
        result[str(index)] = {"x": result[str(index)]["x"], "y": float(y)}
    return result


def _port_data(port: NodePort) -> dict[str, int]:
    return {"node": port.node, "label": port.label}


def _operator_height(line_count: int, geometry: Style) -> float:
    gaps = max(0, line_count - 1)
    return (
        gaps * float(geometry["level_spacing"])
        + 2 * float(geometry["operator_padding"])
    )


def _block_starts(
    projector: Projector,
    ordered: tuple[int, ...],
    port_orders: dict[int, dict[str, list[int]]],
    rank: dict[int, int],
    input_strands: Mapping[NodePort, int],
    output_strands: Mapping[NodePort, int],
) -> dict[int, int]:
    """Place compact operator blocks on fixed levels without layer overlap."""
    level_count = max(1, len(rank))
    widths = {
        index: max(1, len(projector.nodes[index].support)) for index in ordered
    }
    starts: dict[int, int] = {}
    minimum = 0
    for position, index in enumerate(ordered):
        remaining = sum(widths[later] for later in ordered[position + 1 :])
        maximum = max(minimum, level_count - remaining - widths[index])
        candidates = range(minimum, maximum + 1)

        def score(start: int) -> tuple[int, int, int]:
            matches = 0
            displacement = 0
            for side in ("input", "output"):
                strands = input_strands if side == "input" else output_strands
                for offset, label in enumerate(port_orders[index][side]):
                    target = rank[strands[NodePort(index, label)]]
                    level = start + offset
                    matches += level == target
                    displacement += abs(level - target)
            return -matches, displacement, start

        best = min(candidates, key=score)
        starts[index] = best
        minimum = best + widths[index]
    return starts


def _fixed_boundaries(
    projector: Projector,
) -> tuple[tuple[tuple[int, NodePort], ...], tuple[tuple[int, NodePort], ...]]:
    """Return the projector's explicit right and left boundary wiring."""
    return (
        tuple(sorted(projector.input_boundary.items(), key=lambda item: item[1])),
        tuple(sorted(projector.output_boundary.items(), key=lambda item: item[1])),
    )


def _node_layers(projector: Projector) -> dict[int, int]:
    return {
        node_index: layer_index
        for layer_index, layer in enumerate(projector.layers)
        for node_index in layer
    }


def _strand_side_labels(
    projector: Projector,
    inputs: tuple[tuple[int, NodePort], ...],
) -> tuple[dict[NodePort, int], dict[NodePort, int]]:
    """Trace boundary strands without conflating permutation input/output ports."""
    next_port = {
        connection.source: connection.target
        for connection in projector.connections
    }
    input_labels: dict[NodePort, int] = {}
    output_labels: dict[NodePort, int] = {}
    for boundary_label, start in inputs:
        current = start
        while True:
            input_labels[current] = boundary_label
            node = projector.nodes[current.node]
            output = (
                NodePort(current.node, node.permutation(current.label))
                if isinstance(node, PermutationNode)
                else current
            )
            output_labels[output] = boundary_label
            if output not in next_port:
                break
            current = next_port[output]
    return input_labels, output_labels


def _free_levels(
    projector: Projector,
    positions: dict[str, dict[str, float]],
    node_layers: dict[int, int],
    input_strands: Mapping[NodePort, int],
    boundary_labels: list[int],
    geometry: Style,
) -> dict[str, dict[str, int]]:
    """Assign pass-through strands to unused levels in every layer."""
    rank = {label: index for index, label in enumerate(boundary_labels)}
    result: dict[str, dict[str, int]] = {
        str(layer_index): {} for layer_index in range(len(projector.layers))
    }
    display = compile_display_graph(projector)
    for layer in display.operator_columns:
        layer_index = node_layers[layer[0]]
        occupied: set[int] = set()
        active_labels: set[int] = set()
        for node_index in layer:
            node = projector.nodes[node_index]
            count = max(1, len(node.support))
            centre = positions[str(node_index)]["y"]
            start = round(
                (centre - float(geometry["top_line_level"]))
                / float(geometry["level_spacing"])
                - (count - 1) / 2
            )
            occupied.update(range(start, start + count))
            active_labels.update(
                input_strands[NodePort(node_index, label)]
                for label in node.support
            )
        free_labels = sorted(
            set(boundary_labels) - active_labels,
            key=lambda label: rank[label],
        )
        available = sorted(set(range(len(boundary_labels))) - occupied)
        result[str(layer_index)] = {
            str(label): level
            for label, level in zip(free_labels, available)
        }
    return result


def _detangle_score(
    projector: Projector,
    port_orders: dict[int, dict[str, list[int]]],
) -> tuple[float, int, int]:
    """Score the wiring that remains visible after free-layer collapse."""
    geometry = _geometry(None)
    inputs, outputs = _fixed_boundaries(projector)
    input_strands, output_strands = _strand_side_labels(projector, inputs)
    positions = _positions_for_orders(
        projector, geometry, port_orders, input_strands, output_strands
    )
    node_layers = _node_layers(projector)
    boundary_labels = sorted(projector.support)
    boundary_rank = {
        label: position for position, label in enumerate(boundary_labels)
    }
    free_levels = _free_levels(
        projector,
        positions,
        node_layers,
        input_strands,
        boundary_labels,
        geometry,
    )

    display = compile_display_graph(projector)
    display_layers = display.operator_columns
    layer_interfaces: dict[int, tuple[dict[int, int], dict[int, int]]] = {}
    for display_index, layer in enumerate(display_layers):
        exact_layer = node_layers[layer[0]]
        input_levels = {
            int(label): int(level)
            for label, level in free_levels[str(exact_layer)].items()
        }
        output_levels = dict(input_levels)
        for node_index in layer:
            node = projector.nodes[node_index]
            count = len(node.support)
            centre = positions[str(node_index)]["y"]
            start = round(
                (centre - float(geometry["top_line_level"]))
                / float(geometry["level_spacing"])
                - (count - 1) / 2
            )
            for offset, label in enumerate(port_orders[node_index]["input"]):
                input_levels[input_strands[NodePort(node_index, label)]] = (
                    start + offset
                )
            for offset, label in enumerate(port_orders[node_index]["output"]):
                output_levels[output_strands[NodePort(node_index, label)]] = (
                    start + offset
                )
        layer_interfaces[display_index] = input_levels, output_levels

    # Score every inter-layer segment separately.  In particular, a strand
    # crossing several layers contributes its displacement in every gap
    # instead of being measured once as a direct endpoint-to-endpoint jump.
    visible_layers = list(range(len(display_layers)))
    right_boundary = dict(boundary_rank)
    left_boundary = {
        output_strands[port]: boundary_rank[boundary_label]
        for boundary_label, port in outputs
    }
    gaps: list[tuple[Mapping[int, int], Mapping[int, int]]] = []
    if visible_layers:
        rightmost = visible_layers[-1]
        gaps.append((right_boundary, layer_interfaces[rightmost][0]))
        for right_layer, left_layer in zip(
            reversed(visible_layers[1:]), reversed(visible_layers[:-1])
        ):
            gaps.append(
                (
                    layer_interfaces[right_layer][1],
                    layer_interfaces[left_layer][0],
                )
            )
        leftmost = visible_layers[0]
        gaps.append((layer_interfaces[leftmost][1], left_boundary))
    else:
        gaps.append((right_boundary, left_boundary))

    straight = 0
    crossings = 0
    length = 0.0
    corridor_widths = tuple(
        1.0 + 0.2 * min(1.0, complexity / 6.0)
        for complexity in reversed(display.corridor_complexities)
    )
    for (right, left), horizontal in zip(gaps, corridor_widths, strict=True):
        strands = sorted(right, key=lambda label: (right[label], label))
        left_positions = [left[label] for label in strands]
        straight += sum(right[label] == left[label] for label in strands)
        length += sum(
            hypot(horizontal, right[label] - left[label]) for label in strands
        )
        crossings += sum(
            first > second
            for position, first in enumerate(left_positions)
            for second in left_positions[position + 1 :]
        )
    return length, -straight, crossings


def _geometry(style: Style | None) -> dict[str, float | str]:
    configured = dict(load_projector_style() if style is None else style)
    width = float(configured["operator_width"])
    step = float(configured["step"])
    level_spacing = float(configured["level_spacing"])
    left_boundary = float(configured["coefficient_space"])
    configured.update(
        {
            "operator_padding": level_spacing
            * float(configured["operator_padding_fraction"]),
            "top_line_level": float(configured["top_margin"]),
            "node_width": width,
            "layer_step": width + step,
            "left_boundary": left_boundary,
            "first_layer_x": left_boundary + step / 2 + width / 2,
            # Coefficient typography follows diagram geometry rather than
            # independently tuned pixel sizes.
            "coefficient_font_size": 0.75 * level_spacing,
            "fraction_font_size": 0.75 * level_spacing,
            "fraction_height": 0.8 * level_spacing,
            "fraction_line_width": float(configured["line_width"]),
        }
    )
    return configured


def _crossing_reduced_port_orders(
    projector: Projector,
) -> tuple[dict[int, dict[str, list[int]]], int]:
    """Order each node side toward its neighbours and return the induced sign."""
    if projector.port_orders_are_explicit:
        orders = {
            index: {
                "input": list(sides["input"]),
                "output": list(sides["output"]),
            }
            for index, sides in projector.port_orders.items()
        }
        sign = 1
        for index, node in enumerate(projector.nodes):
            if not isinstance(node, Antisymmetriser):
                continue
            canonical = sorted(node.support)
            if _is_odd_order(orders[index]["input"], canonical):
                sign = -sign
            if _is_odd_order(orders[index]["output"], canonical):
                sign = -sign
        return orders, sign
    source_neighbour = {
        connection.source: connection.target.label
        for connection in projector.connections
    }
    target_neighbour = {
        connection.target: connection.source.label
        for connection in projector.connections
    }
    orders: dict[int, dict[str, list[int]]] = {}
    sign = 1
    for index, node in enumerate(projector.nodes):
        canonical = sorted(node.support)
        input_labels = sorted(
            canonical,
            key=lambda label: (
                target_neighbour.get(NodePort(index, label), label), label
            ),
        )
        output_labels = sorted(
            canonical,
            key=lambda label: (
                source_neighbour.get(NodePort(index, label), label), label
            ),
        )
        orders[index] = {"input": input_labels, "output": output_labels}
        if isinstance(node, Antisymmetriser):
            if _is_odd_order(input_labels, canonical):
                sign = -sign
            if _is_odd_order(output_labels, canonical):
                sign = -sign
    return orders, sign


def _is_odd_order(order: list[int], canonical: list[int]) -> bool:
    rank = {label: index for index, label in enumerate(canonical)}
    values = [rank[label] for label in order]
    inversions = sum(
        left > right
        for index, left in enumerate(values)
        for right in values[index + 1 :]
    )
    return bool(inversions % 2)


def _crossing_reduced_order(
    projector: Projector,
    layer: tuple[int, ...],
    input_strands: Mapping[NodePort, int],
    output_strands: Mapping[NodePort, int],
    rank: Mapping[int, int],
) -> tuple[int, ...]:
    """Order disjoint nodes by the centre of their canonical boundary tracks.

    Keeping each node's ports consecutive means interleaved supports cannot
    always avoid crossings. Ordering by exact mean rank minimizes displacement
    from the fixed boundary order and deterministically reduces crossings.
    """
    def key(index: int) -> tuple[Fraction, int]:
        support = projector.nodes[index].support
        positions = [
            rank[strands[NodePort(index, label)]]
            for strands in (input_strands, output_strands)
            for label in support
        ]
        centre = (
            Fraction(sum(positions), len(positions))
            if support
            else Fraction()
        )
        return centre, index

    return tuple(sorted(layer, key=key))


__all__ = ["default_positions", "detangle", "validated_positions", "widget_graph"]
