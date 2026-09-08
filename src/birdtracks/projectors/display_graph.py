"""Immutable, algebra-independent display plans for projector diagrams."""

from __future__ import annotations

from dataclasses import dataclass

from .permutation_node import PermutationNode
from .projector import NodePort, Projector


@dataclass(frozen=True)
class DisplayEndpoint:
    """One end of a visible corridor strand."""

    kind: str
    label: int
    node: int | None = None


@dataclass(frozen=True)
class DisplayStrand:
    """A single visible strand with exact-graph provenance."""

    source: DisplayEndpoint
    target: DisplayEndpoint
    strand_label: int
    permutation_nodes: tuple[int, ...] = ()


@dataclass(frozen=True)
class DisplayGraph:
    """A rendering plan whose columns contain only genuine S/A operators."""

    operator_columns: tuple[tuple[int, ...], ...]
    strands: tuple[DisplayStrand, ...]
    pure_permutation: bool
    crossing_count: int
    corridor_complexities: tuple[int, ...]

    def as_dict(self) -> dict[str, object]:
        """Return deterministic JSON-compatible widget metadata."""
        return {
            "operator_columns": [list(column) for column in self.operator_columns],
            "strands": [
                {
                    "source": _endpoint_dict(strand.source),
                    "target": _endpoint_dict(strand.target),
                    "strand_label": strand.strand_label,
                    "permutation_nodes": list(strand.permutation_nodes),
                }
                for strand in self.strands
            ],
            "pure_permutation": self.pure_permutation,
            "crossing_count": self.crossing_count,
            "corridor_complexities": list(self.corridor_complexities),
        }


def compile_display_graph(projector: Projector) -> DisplayGraph:
    """Compile exact topology into operator columns separated by wiring corridors.

    Permutation nodes are traversed rather than emitted as columns.  The exact
    :class:`Projector` remains untouched and is still used for every algebraic
    operation and editor save.
    """
    if not isinstance(projector, Projector):
        raise TypeError("compile_display_graph expects a Projector")

    operators = {
        index
        for index, node in enumerate(projector.nodes)
        if not isinstance(node, PermutationNode) and len(node.support) > 1
    }
    columns = tuple(
        tuple(index for index in layer if index in operators)
        for layer in projector.layers
        if any(index in operators for index in layer)
    )
    connection_target = {
        connection.source: connection.target for connection in projector.connections
    }
    output_boundary = {
        port: label for label, port in projector.output_boundary.items()
    }
    strands: list[DisplayStrand] = []
    strand_at_input: dict[NodePort, int] = {}
    strand_at_output: dict[NodePort, int] = {}
    for boundary_label, start in sorted(projector.input_boundary.items()):
        current = start
        while True:
            strand_at_input[current] = boundary_label
            node = projector.nodes[current.node]
            mapped = (
                node.permutation(current.label)
                if isinstance(node, PermutationNode)
                else current.label
            )
            output = NodePort(current.node, mapped)
            strand_at_output[output] = boundary_label
            target = connection_target.get(output)
            if target is None:
                break
            current = target

    def trace(
        source: DisplayEndpoint,
        current: NodePort,
        strand_label: int,
        provenance: tuple[int, ...] = (),
    ) -> None:
        visited: set[NodePort] = set()
        while current.node not in operators:
            if current in visited:
                raise ValueError("display wiring contains a permutation-only cycle")
            visited.add(current)
            node = projector.nodes[current.node]
            if not isinstance(node, PermutationNode) and len(node.support) > 1:
                raise AssertionError("operator classification is inconsistent")
            provenance += (current.node,)
            mapped = (
                node.permutation(current.label)
                if isinstance(node, PermutationNode)
                else current.label
            )
            output = NodePort(current.node, mapped)
            target = connection_target.get(output)
            if target is None:
                try:
                    label = output_boundary[output]
                except KeyError as exc:
                    raise ValueError("display strand reaches no output boundary") from exc
                strands.append(
                    DisplayStrand(
                        source,
                        DisplayEndpoint("left_boundary", label),
                        strand_label,
                        provenance,
                    )
                )
                return
            current = target
        strands.append(
            DisplayStrand(
                source,
                DisplayEndpoint("operator_input", current.label, current.node),
                strand_label,
                provenance,
            )
        )

    for boundary_label, port in sorted(projector.input_boundary.items()):
        trace(DisplayEndpoint("right_boundary", boundary_label), port, boundary_label)
    for index in sorted(operators):
        node = projector.nodes[index]
        for label in sorted(node.support):
            output = NodePort(index, label)
            target = connection_target.get(output)
            source = DisplayEndpoint("operator_output", label, index)
            strand_label = strand_at_output[output]
            if target is None:
                try:
                    boundary_label = output_boundary[output]
                except KeyError as exc:
                    raise ValueError("display strand reaches no output boundary") from exc
                strands.append(
                    DisplayStrand(
                        source,
                        DisplayEndpoint("left_boundary", boundary_label),
                        strand_label,
                    )
                )
            else:
                trace(source, target, strand_label)

    ordered = tuple(
        sorted(
            strands,
            key=lambda strand: (
                strand.source.kind,
                -1 if strand.source.node is None else strand.source.node,
                strand.source.label,
                strand.target.kind,
                -1 if strand.target.node is None else strand.target.node,
                strand.target.label,
            ),
        )
    )
    boundary_mapping = {
        strand.source.label: strand.target.label
        for strand in ordered
        if strand.source.kind == "right_boundary"
        and strand.target.kind == "left_boundary"
    }
    crossing_count = sum(
        left_source < right_source and boundary_mapping[left_source] > boundary_mapping[right_source]
        for left_source in sorted(boundary_mapping)
        for right_source in sorted(boundary_mapping)
    )
    column_of = {
        node_index: column
        for column, node_indices in enumerate(columns)
        for node_index in node_indices
    }
    corridor_complexities = [0] * (len(columns) + 1)
    for strand in ordered:
        source_position = (
            len(columns)
            if strand.source.kind == "right_boundary"
            else column_of[strand.source.node]
        )
        target_position = (
            -1
            if strand.target.kind == "left_boundary"
            else column_of[strand.target.node]
        )
        complexity = sum(
            _permutation_inversions(projector.nodes[index])
            for index in strand.permutation_nodes
        )
        for corridor in range(target_position + 1, source_position + 1):
            corridor_complexities[corridor] = max(
                corridor_complexities[corridor], complexity
            )
    return DisplayGraph(
        columns,
        ordered,
        not columns,
        crossing_count,
        tuple(corridor_complexities),
    )


def _permutation_inversions(node: object) -> int:
    if not isinstance(node, PermutationNode):
        return 0
    values = [node.permutation(label) for label in sorted(node.support)]
    return sum(
        left > right
        for index, left in enumerate(values)
        for right in values[index + 1 :]
    )


def _endpoint_dict(endpoint: DisplayEndpoint) -> dict[str, object]:
    result: dict[str, object] = {"kind": endpoint.kind, "label": endpoint.label}
    if endpoint.node is not None:
        result["node"] = endpoint.node
    return result


__all__ = [
    "DisplayEndpoint",
    "DisplayGraph",
    "DisplayStrand",
    "compile_display_graph",
]
