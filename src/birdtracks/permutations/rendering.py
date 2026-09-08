"""Configurable text and LaTeX rendering for permutation algebra values."""

from __future__ import annotations

from collections.abc import Callable
from fractions import Fraction
from typing import TYPE_CHECKING, TypeAlias

from .types import Permutation

if TYPE_CHECKING:
    from birdtracks.linear_combinations import PermutationSum

PermutationExpression: TypeAlias = "Permutation | PermutationSum"
LatexRenderer: TypeAlias = Callable[[PermutationExpression], str]


def _is_permutation_sum(value: object) -> bool:
    from birdtracks.linear_combinations import PermutationSum

    return isinstance(value, PermutationSum)


def cycle_notation(value: PermutationExpression) -> str:
    """Return deterministic cycle notation for a permutation expression."""
    if isinstance(value, Permutation):
        return _permutation_cycle_notation(value)
    if not _is_permutation_sum(value):
        raise TypeError(
            "cycle_notation expects a Permutation or PermutationSum object"
        )
    if not value:
        return "0"
    return _format_sum(
        value, _permutation_cycle_notation, _plain_coefficient, " "
    )


def _permutation_cycle_notation(permutation: Permutation) -> str:
    if not permutation:
        return "e"
    return "".join(
        f"({' '.join(str(label) for label in cycle)})"
        for cycle in permutation.cycles()
    )


def latex(value: PermutationExpression) -> str:
    r"""Return a LaTeX fragment using the globally selected notation.

    The returned string intentionally has no math delimiters, so it can be
    embedded in larger formulas or passed directly to IPython.display.Math.
    """
    if not isinstance(value, Permutation) and not _is_permutation_sum(value):
        raise TypeError("latex expects a Permutation or PermutationSum object")
    return _LATEX_RENDERERS[_display_notation](value)


def set_display_notation(notation: str) -> None:
    """Select the notation used by ``latex`` and Jupyter rich display."""
    if notation not in _LATEX_RENDERERS:
        choices = ", ".join(sorted(_LATEX_RENDERERS))
        raise ValueError(f"unknown display notation {notation!r}; choose {choices}")
    global _display_notation
    _display_notation = notation


def get_display_notation() -> str:
    """Return the notation used by ``latex`` and Jupyter rich display."""
    return _display_notation


def _cycle_latex(value: PermutationExpression) -> str:
    if isinstance(value, Permutation):
        return _permutation_cycle_latex(value)
    if not value:
        return "0"
    return _format_sum(
        value, _permutation_cycle_latex, _latex_coefficient, r"\,"
    )


def _permutation_cycle_latex(permutation: Permutation) -> str:
    if not permutation:
        return r"\mathrm{id}"
    return "".join(
        rf"\left({r'\,'.join(str(label) for label in cycle)}\right)"
        for cycle in permutation.cycles()
    )


def _format_sum(
    value: PermutationSum,
    permutation_renderer: Callable[[Permutation], str],
    coefficient_renderer: Callable[[Fraction], str],
    multiplication_separator: str,
) -> str:
    parts: list[str] = []
    for permutation, coefficient in value.items():
        magnitude = abs(coefficient)
        term = permutation_renderer(permutation)
        if magnitude != 1:
            term = (
                coefficient_renderer(magnitude)
                + multiplication_separator
                + term
            )
        if not parts:
            parts.append("-" + term if coefficient < 0 else term)
        else:
            parts.append((" - " if coefficient < 0 else " + ") + term)
    return "".join(parts)


def _plain_coefficient(coefficient: Fraction) -> str:
    if coefficient.denominator == 1:
        return str(coefficient.numerator)
    return f"{coefficient.numerator}/{coefficient.denominator}"


def _latex_coefficient(coefficient: Fraction) -> str:
    if coefficient.denominator == 1:
        return str(coefficient.numerator)
    return rf"\frac{{{coefficient.numerator}}}{{{coefficient.denominator}}}"


# Adding a notation is deliberately isolated to a renderer entry. The public
# setting and both rich-display methods do not need to change for birdtracks.
_LATEX_RENDERERS: dict[str, LatexRenderer] = {"cycles": _cycle_latex}
_display_notation = "cycles"
