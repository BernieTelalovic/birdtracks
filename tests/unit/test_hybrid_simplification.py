"""Tests for exact hybrid S/A target discovery and local rewrites."""

from birdtracks import Antisymmetriser, Projector, Symmetriser
from birdtracks.projectors.hybrid_simplification import (
    collapse_resolved_sa_pair,
    find_sa_exposure_targets,
    find_sa_targets,
    hybrid_collapse,
    hybrid_simplify_step,
    resolve_sa_target_step,
    sa_pair_ready_to_collapse,
)


def corridor(*, reversed_types: bool = False) -> Projector:
    outer = (
        (Antisymmetriser, Symmetriser)
        if reversed_types
        else (Symmetriser, Antisymmetriser)
    )
    return Projector([
        outer[0]((1, 2)),
        Symmetriser((2, 3)),
        outer[1]((1, 2)),
    ])


def test_finds_direct_plus_obstructed_strand_in_both_type_orders() -> None:
    forward = find_sa_targets(corridor())
    reversed_pair = find_sa_targets(corridor(reversed_types=True))

    assert len(forward) == len(reversed_pair) == 1
    assert forward[0].nodes == (0, 2)
    assert reversed_pair[0].nodes == (2, 0)
    assert forward[0].support_union == frozenset({1, 2})
    assert len(forward[0].direct_paths) == 1
    assert forward[0].potential_paths[0].intervening_nodes == (1,)


def test_targets_rank_by_support_union_cardinality() -> None:
    projector = Projector([
        Symmetriser((1, 2)),
        Symmetriser((2, 9)),
        Antisymmetriser((1, 2)),
        Symmetriser((3, 4, 5)),
        Symmetriser((4, 8)),
        Antisymmetriser((3, 4, 6)),
    ])

    targets = find_sa_targets(projector)

    assert [target.support_union_size for target in targets] == [4, 2]


def test_resolver_step_is_exact_and_removes_zero_branch() -> None:
    projector = corridor()
    result = resolve_sa_target_step(projector, find_sa_targets(projector)[0])

    assert result.collapse() == projector.collapse()
    assert len(result) == 1
    assert all(not find_sa_targets(term) for term, _ in result)


def test_hybrid_step_resolves_an_a_s_target_exactly() -> None:
    projector = corridor(reversed_types=True)

    result = hybrid_simplify_step(projector)

    assert result.collapse() == projector.collapse()
    assert result != projector


def test_hybrid_collapse_returns_the_exact_full_permutation_sum() -> None:
    projector = corridor()

    assert hybrid_collapse(projector, maximum_steps=8) == projector.collapse()


def test_exposure_target_has_only_obstructed_paths_and_a_layer_between() -> None:
    projector = Projector([
        Symmetriser((1, 2)),
        Symmetriser((1, 3)),
        Antisymmetriser((2, 4)),
        Antisymmetriser((1, 2)),
    ])

    target, = find_sa_exposure_targets(projector)

    assert target.nodes == (0, 3)
    assert len(target.obstructed_paths) == 2
    assert all(not path.direct for path in target.obstructed_paths)


def test_adjacent_resolved_pair_is_fully_collapsed_then_simplified() -> None:
    projector = Projector([
        Symmetriser((1, 2)),
        Antisymmetriser((2, 3)),
    ])

    assert sa_pair_ready_to_collapse(projector, 0, 1)
    result = collapse_resolved_sa_pair(projector, 0, 1)

    assert result.collapse() == projector.collapse()
    assert all(
        not any(isinstance(node, (Symmetriser, Antisymmetriser))
                for node in term.nodes)
        for term, _coefficient in result
    )
