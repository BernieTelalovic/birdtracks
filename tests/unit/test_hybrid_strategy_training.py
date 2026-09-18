"""Tests for full anchor–mediator–rewrite policy infrastructure."""

import json

import pytest

from birdtracks import (
    Antisymmetriser,
    Projector,
    ProjectorSum,
    Symmetriser,
    append_strategy_preference,
    apply_strategy_candidate,
    heuristic_strategy_step,
    load_strategy_preferences,
    strategy_candidates,
)
from birdtracks.projectors.hybrid_strategy_training import (
    STRATEGY_FEATURE_COUNT,
    STRATEGY_FEATURE_NAMES,
)


def competing_targets() -> Projector:
    """Two targets where support union and additive domain disagree."""
    return Projector([
        # Additive size 8, union size 4: this must be preferred.
        Symmetriser((1, 2, 3, 4)),
        Symmetriser((2, 8)),
        Symmetriser((3, 9)),
        Symmetriser((4, 10)),
        Antisymmetriser((1, 2, 3, 4)),
        # Additive size 7, union size 5: the old union rule preferred this.
        Symmetriser((20, 21, 22)),
        Symmetriser((21, 30)),
        Antisymmetriser((20, 21, 23, 24)),
    ])


def corridor() -> Projector:
    return Projector([
        Symmetriser((1, 2)),
        Symmetriser((2, 3)),
        Antisymmetriser((1, 2)),
    ])


def test_strategy_oracle_uses_additive_anchor_domain_size() -> None:
    candidates = strategy_candidates(competing_targets())

    assert candidates
    assert all(len(candidate.features) == STRATEGY_FEATURE_COUNT
               for candidate in candidates)
    best = min(candidates, key=lambda candidate: candidate.oracle_score)
    assert best.target.nodes == (0, 4)
    assert best.features[
        STRATEGY_FEATURE_NAMES.index("anchor_additive_domain_size")
    ] == pytest.approx(8 / 64)
    assert best.target.support_union_size == 4


def test_every_strategy_action_is_exact_and_topology_safe() -> None:
    projector = corridor()

    for candidate in strategy_candidates(projector):
        result = apply_strategy_candidate(projector, candidate)
        assert result.collapse() == projector.collapse()


def test_strategy_action_preserves_outer_term_coefficient() -> None:
    projector = corridor()
    untouched = Projector([Symmetriser((100, 101))])
    value = ProjectorSum(((projector, 3), (untouched, 5)))
    candidate = next(
        candidate for candidate in strategy_candidates(value)
        if candidate.projector == projector
    )

    result = apply_strategy_candidate(value, candidate)

    assert result.collapse() == value.collapse()
    assert result.coefficient(untouched) == 5


def test_heuristic_step_uses_the_same_exact_candidate_layer() -> None:
    projector = corridor()

    result = heuristic_strategy_step(projector)

    assert result != ProjectorSum((projector,))
    assert result.collapse() == projector.collapse()


def test_preference_dataset_round_trip(tmp_path) -> None:
    candidates = strategy_candidates(competing_targets())
    path = tmp_path / "preferences.json"

    append_strategy_preference(path, candidates, (0, 1))
    loaded = load_strategy_preferences(path)

    assert len(loaded) == 1
    assert loaded[0].preferred == (0, 1)
    assert loaded[0].features == tuple(
        candidate.features for candidate in candidates
    )
    saved = json.loads(path.read_text())
    assert saved["feature_names"] == list(STRATEGY_FEATURE_NAMES)
    assert saved["examples"][0]["actions"][0] == {
        "anchors": [candidates[0].target.symmetriser,
                    candidates[0].target.antisymmetriser],
        "mediator": candidates[0].node,
        "rearrangements": candidates[0].rewrite.rearrangements,
        "side": candidates[0].rewrite.side,
        "term": candidates[0].term_index,
    }


def test_preference_loader_rejects_feature_schema_drift(tmp_path) -> None:
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps({
        "format": "birdtracks-hybrid-strategy-preferences",
        "version": 1,
        "feature_names": ["old-feature"],
        "examples": [],
    }))

    with pytest.raises(ValueError, match="not a compatible"):
        load_strategy_preferences(path)
