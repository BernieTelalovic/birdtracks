"""Variable-length supervised policy environment for hybrid S/A reduction."""

from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Literal

from .hybrid_simplification import (
    ExposureTarget,
    SATarget,
    _recursive_arrangements,
    find_sa_exposure_targets,
    find_sa_targets,
    sa_pair_paths,
    sa_pair_ready_to_collapse,
)
from .projector import Projector
from .projector_sum import ProjectorSum
from .simplification import recursive_expand_node
from .symmetrisers import Antisymmetriser, Symmetriser

PolicyKind = Literal["resolver", "exposer"]
PolicyTarget = SATarget | ExposureTarget
FEATURE_COUNT = 25


@dataclass(frozen=True)
class RewriteCandidate:
    """One rearrangement plus one costly recursive-identity application."""

    node: int
    side: Literal["input", "output"]
    rearrangements: int
    result: ProjectorSum
    features: tuple[float, ...]
    oracle_score: tuple[int, ...]


def rewrite_candidates(
    projector: Projector, target: PolicyTarget, kind: PolicyKind
) -> tuple[RewriteCandidate, ...]:
    """Enumerate legal target-conditioned atomic actions and exact outcomes."""
    _validate_kind_target(kind, target)
    endpoint_objects = (
        projector.nodes[target.symmetriser],
        projector.nodes[target.antisymmetriser],
    )
    raw = []
    for node_index in target.intervening_nodes:
        node = projector.nodes[node_index]
        if not isinstance(node, (Symmetriser, Antisymmetriser)):
            continue
        for side in ("input", "output"):
            for arranged, rearrangements in _recursive_arrangements(
                projector, node_index, side
            ):
                result = recursive_expand_node(arranged, node_index, side=side)
                metrics = _outcome_metrics(result, endpoint_objects, kind)
                score = _oracle_score(metrics, rearrangements, kind)
                features = _action_features(
                    projector, target, node_index, side, rearrangements,
                    result, metrics,
                )
                raw.append(RewriteCandidate(
                    node_index, side, rearrangements, result, features, score
                ))
    # Equal outcomes can arise through equivalent port arrangements. Retain the
    # cheapest deterministic representative so they do not distort labels.
    unique: dict[ProjectorSum, RewriteCandidate] = {}
    for candidate in raw:
        previous = unique.get(candidate.result)
        if previous is None or (
            candidate.oracle_score, candidate.node, candidate.side
        ) < (previous.oracle_score, previous.node, previous.side):
            unique[candidate.result] = candidate
    return tuple(sorted(
        unique.values(),
        key=lambda candidate: (
            candidate.node, candidate.side, candidate.rearrangements,
            repr(candidate.result),
        ),
    ))


def oracle_trajectory(
    projector: Projector,
    target: PolicyTarget,
    kind: PolicyKind,
    *,
    maximum_steps: int = 128,
) -> tuple[tuple[tuple[RewriteCandidate, ...], tuple[int, ...]], ...]:
    """Return oracle-labelled states until success, repetition, or safety cap.

    Recursive rewrites are the only learned actions. Automatic cleanup already
    occurs inside each action. Resolver endpoint collapse is deliberately not
    represented here because it is a deterministic terminal operation.
    """
    if maximum_steps < 1:
        raise ValueError("maximum_steps must be positive")
    _validate_kind_target(kind, target)
    records = []
    visited = {projector}
    current, current_target = projector, target
    for _ in range(maximum_steps):
        candidates = rewrite_candidates(current, current_target, kind)
        if not candidates:
            break
        best_score = min(candidate.oracle_score for candidate in candidates)
        best = tuple(
            index for index, candidate in enumerate(candidates)
            if candidate.oracle_score == best_score
        )
        records.append((candidates, best))
        selected = candidates[best[0]]
        continuations = _continuations(
            selected.result,
            (current.nodes[current_target.symmetriser],
             current.nodes[current_target.antisymmetriser]),
            kind,
        )
        if not continuations:
            break
        current, current_target = max(
            continuations,
            key=lambda item: (
                len(item[1].intervening_nodes),
                len(item[0].nodes),
                repr(item[0]),
            ),
        )
        if current in visited:
            break
        visited.add(current)
    return tuple(records)


def _outcome_metrics(
    result: ProjectorSum,
    endpoint_objects: tuple[object, object],
    kind: PolicyKind,
) -> tuple[int, int, int, int, int, int]:
    terminal = unresolved = obstructed = nodes = layers = 0
    for child, _coefficient in result:
        mapped = _mapped_pair(child, endpoint_objects)
        if mapped is None:
            terminal += 1
            continue
        symmetriser, antisymmetriser = mapped
        paths = sa_pair_paths(child, symmetriser, antisymmetriser)
        direct = sum(path.direct for path in paths)
        blocked = sum(not path.direct for path in paths)
        success = (
            direct > 0 if kind == "exposer"
            else sa_pair_ready_to_collapse(child, symmetriser, antisymmetriser)
        )
        if success:
            terminal += 1
        else:
            unresolved += 1
            obstructed += sum(len(path.intervening_nodes) for path in paths)
        nodes += len(child.nodes)
        layers += len(child.layers)
    return len(result), terminal, unresolved, obstructed, nodes, layers


