"""Training states for the complete S/A exposure strategy.

The lower-level :mod:`hybrid_policy_training` module assumes that an S/A
target has already been selected.  This module exposes the decision actually
made by a human calculator: choose an anchor pair, choose an intervening S/A,
choose a topology-preserving port arrangement, and apply one recursive
identity.  Every candidate is generated and evaluated by the exact symbolic
kernel; a learner only ranks those candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from math import lgamma
from os import PathLike
from pathlib import Path
from typing import Callable, Sequence

from .hybrid_policy_training import (
    FEATURE_COUNT as REWRITE_FEATURE_COUNT,
    RewriteCandidate,
    rewrite_candidates,
)
from .hybrid_simplification import SATarget, find_sa_targets
from .projector import Projector
from .projector_sum import ProjectorSum

DATASET_FORMAT = "birdtracks-hybrid-strategy-preferences"
DATASET_VERSION = 1

STRATEGY_FEATURE_NAMES = (
    "term_log_expansion_weight",
    "anchor_additive_domain_size",
    "anchor_larger_domain_size",
    "anchor_smaller_domain_size",
    "anchor_shared_domain_size",
    "anchor_union_domain_size",
    "direct_path_count",
    "obstructed_path_count",
    "minimum_path_blockers",
    "total_path_blockers",
    "mediator_domain_size",
    "mediator_other_blockers",
    "mediator_other_shared_domain_total",
    "mediator_other_shared_domain_max",
    "mediator_farthest_anchor_distance",
    "mediator_anchor_distance_total",
    "mediator_anchor_distance_imbalance",
    "mediator_path_multiplicity",
    *(f"rewrite_{index}" for index in range(REWRITE_FEATURE_COUNT)),
)
STRATEGY_FEATURE_COUNT = len(STRATEGY_FEATURE_NAMES)


@dataclass(frozen=True)
class MediatorObstruction:
    """The cheapest physical path on which a node mediates an anchor pair."""

    other_blockers: int
    shared_domain_total: int
    shared_domain_max: int
    farthest_anchor_distance: int
    anchor_distance_total: int
    anchor_distance_imbalance: int
    path_multiplicity: int

    @property
    def rank(self) -> tuple[int, ...]:
        """Human-inspired lexicographic notion of least obfuscated."""
        return (
            self.other_blockers,
            self.shared_domain_total,
            self.shared_domain_max,
            self.farthest_anchor_distance,
            self.anchor_distance_total,
            self.anchor_distance_imbalance,
        )


@dataclass(frozen=True)
class StrategyCandidate:
    """One complete anchor–mediator–arrangement–rewrite macro action."""

    term_index: int
    projector: Projector
    target: SATarget
    rewrite: RewriteCandidate
    obstruction: MediatorObstruction
    features: tuple[float, ...]
    oracle_score: tuple[int, ...]

    @property
    def node(self) -> int:
        return self.rewrite.node

    @property
    def result(self) -> ProjectorSum:
        return self.rewrite.result


@dataclass(frozen=True)
class PreferenceGroup:
    """One variable-sized ranking decision and all acceptable choices."""

    features: tuple[tuple[float, ...], ...]
    preferred: tuple[int, ...]


class LearnedHybridStrategy:
    """Optional PyTorch ranker loaded behind the dependency-free core API."""

    def __init__(self, checkpoint: str | PathLike[str]) -> None:
        try:
            import torch
            from torch import nn
        except ImportError as exc:
            raise ImportError(
                "the learned strategy requires: pip install 'birdtracks[training]'"
            ) from exc
        payload = torch.load(
            Path(checkpoint), map_location="cpu", weights_only=True
        )
        if (
            payload.get("model_kind") != "hybrid_strategy_action_ranker_v1"
            or payload.get("feature_count") != STRATEGY_FEATURE_COUNT
            or tuple(payload.get("feature_names", ())) != STRATEGY_FEATURE_NAMES
        ):
            raise ValueError("checkpoint is not a compatible hybrid strategy model")
        hidden = int(payload["hidden"])
        depth = int(payload["depth"])
        layers: list[nn.Module] = [
            nn.Linear(STRATEGY_FEATURE_COUNT, hidden), nn.ReLU()
        ]
        for _ in range(depth - 1):
            layers.extend((nn.Linear(hidden, hidden), nn.ReLU()))
        layers.append(nn.Linear(hidden, 1))
        self._torch = torch
        self._model = nn.Sequential(*layers)
        self._model.load_state_dict(payload["model_state"])
        self._model.eval()

    def scores(
        self, features: tuple[tuple[float, ...], ...]
    ) -> tuple[float, ...]:
        """Score a variable-sized legal action set."""
        if not features:
            return ()
        if any(len(candidate) != STRATEGY_FEATURE_COUNT for candidate in features):
            raise ValueError("candidate has the wrong strategy feature width")
        tensor = self._torch.tensor(features, dtype=self._torch.float32)
        with self._torch.no_grad():
            values = self._model(tensor).squeeze(-1)
        return tuple(float(value) for value in values.tolist())

    def step(self, value: Projector | ProjectorSum) -> ProjectorSum:
        """Rank and apply one exact macro action."""
        return ranked_strategy_step(value, self.scores)


def strategy_candidates(
    value: Projector | ProjectorSum,
) -> tuple[StrategyCandidate, ...]:
    """Enumerate every exact resolver macro across all surviving terms.

    Anchor size is deliberately ``|D(S)| + |D(A)|``.  Shared lines therefore
    contribute once to each operator, matching the author's hand strategy.
    """
    current = value if isinstance(value, ProjectorSum) else ProjectorSum((value,))
    raw: list[StrategyCandidate] = []
    for term_index, (projector, _coefficient) in enumerate(current):
        term_weight = _log_expansion_weight(projector)
        for target in find_sa_targets(projector):
            symmetriser = projector.nodes[target.symmetriser]
            antisymmetriser = projector.nodes[target.antisymmetriser]
            additive_size = len(symmetriser.support) + len(antisymmetriser.support)
            shared_size = len(symmetriser.support & antisymmetriser.support)
            for rewrite in rewrite_candidates(projector, target, "resolver"):
                obstruction = mediator_obstruction(
                    projector, target, rewrite.node
                )
                features = (
                    term_weight / 128.0,
                    additive_size / 64.0,
                    max(len(symmetriser.support), len(antisymmetriser.support)) / 32.0,
                    min(len(symmetriser.support), len(antisymmetriser.support)) / 32.0,
                    shared_size / 32.0,
                    target.support_union_size / 64.0,
                    len(target.direct_paths) / 8.0,
                    len(target.potential_paths) / 8.0,
                    min(len(path.intervening_nodes) for path in target.potential_paths)
                    / 32.0,
                    sum(len(path.intervening_nodes) for path in target.potential_paths)
                    / 64.0,
                    len(projector.nodes[rewrite.node].support) / 32.0,
                    obstruction.other_blockers / 32.0,
                    obstruction.shared_domain_total / 64.0,
                    obstruction.shared_domain_max / 32.0,
                    obstruction.farthest_anchor_distance / 32.0,
                    obstruction.anchor_distance_total / 64.0,
                    obstruction.anchor_distance_imbalance / 32.0,
                    obstruction.path_multiplicity / 8.0,
                    *rewrite.features,
                )
                if len(features) != STRATEGY_FEATURE_COUNT:
                    raise AssertionError("hybrid strategy feature count drifted")
                # The score formalizes the user's staged procedure.  Outcome
                # quality only breaks ties after anchors and mediators.
                oracle_score = (
                    -additive_size,
                    *obstruction.rank,
                    *rewrite.oracle_score,
                )
                raw.append(StrategyCandidate(
                    term_index,
                    projector,
                    target,
                    rewrite,
                    obstruction,
                    features,
                    oracle_score,
                ))
    return tuple(sorted(raw, key=_candidate_key))


def mediator_obstruction(
    projector: Projector, target: SATarget, node_index: int
) -> MediatorObstruction:
    """Measure how much other S/A structure hides one proposed mediator."""
    profiles: list[tuple[tuple[int, ...], MediatorObstruction]] = []
    containing = [
        path for path in target.potential_paths
        if node_index in path.intervening_nodes
    ]
    for path in containing:
        position = path.intervening_nodes.index(node_index)
        source_distance = position + 1
        target_distance = len(path.intervening_nodes) - position
        other_nodes = tuple(
            index for index in path.intervening_nodes if index != node_index
        )
        support = projector.nodes[node_index].support
        overlaps = [
            len(support & projector.nodes[index].support)
            for index in other_nodes
        ]
        profile = MediatorObstruction(
            other_blockers=len(other_nodes),
            shared_domain_total=sum(overlaps),
            shared_domain_max=max(overlaps, default=0),
            farthest_anchor_distance=max(source_distance, target_distance),
            anchor_distance_total=source_distance + target_distance,
            anchor_distance_imbalance=abs(source_distance - target_distance),
            path_multiplicity=len(containing),
        )
        profiles.append((profile.rank, profile))
    if not profiles:
        raise ValueError("mediator is not on an obstructed target path")
    return min(profiles, key=lambda item: item[0])[1]


def apply_strategy_candidate(
    value: Projector | ProjectorSum, candidate: StrategyCandidate
) -> ProjectorSum:
    """Apply a previously enumerated macro while preserving exact coefficients."""
    current = value if isinstance(value, ProjectorSum) else ProjectorSum((value,))
    terms = list(current)
    if not 0 <= candidate.term_index < len(terms):
        raise ValueError("candidate term is not present in this state")
    projector, coefficient = terms[candidate.term_index]
    if projector != candidate.projector:
        raise ValueError("candidate was generated for a different state")
    terms.pop(candidate.term_index)
    return ProjectorSum((
        *terms,
        *((child, coefficient * factor) for child, factor in candidate.result),
    ))


def heuristic_strategy_step(value: Projector | ProjectorSum) -> ProjectorSum:
    """Apply the best candidate under the transparent human-inspired oracle."""
    candidates = strategy_candidates(value)
    if not candidates:
        return value if isinstance(value, ProjectorSum) else ProjectorSum((value,))
    selected = min(candidates, key=lambda candidate: candidate.oracle_score)
    return apply_strategy_candidate(value, selected)


def ranked_strategy_step(
    value: Projector | ProjectorSum,
    scorer: Callable[[tuple[tuple[float, ...], ...]], Sequence[float]],
) -> ProjectorSum:
    """Apply the legal candidate assigned the greatest score by ``scorer``."""
    candidates = strategy_candidates(value)
    if not candidates:
        return value if isinstance(value, ProjectorSum) else ProjectorSum((value,))
    scores = tuple(float(score) for score in scorer(tuple(
        candidate.features for candidate in candidates
    )))
    if len(scores) != len(candidates):
        raise ValueError("strategy scorer returned the wrong number of scores")
    selected = max(
        range(len(candidates)),
        key=lambda index: (
            scores[index],
            tuple(-x for x in candidates[index].oracle_score),
        ),
    )
    return apply_strategy_candidate(value, candidates[selected])


def append_strategy_preference(
    path: str | PathLike[str],
    candidates: Sequence[StrategyCandidate],
    preferred: int | Sequence[int],
) -> None:
    """Atomically append one human ranking decision as model-ready features."""
    if not candidates:
        raise ValueError("a preference decision needs at least one candidate")
    choices = (preferred,) if isinstance(preferred, int) else tuple(preferred)
    if not choices or any(index < 0 or index >= len(candidates) for index in choices):
        raise ValueError("preferred candidate index is outside the candidate list")
    destination = Path(path)
    dataset = _read_preference_dataset(destination)
    dataset["examples"].append({
        "features": [list(candidate.features) for candidate in candidates],
        "preferred": sorted(set(choices)),
        "actions": [
            {
                "term": candidate.term_index,
                "anchors": [
                    candidate.target.symmetriser,
                    candidate.target.antisymmetriser,
                ],
                "mediator": candidate.node,
                "side": candidate.rewrite.side,
                "rearrangements": candidate.rewrite.rearrangements,
            }
            for candidate in candidates
        ],
    })
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(
        json.dumps(dataset, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)


def load_strategy_preferences(
    path: str | PathLike[str],
) -> tuple[PreferenceGroup, ...]:
    """Load and validate human ranking decisions."""
    result = []
    for example_index, example in enumerate(
        _read_preference_dataset(Path(path))["examples"]
    ):
        try:
            features = tuple(
                tuple(float(value) for value in candidate)
                for candidate in example["features"]
            )
            preferred = tuple(int(index) for index in example["preferred"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"strategy preference {example_index} is malformed"
            ) from exc
        if not features or any(
            len(candidate) != STRATEGY_FEATURE_COUNT for candidate in features
        ):
            raise ValueError(
                f"strategy preference {example_index} has incompatible features"
            )
        if not preferred or any(
            index < 0 or index >= len(features) for index in preferred
        ):
            raise ValueError(
                f"strategy preference {example_index} has invalid choices"
            )
        result.append(PreferenceGroup(features, preferred))
    return tuple(result)


def _read_preference_dataset(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "format": DATASET_FORMAT,
            "version": DATASET_VERSION,
            "feature_names": list(STRATEGY_FEATURE_NAMES),
            "examples": [],
        }
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("format") != DATASET_FORMAT
        or value.get("version") != DATASET_VERSION
        or value.get("feature_names") != list(STRATEGY_FEATURE_NAMES)
        or not isinstance(value.get("examples"), list)
    ):
        raise ValueError(f"{path} is not a compatible strategy-preference dataset")
    return value


def _log_expansion_weight(projector: Projector) -> float:
    return sum(lgamma(len(node.support) + 1) for node in projector.nodes)


def _candidate_key(candidate: StrategyCandidate) -> tuple[object, ...]:
    return (
        candidate.term_index,
        candidate.target.symmetriser,
        candidate.target.antisymmetriser,
        candidate.node,
        candidate.rewrite.side,
        candidate.rewrite.rearrangements,
        repr(candidate.result),
    )


__all__ = [
    "DATASET_FORMAT",
    "DATASET_VERSION",
    "LearnedHybridStrategy",
    "MediatorObstruction",
    "PreferenceGroup",
    "STRATEGY_FEATURE_COUNT",
    "STRATEGY_FEATURE_NAMES",
    "StrategyCandidate",
    "append_strategy_preference",
    "apply_strategy_candidate",
    "heuristic_strategy_step",
    "load_strategy_preferences",
    "mediator_obstruction",
    "ranked_strategy_step",
    "strategy_candidates",
]
