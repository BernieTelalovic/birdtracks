"""Tests for variable-length target-conditioned policy training states."""

from random import Random

from birdtracks import random_exposure_problem, random_resolver_problem
from birdtracks.projectors.hybrid_policy_training import (
    FEATURE_COUNT,
    oracle_trajectory,
    rewrite_candidates,
)


def test_resolver_candidates_are_exact_and_fixed_width() -> None:
    projector, target = random_resolver_problem(
        Random(12), minimum_lines=4, maximum_lines=4,
        minimum_layers=3, maximum_layers=3,
    )

    candidates = rewrite_candidates(projector, target, "resolver")

    assert candidates
    assert all(len(candidate.features) == FEATURE_COUNT for candidate in candidates)
    assert all(candidate.result.collapse() == projector.collapse()
               for candidate in candidates)


def test_exposer_oracle_can_train_on_multiple_successive_states() -> None:
    projector, target = random_exposure_problem(
        Random(2), minimum_lines=4, maximum_lines=4,
        minimum_layers=3, maximum_layers=3,
    )

    trajectory = oracle_trajectory(
        projector, target, "exposer", maximum_steps=8
    )

    assert len(trajectory) >= 2
    for candidates, preferred in trajectory:
        assert candidates
        assert preferred
        best = min(candidate.oracle_score for candidate in candidates)
        assert all(candidates[index].oracle_score == best for index in preferred)


def test_episode_limit_is_only_a_safety_cap() -> None:
    projector, target = random_exposure_problem(
        Random(2), minimum_lines=4, maximum_lines=4,
        minimum_layers=3, maximum_layers=3,
    )

    trajectory = oracle_trajectory(
        projector, target, "exposer", maximum_steps=1
    )

    assert len(trajectory) == 1
