"""Tests for deterministic plain-text and LaTeX permutation rendering."""

from fractions import Fraction

import pytest

from birdtracks import (
    Permutation,
    PermutationSum,
    cycle_notation,
    get_display_notation,
    latex,
    set_display_notation,
)


def test_identity_rendering() -> None:
    identity = Permutation.identity()
    assert cycle_notation(identity) == "e"
    assert latex(identity) == r"\mathrm{id}"
    assert identity._repr_latex_() == r"$\mathrm{id}$"


def test_disjoint_cycles_render_deterministically() -> None:
    permutation = Permutation.from_cycles((5, 4), (3, 1, 2))
    assert permutation.cycles() == ((1, 2, 3), (4, 5))
    assert cycle_notation(permutation) == "(1 2 3)(4 5)"
    expected = r"\left(1\,2\,3\right)\left(4\,5\right)"
    assert latex(permutation) == expected
    assert permutation._repr_latex_() == "$" + expected + "$"


def test_signed_and_arbitrary_precision_labels_are_preserved() -> None:
    huge = 1 << 1000
    permutation = Permutation.from_cycle(-huge, 0, huge)
    assert cycle_notation(permutation) == f"({-huge} 0 {huge})"
    assert latex(permutation) == rf"\left({-huge}\,0\,{huge}\right)"


def test_permutation_sum_renders_coefficients_and_signs() -> None:
    identity = Permutation.identity()
    p = Permutation.from_cycle(1, 2)
    q = Permutation.from_cycle(2, 3)
    value = PermutationSum(
        ((identity, -2), (p, Fraction(1, 3)), (q, -1))
    )

    assert cycle_notation(value) == "-2 e + 1/3 (1 2) - (2 3)"
    expected = (
        r"-2\,\mathrm{id} + \frac{1}{3}\,\left(1\,2\right)"
        r" - \left(2\,3\right)"
    )
    assert latex(value) == expected
    assert value._repr_latex_() == "$" + expected + "$"


def test_zero_sum_rendering() -> None:
    assert cycle_notation(PermutationSum.zero()) == "0"
    assert latex(PermutationSum.zero()) == "0"


def test_display_notation_setting_is_shared() -> None:
    set_display_notation("cycles")
    assert get_display_notation() == "cycles"
    with pytest.raises(ValueError, match="unknown display notation"):
        set_display_notation("birdtracks")
    assert get_display_notation() == "cycles"


@pytest.mark.parametrize("renderer", [cycle_notation, latex])
def test_renderer_rejects_non_permutations(renderer: object) -> None:
    with pytest.raises(TypeError):
        renderer({1: 2})  # type: ignore[operator]