def _oracle_score(
    metrics: tuple[int, int, int, int, int, int],
    rearrangements: int,
    kind: PolicyKind,
) -> tuple[int, ...]:
    live, terminal, unresolved, obstructed, nodes, layers = metrics
    # Success/progress dominates; live combinatorics dominates the very small
    # rearrangement and step proxies. Repeated application yields trajectories
    # of unrestricted learned length up to the caller's safety cap.
    return (
        unresolved,
        live,
        obstructed,
        -terminal,
        rearrangements,
        nodes,
        layers,
        int(kind == "exposer"),
    )


def _action_features(
    projector: Projector,
    target: PolicyTarget,
    node_index: int,
    side: str,
    rearrangements: int,
    result: ProjectorSum,
    metrics: tuple[int, int, int, int, int, int],
) -> tuple[float, ...]:
    layer_of = {
        node: layer
        for layer, members in enumerate(projector.layers)
        for node in members
    }
    node = projector.nodes[node_index]
    paths = (
        (*target.direct_paths, *target.potential_paths)
        if isinstance(target, SATarget) else target.obstructed_paths
    )
    direct = sum(path.direct for path in paths)
    blocked = len(paths) - direct
    live, terminal, unresolved, obstructed, result_nodes, result_layers = metrics
    features = (
        len(projector.support) / 32.0,
        len(projector.layers) / 24.0,
        len(projector.nodes) / 64.0,
        target.support_union_size / 32.0,
        direct / 8.0,
        blocked / 8.0,
        len(target.intervening_nodes) / 32.0,
        abs(layer_of[target.symmetriser] - layer_of[target.antisymmetriser]) / 24.0,
        float(isinstance(node, Symmetriser)),
        float(isinstance(node, Antisymmetriser)),
        len(node.support) / 32.0,
        layer_of[node_index] / max(1, len(projector.layers) - 1),
        abs(layer_of[node_index] - layer_of[target.symmetriser]) / 24.0,
        abs(layer_of[node_index] - layer_of[target.antisymmetriser]) / 24.0,
        sum(node_index in path.intervening_nodes for path in paths) / 8.0,
        float(side == "input"),
        float(side == "output"),
        rearrangements / 4.0,
        live / 16.0,
        max(0, 2 - live) / 2.0,
        terminal / max(1, live),
        unresolved / max(1, live),
        obstructed / 32.0,
        result_nodes / 128.0,
        result_layers / 48.0,
    )
    if len(features) != FEATURE_COUNT:
        raise AssertionError("hybrid policy feature count drifted")
    return features


def _continuations(
    result: ProjectorSum,
    endpoint_objects: tuple[object, object],
    kind: PolicyKind,
) -> list[tuple[Projector, PolicyTarget]]:
    continuations = []
    for child, _coefficient in result:
        mapped = _mapped_pair(child, endpoint_objects)
        if mapped is None:
            continue
        symmetriser, antisymmetriser = mapped
        paths = sa_pair_paths(child, symmetriser, antisymmetriser)
        if kind == "exposer" and any(path.direct for path in paths):
            continue
        if kind == "resolver" and sa_pair_ready_to_collapse(
            child, symmetriser, antisymmetriser
        ):
            continue
        candidates: tuple[PolicyTarget, ...] = (
            find_sa_targets(child)
            if kind == "resolver" else find_sa_exposure_targets(child)
        )
        matching = next(
            (target for target in candidates if target.nodes == mapped), None
        )
        if matching is not None:
            continuations.append((child, matching))
    return continuations


def _mapped_pair(
    projector: Projector, endpoint_objects: tuple[object, object]
) -> tuple[int, int] | None:
    indices = []
    for endpoint in endpoint_objects:
        matches = [
            index for index, node in enumerate(projector.nodes)
            if node is endpoint
        ]
        if len(matches) != 1:
            return None
        indices.append(matches[0])
    return indices[0], indices[1]


def _validate_kind_target(kind: PolicyKind, target: PolicyTarget) -> None:
    if kind not in {"resolver", "exposer"}:
        raise ValueError("kind must be 'resolver' or 'exposer'")
    expected = SATarget if kind == "resolver" else ExposureTarget
    if not isinstance(target, expected):
        raise TypeError(f"{kind} policy received the wrong target type")


__all__ = [
    "FEATURE_COUNT",
    "PolicyKind",
    "RewriteCandidate",
    "oracle_trajectory",
    "rewrite_candidates",
]
