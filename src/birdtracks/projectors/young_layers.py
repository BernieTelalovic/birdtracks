"""Recognition of Young diagrams formed by adjacent S/A layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from .symmetrisers import Antisymmetriser, Symmetriser

if TYPE_CHECKING:
    from .projector import Projector


YoungLayerOrder = Literal["SA", "AS"]


@dataclass(frozen=True, order=True)
class YoungLayerPair:
    """A Young diagram represented by one adjacent S/A layer pair."""

    shape: tuple[int, ...]
    support: frozenset[int]
    layers: tuple[int, int]
    order: YoungLayerOrder


@dataclass(frozen=True, order=True)
class BracketingYoungLayers:
    """Two equal Young-layer pairs enclosing only subset-supported S/A nodes."""

    shape: tuple[int, ...]
    support: frozenset[int]
    occurrences: tuple[YoungLayerPair, YoungLayerPair]

    @property
    def layers(self) -> tuple[tuple[int, int], tuple[int, int]]:
        """The layer indices of the two occurrences."""
        first, second = self.occurrences
        return first.layers, second.layers


def identify_largest_young_layer_pair(
    projector: Projector,
) -> YoungLayerPair | None:
    """Return the largest Young diagram in any two adjacent layers."""
    matches = _young_layer_pairs(projector)
    return min(matches, key=_largest_first_key) if matches else None


def identify_bracketing_young_layers(
    projector: Projector,
) -> BracketingYoungLayers | None:
    """Return the largest repeated Young pair bracketing compatible S/A nodes.

    The two occurrences have equal shape and support but opposite layer order.
    Every other symmetriser or antisymmetriser between them must have support
    contained in that common support.  Non-S/A nodes do not affect matching.
    """
    matches = _young_layer_pairs(projector)
    candidates: list[BracketingYoungLayers] = []
    for position, first in enumerate(matches):
        for second in matches[position + 1 :]:
            if first.layers[1] >= second.layers[0]:
                continue
            if (
                first.shape != second.shape
                or first.support != second.support
                or first.order == second.order
            ):
                continue
            if not _interior_sa_supports_are_subsets(
                projector, first, second
            ):
                continue
            candidates.append(
                BracketingYoungLayers(
                    first.shape, first.support, (first, second)
                )
            )
    return min(candidates, key=_largest_bracket_key) if candidates else None


def _young_layer_pairs(projector: Projector) -> tuple[YoungLayerPair, ...]:
    connection_counts: dict[frozenset[int], int] = {}
    for connection in projector.connections:
        node_pair = frozenset((connection.source.node, connection.target.node))
        connection_counts[node_pair] = connection_counts.get(node_pair, 0) + 1

    matches: list[YoungLayerPair] = []
    for left_layer in range(len(projector.layers) - 1):
        right_layer = left_layer + 1
        left_nodes = projector.layers[left_layer]
        right_nodes = projector.layers[right_layer]
        for order, s_indices, a_indices in (
            (
                "SA",
                tuple(i for i in left_nodes if isinstance(projector.nodes[i], Symmetriser)),
                tuple(i for i in right_nodes if isinstance(projector.nodes[i], Antisymmetriser)),
            ),
            (
                "AS",
                tuple(i for i in right_nodes if isinstance(projector.nodes[i], Symmetriser)),
                tuple(i for i in left_nodes if isinstance(projector.nodes[i], Antisymmetriser)),
            ),
        ):
            for component_s, component_a in _overlap_components(
                s_indices, a_indices, connection_counts
            ):
                if not all(
                    connection_counts.get(frozenset((s_index, a_index)), 0) == 1
                    for s_index in component_s
                    for a_index in component_a
                ):
                    continue
                s_blocks = tuple(projector.nodes[index].support for index in component_s)
                a_blocks = tuple(projector.nodes[index].support for index in component_a)
                support = frozenset().union(*s_blocks, *a_blocks)
                rows = _partition_with_singletons(s_blocks, support)
                columns = _partition_with_singletons(a_blocks, support)
                if columns == _conjugate_partition(rows):
                    matches.append(
                        YoungLayerPair(
                            rows, support, (left_layer, right_layer), order
                        )
                    )
    return tuple(matches)


def _overlap_components(
    s_indices: tuple[int, ...],
    a_indices: tuple[int, ...],
    connection_counts: dict[frozenset[int], int],
) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    remaining = {("S", index) for index in s_indices}
    remaining.update(("A", index) for index in a_indices)
    components: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    while remaining:
        pending = [remaining.pop()]
        component: set[tuple[str, int]] = set()
        while pending:
            kind, index = pending.pop()
            component.add((kind, index))
            opposite = "A" if kind == "S" else "S"
            opposite_indices = a_indices if kind == "S" else s_indices
            neighbours = {
                (opposite, other)
                for other in opposite_indices
                if connection_counts.get(frozenset((index, other)), 0)
                and (opposite, other) in remaining
            }
            remaining.difference_update(neighbours)
            pending.extend(neighbours)
        component_s = tuple(sorted(index for kind, index in component if kind == "S"))
        component_a = tuple(sorted(index for kind, index in component if kind == "A"))
        if component_s and component_a:
            components.append((component_s, component_a))
    return tuple(components)


def _partition_with_singletons(
    blocks: tuple[frozenset[int], ...], support: frozenset[int]
) -> tuple[int, ...]:
    covered = frozenset().union(*blocks)
    return tuple(sorted(
        (len(block) for block in blocks), reverse=True
    )) + (1,) * len(support - covered)


def _conjugate_partition(partition: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(
        sum(length >= column for length in partition)
        for column in range(1, partition[0] + 1)
    ) if partition else ()


def _interior_sa_supports_are_subsets(
    projector: Projector,
    first: YoungLayerPair,
    second: YoungLayerPair,
) -> bool:
    return all(
        node.support <= first.support
        for layer_index in range(first.layers[1] + 1, second.layers[0])
        for node_index in projector.layers[layer_index]
        if isinstance(
            (node := projector.nodes[node_index]),
            (Symmetriser, Antisymmetriser),
        )
    )


def _largest_first_key(match: YoungLayerPair) -> tuple[object, ...]:
    return (-len(match.support), match.layers, match.shape, match.order)


def _largest_bracket_key(match: BracketingYoungLayers) -> tuple[object, ...]:
    first, second = match.occurrences
    return (
        -len(match.support),
        -(second.layers[1] - first.layers[0]),
        first.layers,
        second.layers,
        match.shape,
    )
