"""BLISS-backed canonical forms for symbolic projector graphs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import igraph

from .permutation_node import PermutationNode
from .symmetrisers import Antisymmetriser, Symmetriser


@dataclass(frozen=True)
class _Port:
    node: int
    side: str
    ordinal: int


@dataclass(frozen=True)
class _BoundaryPort:
    node: int
    label: int


def canonical_graph_key(
    nodes: Sequence[object],
    connections: Sequence[object],
    input_boundary: Mapping[int, object],
    output_boundary: Mapping[int, object],
) -> tuple[tuple[object, ...], int]:
    """Return an internal-label-free certificate and orientation sign.

    Edge direction and kind are encoded using colored vertices because BLISS
    canonicalizes simple undirected colored graphs.
    """
    absorbed = _absorb_complete_permutation(
        nodes, connections, input_boundary, output_boundary
    )
    if absorbed is not None:
        operator, absorption_sign = absorbed
        boundary = {
            label: _BoundaryPort(0, label) for label in operator.support
        }
        certificate, orientation_sign = canonical_graph_key(
            [operator], [], boundary, boundary
        )
        return certificate, absorption_sign * orientation_sign

    vertex_colors: list[tuple[object, ...]] = []
    edges: list[tuple[int, int]] = []
    ports: dict[int, _Port] = {}
    input_ports: dict[tuple[int, int], int] = {}
    output_ports: dict[tuple[int, int], int] = {}
    boundary_inputs = {
        (port.node, port.label): label for label, port in input_boundary.items()
    }
    boundary_outputs = {
        (port.node, port.label): label for label, port in output_boundary.items()
    }

    def add_vertex(color: tuple[object, ...]) -> int:
        result = len(vertex_colors)
        vertex_colors.append(color)
        return result

    def add_arc(source: int, target: int, kind: str) -> None:
        tail = add_vertex(("arc", kind, "tail"))
        middle = add_vertex(("arc", kind, "middle"))
        head = add_vertex(("arc", kind, "head"))
        edges.extend(
            ((source, tail), (tail, middle), (middle, head), (head, target))
        )

    for node_index, node in enumerate(nodes):
        if isinstance(node, Symmetriser):
            kind, labels = "S", node.labels
        elif isinstance(node, Antisymmetriser):
            kind, labels = "A", node.labels
        elif isinstance(node, PermutationNode):
            kind, labels = "P", tuple(sorted(node.support))
        else:  # pragma: no cover - Projector validates nodes first
            raise TypeError(f"unsupported projector node {node!r}")

        operator = add_vertex(("operator", kind, len(labels)))
        for ordinal, label in enumerate(labels):
            local_key = (node_index, label)
            input_port = add_vertex(
                ("port", "input", boundary_inputs.get(local_key))
            )
            output_port = add_vertex(
                ("port", "output", boundary_outputs.get(local_key))
            )
            input_ports[local_key] = input_port
            output_ports[local_key] = output_port
            ports[input_port] = _Port(node_index, "input", ordinal)
            ports[output_port] = _Port(node_index, "output", ordinal)
            add_arc(operator, input_port, "operator_input")
            add_arc(operator, output_port, "operator_output")

        if isinstance(node, PermutationNode):
            for label in labels:
                add_arc(
                    input_ports[(node_index, label)],
                    output_ports[(node_index, node.permutation(label))],
                    "permutation",
                )

    for connection in connections:
        add_arc(
            output_ports[(connection.source.node, connection.source.label)],
            input_ports[(connection.target.node, connection.target.label)],
            "connection",
        )

    color_ids = _color_ids(vertex_colors)
    graph = igraph.Graph(len(vertex_colors), edges=edges, directed=False)
    canonical_order = tuple(graph.canonical_permutation(color=color_ids))
    permutation = [0] * len(canonical_order)
    for new, old in enumerate(canonical_order):
        permutation[old] = new
    canonical_colors: list[tuple[object, ...] | None] = [None] * len(permutation)
    canonical_edges = []
    for old, new in enumerate(permutation):
        canonical_colors[new] = vertex_colors[old]
    for left, right in edges:
        canonical_edges.append(tuple(sorted((permutation[left], permutation[right]))))
    certificate: tuple[object, ...] = (
        tuple(canonical_colors),
        tuple(sorted(canonical_edges)),
    )

    sign = _canonical_orientation_sign(permutation, ports, nodes)
    if any(
        _automorphism_sign(generator, ports, nodes) < 0
        for generator in graph.automorphism_group(color=color_ids)
    ):
        sign = 0
    return certificate, sign


def _absorb_complete_permutation(
    nodes: Sequence[object],
    connections: Sequence[object],
    input_boundary: Mapping[int, object],
    output_boundary: Mapping[int, object],
) -> tuple[Symmetriser | Antisymmetriser, int] | None:
    if len(nodes) != 2:
        return None
    permutation_nodes = [node for node in nodes if isinstance(node, PermutationNode)]
    operators = [
        node for node in nodes if isinstance(node, (Symmetriser, Antisymmetriser))
    ]
    if len(permutation_nodes) != 1 or len(operators) != 1:
        return None
    permutation_node = permutation_nodes[0]
    operator = operators[0]
    if not permutation_node.support <= operator.support:
        return None
    if set(input_boundary) != operator.support or set(output_boundary) != operator.support:
        return None
    if len(connections) != len(permutation_node.support):
        return None

    permutation_index = nodes.index(permutation_node)
    operator_index = nodes.index(operator)
    # This shortcut encodes the ordinary product P*S/A, whose intermediate
    # strands retain their labels.  More general two-node graphs (notably a
    # crossed connection into an antisymmetriser) carry an additional
    # orientation sign and must go through the full graph canonicalizer.
    expected_connections = {
        frozenset(
            (
                (permutation_index, label),
                (operator_index, label),
            )
        )
        for label in permutation_node.support
    }
    actual_connections = {
        frozenset(
            (
                (connection.source.node, connection.source.label),
                (connection.target.node, connection.target.label),
            )
        )
        for connection in connections
    }
    if actual_connections != expected_connections:
        return None

    left_index, right_index = 0, 1
    expected_inputs = {
        label: (right_index if label in permutation_node.support else operator_index, label)
        for label in operator.support
    }
    expected_outputs = {
        label: (left_index if label in permutation_node.support else operator_index, label)
        for label in operator.support
    }
    actual_inputs = {
        label: (port.node, port.label) for label, port in input_boundary.items()
    }
    actual_outputs = {
        label: (port.node, port.label) for label, port in output_boundary.items()
    }
    if actual_inputs != expected_inputs or actual_outputs != expected_outputs:
        return None
    sign = (
        _permutation_parity(permutation_node)
        if isinstance(operator, Antisymmetriser)
        else 1
    )
    return operator, sign


def _permutation_parity(node: PermutationNode) -> int:
    transpositions = sum(len(cycle) - 1 for cycle in node.permutation.cycles())
    return -1 if transpositions % 2 else 1


def _color_ids(colors: Sequence[tuple[object, ...]]) -> list[int]:
    ordered = sorted(set(colors), key=repr)
    rank = {color: index for index, color in enumerate(ordered)}
    return [rank[color] for color in colors]


def _canonical_orientation_sign(
    permutation: Sequence[int],
    ports: Mapping[int, _Port],
    nodes: Sequence[object],
) -> int:
    sign = 1
    for node_index, node in enumerate(nodes):
        if not isinstance(node, Antisymmetriser):
            continue
        for side in ("input", "output"):
            ordered = sorted(
                (
                    (permutation[vertex], port.ordinal)
                    for vertex, port in ports.items()
                    if port.node == node_index and port.side == side
                )
            )
            sign *= _parity([ordinal for _rank, ordinal in ordered])
    return sign


def _automorphism_sign(
    permutation: Sequence[int],
    ports: Mapping[int, _Port],
    nodes: Sequence[object],
) -> int:
    sign = 1
    for node_index, node in enumerate(nodes):
        if not isinstance(node, Antisymmetriser):
            continue
        for side in ("input", "output"):
            source = sorted(
                (
                    (port.ordinal, vertex)
                    for vertex, port in ports.items()
                    if port.node == node_index and port.side == side
                )
            )
            target_ordinals = [ports[permutation[vertex]].ordinal for _, vertex in source]
            sign *= _parity(target_ordinals)
    return sign


def _parity(values: Sequence[int]) -> int:
    inversions = sum(
        left > right
        for index, left in enumerate(values)
        for right in values[index + 1 :]
    )
    return -1 if inversions % 2 else 1


__all__ = ["canonical_graph_key"]
