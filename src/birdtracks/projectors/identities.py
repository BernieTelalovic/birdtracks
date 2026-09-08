"""Named exact rewrite identities for symbolic projector diagrams."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType
from typing import Callable

from birdtracks.permutations import Permutation

from .permutation_node import PermutationNode
from .projector import Connection, NodePort, Projector
from .projector_sum import ProjectorSum
from .symmetrisers import Antisymmetriser, Symmetriser


@dataclass(frozen=True)
class AlgebraicIdentity:
    """A named, directional rewrite returning ``None`` when it does not match."""

    name: str
    rewrite: Callable[[Projector], ProjectorSum | None]
    automatic: bool = False

    def apply(self, projector: Projector) -> ProjectorSum | None:
        if not isinstance(projector, Projector):
            raise TypeError("an algebraic identity expects a Projector")
        return self.rewrite(projector)


def _annihilate_multiply_connected_s_a(
    projector: Projector,
) -> ProjectorSum | None:
    """Detect distinct S/A strands, including paths through permutations.

    A connection joins consecutive operator ports and therefore represents
    the same strand through every intervening layer on which it is free. An
    expanded operator is a permutation node, so follow its internal mapping
    before deciding which S/A node is reached by that strand.
    """
    counts: dict[tuple[int, int], int] = {}
    next_port = {
        connection.source: connection.target
        for connection in projector.connections
    }
    for source_index, source_node in enumerate(projector.nodes):
        if not isinstance(source_node, (Symmetriser, Antisymmetriser)):
            continue
        for label in source_node.support:
            current = next_port.get(NodePort(source_index, label))
            visited: set[NodePort] = set()
            while current is not None and current not in visited:
                visited.add(current)
                target_node = projector.nodes[current.node]
                if isinstance(target_node, (Symmetriser, Antisymmetriser)):
                    if type(source_node) is not type(target_node):
                        pair = tuple(sorted((source_index, current.node)))
                        counts[pair] = counts.get(pair, 0) + 1
                        if counts[pair] >= 2:
                            return ProjectorSum()
                    break
                if not isinstance(target_node, PermutationNode):
                    break
                output = NodePort(
                    current.node,
                    target_node.permutation(current.label),
                )
                current = next_port.get(output)
    return None


def _absorb_nested_same_type_operator(
    projector: Projector,
) -> ProjectorSum | None:
    """Apply P Q = Q P = P when Q is nested inside same-type P.

    Supports are compared by the actual strands between nodes rather than by
    their local integer names.  Permutation-only nodes may occur along those
    strands; they remain in the graph after the absorbed node is removed.
    """
    next_port = {
        connection.source: connection.target
        for connection in projector.connections
    }
    counts: dict[tuple[int, int], int] = {}
    for source_index, source_node in enumerate(projector.nodes):
        if not isinstance(source_node, (Symmetriser, Antisymmetriser)):
            continue
        for label in source_node.support:
            current = next_port.get(NodePort(source_index, label))
            visited: set[NodePort] = set()
            while current is not None and current not in visited:
                visited.add(current)
                target_node = projector.nodes[current.node]
                if isinstance(target_node, (Symmetriser, Antisymmetriser)):
                    if type(source_node) is type(target_node):
                        pair = (source_index, current.node)
                        counts[pair] = counts.get(pair, 0) + 1
                    break
                if not isinstance(target_node, PermutationNode):
                    break
                current = next_port.get(
                    NodePort(
                        current.node,
                        target_node.permutation(current.label),
                    )
                )

    candidates: list[tuple[tuple[int, int, int, int], int]] = []
    for (source_index, target_index), count in counts.items():
        source_size = len(projector.nodes[source_index].support)
        target_size = len(projector.nodes[target_index].support)
        if count != min(source_size, target_size):
            continue
        # Flow is right-to-left.  For equal supports retain the left factor,
        # exactly as P * Q = P.
        remove_index = (
            source_index if source_size <= target_size else target_index
        )
        candidates.append(
            (
                (-max(source_size, target_size), -count, source_index, target_index),
                remove_index,
            )
        )
    if not candidates:
        return None

    _rank, remove_index = min(candidates)
    return ProjectorSum((_remove_operator(projector, remove_index),))


def _remove_operator(projector: Projector, remove_index: int) -> Projector:
    """Bypass one identity-absorbed S/A without changing any other wiring."""
    node = projector.nodes[remove_index]
    incoming = {
        connection.target.label: connection
        for connection in projector.connections
        if connection.target.node == remove_index
    }
    outgoing = {
        connection.source.label: connection
        for connection in projector.connections
        if connection.source.node == remove_index
    }
    connections = [
        connection
        for connection in projector.connections
        if connection.source.node != remove_index
        and connection.target.node != remove_index
    ]
    for label in node.support:
        before = incoming.get(label)
        after = outgoing.get(label)
        if before is not None and after is not None:
            connections.append(Connection(before.source, after.target))

    input_boundary = dict(projector.input_boundary)
    output_boundary = dict(projector.output_boundary)
    for boundary_label, port in tuple(input_boundary.items()):
        if port.node == remove_index:
            after = outgoing.get(port.label)
            if after is None:
                raise AssertionError("absorbed input strand has no continuation")
            input_boundary[boundary_label] = after.target
    for boundary_label, port in tuple(output_boundary.items()):
        if port.node == remove_index:
            before = incoming.get(port.label)
            if before is None:
                raise AssertionError("absorbed output strand has no continuation")
            output_boundary[boundary_label] = before.source

    def shifted(port: NodePort) -> NodePort:
        return NodePort(port.node - (port.node > remove_index), port.label)

    remaining_nodes = tuple(
        node for index, node in enumerate(projector.nodes) if index != remove_index
    )
    remaining_orders = {
        index - (index > remove_index): {
            "input": orders["input"],
            "output": orders["output"],
        }
        for index, orders in projector.port_orders.items()
        if index != remove_index
    }
    unit = Projector(
        remaining_nodes,
        (
            Connection(shifted(connection.source), shifted(connection.target))
            for connection in connections
        ),
        input_boundary={
            label: shifted(port) for label, port in input_boundary.items()
        },
        output_boundary={
            label: shifted(port) for label, port in output_boundary.items()
        },
        port_orders=remaining_orders,
    )
    return unit * (
        projector.canonical_coefficient / unit.canonical_coefficient
    )


def _recursive_expansion(
    projector: Projector,
    projector_type: type[Symmetriser] | type[Antisymmetriser],
    sign: int,
) -> ProjectorSum | None:
    if len(projector.nodes) != 1 or projector.connections:
        return None
    node = projector.nodes[0]
    if not isinstance(node, projector_type) or len(node.labels) < 2:
        return None

    labels = node.labels
    smaller_operator = (
        projector_type(labels[:-1])
        if len(labels) > 2
        else PermutationNode(Permutation.identity(), support=labels[:-1])
    )
    prefix = Projector(
        [
            smaller_operator,
            PermutationNode(Permutation.identity(), support=(labels[-1],)),
        ]
    )
    transposition = Projector(
        [PermutationNode(Permutation.from_cycle(labels[-2], labels[-1]))]
    )
    sandwiched = prefix * transposition * prefix
    k = len(labels)
    return ProjectorSum(
        (
            (prefix, projector.coefficient * Fraction(1, k)),
            (
                sandwiched,
                projector.coefficient * Fraction(sign * (k - 1), k),
            ),
        )
    )


def _permutation_sign(permutation: Permutation) -> int:
    transpositions = sum(len(cycle) - 1 for cycle in permutation.cycles())
    return -1 if transpositions % 2 else 1


def _absorb_permutation(
    projector: Projector,
    projector_type: type[Symmetriser] | type[Antisymmetriser],
    permutation_on_left: bool,
) -> ProjectorSum | None:
    if len(projector.nodes) != 2 or projector.port_orders_are_explicit:
        return None
    first, second = projector.nodes
    permutation_node, operator = (
        (first, second) if permutation_on_left else (second, first)
    )
    if not isinstance(permutation_node, PermutationNode) or not isinstance(
        operator, projector_type
    ):
        return None
    if not permutation_node.support <= operator.support:
        return None
    if projector != Projector(projector.nodes, coefficient=projector.coefficient):
        return None

    sign = (
        _permutation_sign(permutation_node.permutation)
        if isinstance(operator, Antisymmetriser)
        else 1
    )
    reduced = Projector([operator], coefficient=projector.coefficient * sign)
    return ProjectorSum((reduced,))


MULTIPLY_CONNECTED_S_A_ANNIHILATION = AlgebraicIdentity(
    "multiply_connected_symmetriser_antisymmetriser_annihilation",
    _annihilate_multiply_connected_s_a,
    automatic=True,
)
SAME_TYPE_NESTED_ABSORPTION = AlgebraicIdentity(
    "same_type_nested_absorption",
    _absorb_nested_same_type_operator,
    automatic=True,
)
SYMMETRISER_RECURSION = AlgebraicIdentity(
    "symmetriser_recursion",
    lambda projector: _recursive_expansion(projector, Symmetriser, 1),
)
ANTISYMMETRISER_RECURSION = AlgebraicIdentity(
    "antisymmetriser_recursion",
    lambda projector: _recursive_expansion(projector, Antisymmetriser, -1),
)
PERMUTATION_LEFT_SYMMETRISER_ABSORPTION = AlgebraicIdentity(
    "permutation_left_symmetriser_absorption",
    lambda projector: _absorb_permutation(projector, Symmetriser, True),
    automatic=True,
)
PERMUTATION_RIGHT_SYMMETRISER_ABSORPTION = AlgebraicIdentity(
    "permutation_right_symmetriser_absorption",
    lambda projector: _absorb_permutation(projector, Symmetriser, False),
    automatic=True,
)
PERMUTATION_LEFT_ANTISYMMETRISER_ABSORPTION = AlgebraicIdentity(
    "permutation_left_antisymmetriser_absorption",
    lambda projector: _absorb_permutation(projector, Antisymmetriser, True),
    automatic=True,
)
PERMUTATION_RIGHT_ANTISYMMETRISER_ABSORPTION = AlgebraicIdentity(
    "permutation_right_antisymmetriser_absorption",
    lambda projector: _absorb_permutation(projector, Antisymmetriser, False),
    automatic=True,
)

IDENTITIES = MappingProxyType(
    {
        identity.name: identity
        for identity in (
            MULTIPLY_CONNECTED_S_A_ANNIHILATION,
            SAME_TYPE_NESTED_ABSORPTION,
            SYMMETRISER_RECURSION,
            ANTISYMMETRISER_RECURSION,
            PERMUTATION_LEFT_SYMMETRISER_ABSORPTION,
            PERMUTATION_RIGHT_SYMMETRISER_ABSORPTION,
            PERMUTATION_LEFT_ANTISYMMETRISER_ABSORPTION,
            PERMUTATION_RIGHT_ANTISYMMETRISER_ABSORPTION,
        )
    }
)


__all__ = [
    "AlgebraicIdentity",
    "ANTISYMMETRISER_RECURSION",
    "IDENTITIES",
    "MULTIPLY_CONNECTED_S_A_ANNIHILATION",
    "PERMUTATION_LEFT_ANTISYMMETRISER_ABSORPTION",
    "PERMUTATION_LEFT_SYMMETRISER_ABSORPTION",
    "PERMUTATION_RIGHT_ANTISYMMETRISER_ABSORPTION",
    "PERMUTATION_RIGHT_SYMMETRISER_ABSORPTION",
    "SAME_TYPE_NESTED_ABSORPTION",
    "SYMMETRISER_RECURSION",
]
