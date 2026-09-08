"""Targeted S/A simplification primitives for the hybrid strategy."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .permutation_node import PermutationNode
from .projector import NodePort, Projector
from .projector_sum import ProjectorSum
from .simplification import expand_node, permute_node_ports, recursive_expand_node
from .symmetrisers import Antisymmetriser, Symmetriser


@dataclass(frozen=True)
class StrandPath:
    """One physical strand between two S/A nodes."""

    source: NodePort
    target: NodePort
    intervening_nodes: tuple[int, ...]

    @property
    def direct(self) -> bool:
        return not self.intervening_nodes


@dataclass(frozen=True)
class SATarget:
    """Opposite-type nodes with one direct and a potential second strand."""

    symmetriser: int
    antisymmetriser: int
    support_union: frozenset[int]
    direct_paths: tuple[StrandPath, ...]
    potential_paths: tuple[StrandPath, ...]

    @property
    def support_union_size(self) -> int:
        return len(self.support_union)

    @property
    def nodes(self) -> tuple[int, int]:
        return self.symmetriser, self.antisymmetriser

    @property
    def intervening_nodes(self) -> tuple[int, ...]:
        return tuple(sorted({
            node
            for path in self.potential_paths
            for node in path.intervening_nodes
        }))


@dataclass(frozen=True)
class ExposureTarget:
    """Opposite-type nodes joined only by obstructed physical strands."""

    symmetriser: int
    antisymmetriser: int
    support_union: frozenset[int]
    obstructed_paths: tuple[StrandPath, ...]

    @property
    def support_union_size(self) -> int:
        return len(self.support_union)

    @property
    def nodes(self) -> tuple[int, int]:
        return self.symmetriser, self.antisymmetriser

    @property
    def intervening_nodes(self) -> tuple[int, ...]:
        return tuple(sorted({
            node
            for path in self.obstructed_paths
            for node in path.intervening_nodes
        }))


def find_sa_targets(projector: Projector) -> tuple[SATarget, ...]:
    """Find S/A pairs with one direct and another obstructed physical strand."""
    if not isinstance(projector, Projector):
        raise TypeError("find_sa_targets expects a Projector")
    paths = _opposite_sa_paths(projector)
    targets = []
    for pair, pair_paths in paths.items():
        direct = tuple(path for path in pair_paths if path.direct)
        potential = tuple(path for path in pair_paths if not path.direct)
        if len(direct) != 1 or not potential:
            continue
        symmetriser, antisymmetriser = _typed_pair(projector, pair)
        targets.append(SATarget(
            symmetriser,
            antisymmetriser,
            _support_union(projector, pair),
            direct,
            potential,
        ))
    return tuple(sorted(
        targets,
        key=lambda target: (
            -target.support_union_size,
            target.symmetriser,
            target.antisymmetriser,
        ),
    ))


def find_sa_exposure_targets(projector: Projector) -> tuple[ExposureTarget, ...]:
    """Find separated S/A pairs joined by obstructed but no direct strands."""
    if not isinstance(projector, Projector):
        raise TypeError("find_sa_exposure_targets expects a Projector")
    layer_of = {
        node_index: layer_index
        for layer_index, layer in enumerate(projector.layers)
        for node_index in layer
    }
    targets = []
    for pair, pair_paths in _opposite_sa_paths(projector).items():
        if any(path.direct for path in pair_paths):
            continue
        obstructed = tuple(path for path in pair_paths if not path.direct)
        if not obstructed or abs(layer_of[pair[0]] - layer_of[pair[1]]) < 2:
            continue
        symmetriser, antisymmetriser = _typed_pair(projector, pair)
        targets.append(ExposureTarget(
            symmetriser,
            antisymmetriser,
            _support_union(projector, pair),
            obstructed,
        ))
    return tuple(sorted(
        targets,
        key=lambda target: (
            -target.support_union_size,
            target.symmetriser,
            target.antisymmetriser,
        ),
    ))


def sa_pair_paths(
    projector: Projector, symmetriser: int, antisymmetriser: int
) -> tuple[StrandPath, ...]:
    """Return every physical strand between one explicitly selected S/A pair."""
    if not isinstance(projector, Projector):
        raise TypeError("sa_pair_paths expects a Projector")
    if not 0 <= symmetriser < len(projector.nodes):
        raise IndexError("symmetriser node is outside the projector")
    if not 0 <= antisymmetriser < len(projector.nodes):
        raise IndexError("antisymmetriser node is outside the projector")
    if not isinstance(projector.nodes[symmetriser], Symmetriser):
        raise TypeError("selected symmetriser node is not a Symmetriser")
    if not isinstance(projector.nodes[antisymmetriser], Antisymmetriser):
        raise TypeError("selected antisymmetriser node is not an Antisymmetriser")
    pair = tuple(sorted((symmetriser, antisymmetriser)))
    return tuple(_opposite_sa_paths(projector).get(pair, ()))


def sa_pair_ready_to_collapse(
    projector: Projector, symmetriser: int, antisymmetriser: int
) -> bool:
    """Return whether a selected pair is adjacent and connected only directly."""
    paths = sa_pair_paths(projector, symmetriser, antisymmetriser)
    if not paths or not all(path.direct for path in paths):
        return False
    layer_of = {
        node_index: layer_index
        for layer_index, layer in enumerate(projector.layers)
        for node_index in layer
    }
    return abs(layer_of[symmetriser] - layer_of[antisymmetriser]) == 1


def collapse_resolved_sa_pair(
    projector: Projector, symmetriser: int, antisymmetriser: int
) -> ProjectorSum:
    """Fully expand an adjacent resolved pair, then run automatic cleanup."""
    if not sa_pair_ready_to_collapse(projector, symmetriser, antisymmetriser):
        raise ValueError("selected S/A pair is not ready for final collapse")
    current = ProjectorSum((projector,))
    for node_index in sorted((symmetriser, antisymmetriser), reverse=True):
        expanded = []
        for term, outer_coefficient in current:
            for candidate, local_coefficient in expand_node(term, node_index):
                expanded.append((
                    candidate,
                    outer_coefficient * local_coefficient,
                ))
        current = ProjectorSum(expanded)
    return _automatic_cleanup(current)


def _opposite_sa_paths(
    projector: Projector,
) -> dict[tuple[int, int], list[StrandPath]]:
    paths: dict[tuple[int, int], list[StrandPath]] = {}
    next_port = {
        connection.source: connection.target
        for connection in projector.connections
    }
    for source_index, source_node in enumerate(projector.nodes):
        if not isinstance(source_node, (Symmetriser, Antisymmetriser)):
            continue
        for source_label in source_node.support:
            current = next_port.get(NodePort(source_index, source_label))
            intervening: list[int] = []
            visited: set[NodePort] = set()
            while current is not None and current not in visited:
                visited.add(current)
                node = projector.nodes[current.node]
                if isinstance(node, (Symmetriser, Antisymmetriser)):
                    if type(node) is not type(source_node):
                        key = tuple(sorted((source_index, current.node)))
                        paths.setdefault(key, []).append(
                            StrandPath(
                                NodePort(source_index, source_label),
                                current,
                                tuple(intervening),
                            )
                        )
                    intervening.append(current.node)
                    current = next_port.get(NodePort(current.node, current.label))
                    continue
                if not isinstance(node, PermutationNode):
                    break
                current = next_port.get(
                    NodePort(current.node, node.permutation(current.label))
                )
    return paths


def _typed_pair(projector: Projector, pair: tuple[int, int]) -> tuple[int, int]:
    left, right = pair
    symmetriser = left if isinstance(projector.nodes[left], Symmetriser) else right
    return symmetriser, right if symmetriser == left else left


def _support_union(
    projector: Projector, pair: tuple[int, int]
) -> frozenset[int]:
    return (
        frozenset(projector.nodes[pair[0]].support)
        | frozenset(projector.nodes[pair[1]].support)
    )


def resolve_sa_target_step(projector: Projector, target: SATarget) -> ProjectorSum:
    """Choose the exact recursive corridor rewrite with fewest survivors."""
    if target not in find_sa_targets(projector):
        raise ValueError("target does not belong to this projector")
    candidates: list[tuple[tuple[object, ...], ProjectorSum]] = []
    for node_index in target.intervening_nodes:
        node = projector.nodes[node_index]
        if not isinstance(node, (Symmetriser, Antisymmetriser)):
            continue
        for side in ("input", "output"):
            for arranged, rearrangements in _recursive_arrangements(
                projector, node_index, side
            ):
                result = recursive_expand_node(arranged, node_index, side=side)
                remaining_targets = sum(
                    len(find_sa_targets(term)) for term, _ in result
                )
                candidates.append((
                    (
                        len(result),
                        remaining_targets,
                        rearrangements,
                        -len(node.support),
                        node_index,
                        side,
                        repr(result),
                    ),
                    result,
                ))
    if not candidates:
        return ProjectorSum((projector,))
    return min(candidates, key=lambda item: item[0])[1]


def expose_sa_target_step(
    projector: Projector, target: ExposureTarget | None = None
) -> ProjectorSum:
    """Choose one recursive rewrite exposing the largest support-union target."""
    if target is not None and target not in find_sa_exposure_targets(projector):
        raise ValueError("exposure target does not belong to this projector")
    if find_sa_targets(projector):
        return ProjectorSum((projector,))
    candidates: list[tuple[tuple[object, ...], ProjectorSum]] = []
    for node_index, node in enumerate(projector.nodes):
        if not isinstance(node, (Symmetriser, Antisymmetriser)) or len(node.support) < 2:
            continue
        for side in ("input", "output"):
            for arranged, rearrangements in _recursive_arrangements(
                projector, node_index, side
            ):
                result = recursive_expand_node(arranged, node_index, side=side)
                exposed = [
                    candidate_target
                    for term, _ in result
                    for candidate_target in find_sa_targets(term)
                    if target is None
                    or candidate_target.nodes == target.nodes
                ]
                if not exposed:
                    continue
                largest = max(target.support_union_size for target in exposed)
                candidates.append((
                    (
                        -largest,
                        len(result),
                        rearrangements,
                        node_index,
                        side,
                        repr(result),
                    ),
                    result,
                ))
    if not candidates:
        return ProjectorSum((projector,))
    return min(candidates, key=lambda item: item[0])[1]


def hybrid_simplify_step(value: Projector | ProjectorSum) -> ProjectorSum:
    """Resolve the largest target, otherwise try to expose one, in one term."""
    current = value if isinstance(value, ProjectorSum) else ProjectorSum((value,))
    current = _automatic_cleanup(current)
    ranked: list[tuple[tuple[int, int, int, str], int, SATarget]] = []
    terms = list(current)
    for term_index, (projector, _coefficient) in enumerate(terms):
        targets = find_sa_targets(projector)
        if targets:
            target = targets[0]
            ranked.append((
                (-target.support_union_size, target.symmetriser, target.antisymmetriser, repr(projector)),
                term_index,
                target,
            ))
    if ranked:
        _rank, term_index, target = min(ranked)
        projector, coefficient = terms.pop(term_index)
        replacement = resolve_sa_target_step(projector, target)
        return ProjectorSum((
            *terms,
            *((term, coefficient * factor) for term, factor in replacement),
        ))

    exposures = []
    for term_index, (projector, coefficient) in enumerate(terms):
        exposure_targets = find_sa_exposure_targets(projector)
        selected_exposure = exposure_targets[0] if exposure_targets else None
        replacement = expose_sa_target_step(projector, selected_exposure)
        exposed_size = max(
            (
                target.support_union_size
                for term, _ in replacement
                for target in find_sa_targets(term)
            ),
            default=0,
        )
        if exposed_size:
            exposures.append((-exposed_size, term_index, projector, coefficient, replacement))
    if not exposures:
        return current
    _rank, term_index, _projector, coefficient, replacement = min(
        exposures, key=lambda item: (item[0], item[1])
    )
    terms.pop(term_index)
    return ProjectorSum((
        *terms,
        *((term, coefficient * factor) for term, factor in replacement),
    ))


def hybrid_reduce(
    value: Projector | ProjectorSum, *, maximum_steps: int = 256
) -> ProjectorSum:
    """Apply targeted stages until every term has at most two S/A layers."""
    if maximum_steps < 0:
        raise ValueError("maximum_steps cannot be negative")
    current = _automatic_cleanup(
        value if isinstance(value, ProjectorSum) else ProjectorSum((value,))
    )
    visited = {current}
    for _ in range(maximum_steps):
        if all(_sa_layer_count(projector) <= 2 for projector, _ in current):
            break
        candidate = hybrid_simplify_step(current)
        if candidate == current or candidate in visited:
            break
        current = candidate
        visited.add(current)
    return current


def hybrid_collapse(
    value: Projector | ProjectorSum,
    *,
    maximum_steps: int = 256,
    dimension: int | float | Fraction | None = None,
) -> object:
    """Run the hybrid reduction and exactly collapse its surviving remainder."""
    return hybrid_reduce(value, maximum_steps=maximum_steps).collapse(
        dimension=dimension
    )


def _automatic_cleanup(value: ProjectorSum) -> ProjectorSum:
    pending = list(value)
    survivors: list[tuple[Projector, Fraction]] = []
    while pending:
        projector, coefficient = pending.pop()
        rewritten = projector.simplify()
        if len(rewritten) == 1 and rewritten.coefficient(projector) == 1:
            survivors.append((projector, coefficient))
        else:
            pending.extend(
                (candidate, coefficient * factor)
                for candidate, factor in rewritten
            )
    return ProjectorSum(survivors)


def _sa_layer_count(projector: Projector) -> int:
    return sum(
        any(
            isinstance(projector.nodes[index], (Symmetriser, Antisymmetriser))
            for index in layer
        )
        for layer in projector.layers
    )


def _recursive_arrangements(
    projector: Projector, node_index: int, side: str
) -> tuple[tuple[Projector, int], ...]:
    order = tuple(projector.port_orders[node_index][side])
    if len(order) < 2:
        return ()
    arrangements: dict[tuple[int, ...], tuple[Projector, int]] = {}
    for penultimate in order:
        for last in order:
            if penultimate == last:
                continue
            desired = (penultimate, last)
            if order[-2:] == desired:
                arranged, moves = projector, 0
            else:
                one_move = None
                for index in range(len(order)):
                    for destination in range(len(order)):
                        if index == destination:
                            continue
                        candidate = permute_node_ports(
                            projector, node_index, side, index, destination
                        )
                        if tuple(candidate.port_orders[node_index][side])[-2:] == desired:
                            one_move = candidate
                            break
                    if one_move is not None:
                        break
                if one_move is not None:
                    arranged, moves = one_move, 1
                else:
                    arranged = permute_node_ports(
                        projector,
                        node_index,
                        side,
                        order.index(penultimate),
                        len(order) - 1,
                    )
                    current = tuple(arranged.port_orders[node_index][side])
                    arranged = permute_node_ports(
                        arranged,
                        node_index,
                        side,
                        current.index(last),
                        len(current) - 1,
                    )
                    moves = 2
            final_order = tuple(arranged.port_orders[node_index][side])
            previous = arrangements.get(final_order)
            if previous is None or moves < previous[1]:
                arrangements[final_order] = arranged, moves
    return tuple(arrangements[key] for key in sorted(arrangements))


__all__ = [
    "collapse_resolved_sa_pair",
    "ExposureTarget",
    "SATarget",
    "StrandPath",
    "expose_sa_target_step",
    "find_sa_targets",
    "find_sa_exposure_targets",
    "hybrid_collapse",
    "hybrid_reduce",
    "hybrid_simplify_step",
    "resolve_sa_target_step",
    "sa_pair_paths",
    "sa_pair_ready_to_collapse",
]
