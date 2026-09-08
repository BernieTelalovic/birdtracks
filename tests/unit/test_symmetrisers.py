"""Unit tests for symbolic symmetrisers and antisymmetrisers."""

import pickle
from fractions import Fraction

import pytest

from birdtracks import Antisymmetriser, Permutation, PermutationSum, Symmetriser


def test_symmetriser_collapses_to_normalised_permutations_of_support() -> None:
    projector = Symmetriser({1, 2, 4})
    collapsed = projector.collapse()

    expected = {
        Permutation.identity(): Fraction(1, 6),
        Permutation.from_cycle(1, 2): Fraction(1, 6),
        Permutation.from_cycle(1, 4): Fraction(1, 6),
        Permutation.from_cycle(2, 4): Fraction(1, 6),
        Permutation.from_cycle(1, 2, 4): Fraction(1, 6),
        Permutation.from_cycle(1, 4, 2): Fraction(1, 6),
    }

    assert collapsed.terms == expected


def test_antisymmetriser_uses_permutation_parity_for_signs() -> None:
    collapsed = Antisymmetriser((1, 2, 4)).collapse()

    expected = {
        Permutation.identity(): Fraction(1, 6),
        Permutation.from_cycle(1, 2): Fraction(-1, 6),
        Permutation.from_cycle(1, 4): Fraction(-1, 6),
        Permutation.from_cycle(2, 4): Fraction(-1, 6),
        Permutation.from_cycle(1, 2, 4): Fraction(1, 6),
        Permutation.from_cycle(1, 4, 2): Fraction(1, 6),
    }

    assert collapsed.terms == expected


@pytest.mark.parametrize("projector_type", [Symmetriser, Antisymmetriser])
def test_empty_and_single_line_projectors_collapse_to_identity(projector_type: type) -> None:
    identity_sum = PermutationSum.from_permutation(Permutation.identity())
    assert projector_type([]).collapse() == identity_sum
    assert projector_type([7]).collapse() == identity_sum


def test_user_order_is_preserved_but_does_not_change_value_semantics() -> None:
    left = Symmetriser([4, 1, 2])
    right = Symmetriser((1, 2, 4))

    assert left.support == frozenset({1, 2, 4})
    assert left.labels == (4, 1, 2)
    assert left == right
    assert hash(left) == hash(right)
    assert left != Antisymmetriser([1, 2, 4])
    assert pickle.loads(pickle.dumps(left)) == left


def test_unordered_support_gets_a_deterministic_order() -> None:
    assert Symmetriser({4, 1, 2}).labels == (1, 2, 4)


def test_antisymmetriser_collapse_is_independent_of_stored_order() -> None:
    assert Antisymmetriser((4, 1, 2)).collapse() == Antisymmetriser(
        (1, 2, 4)
    ).collapse()


@pytest.mark.parametrize("support", [[1, 1], [True], [1.0], ["1"]])
def test_invalid_support_is_rejected(support: list[object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        Symmetriser(support)  # type: ignore[arg-type]


def test_non_collection_support_is_rejected() -> None:
    with pytest.raises(TypeError, match="collection"):
        Symmetriser(1)  # type: ignore[arg-type]
