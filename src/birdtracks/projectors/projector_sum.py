"""Formal exact linear combinations of projector diagrams."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from fractions import Fraction
from os import PathLike
from types import MappingProxyType

from birdtracks.linear_combinations import PermutationSum, PolynomialPermutationSum
from birdtracks.linear_combinations.coefficients import require_coefficient

from .projector import Projector


class ProjectorSum:
    """An immutable formal sum of independent projector diagrams.

    Supports need not match: addition does not connect any strands. Equal
    diagrams are collected with exact rational coefficients.
    """

    __slots__ = (
        "_terms",
        "_lookup",
        "_display_terms",
        "_display_lookup",
        "_hash",
    )

    def __init__(
        self,
        terms: Mapping[Projector, int | float | Fraction]
        | Iterable[Projector | tuple[Projector, int | float | Fraction]] = (),
    ) -> None:
        source = terms.items() if isinstance(terms, Mapping) else terms
        combined: dict[Projector, Fraction] = {}
        for term in source:
            if isinstance(term, Projector):
                projector, coefficient = term, Fraction(1)
            else:
                try:
                    projector, coefficient = term
                except (TypeError, ValueError) as exc:
                    raise TypeError(
                        "terms must be Projectors or (Projector, coefficient) pairs"
                    ) from exc
            if not isinstance(projector, Projector):
                raise TypeError("term keys must be Projector objects")
            exact = (
                require_coefficient(coefficient)
                * projector.canonical_value_coefficient
            )
            if not exact:
                continue
            canonical = projector / projector.canonical_value_coefficient
            combined[canonical] = combined.get(canonical, Fraction()) + exact

        self._terms = tuple(
            sorted(
                (
                    (projector, coefficient)
                    for projector, coefficient in combined.items()
                    if coefficient
                ),
                key=lambda term: repr(term[0]),
            )
        )
        self._lookup = MappingProxyType(dict(self._terms))
        self._display_terms = tuple(
            (
                projector / projector.coefficient,
                coefficient * projector.coefficient,
            )
            for projector, coefficient in self._terms
        )
        self._display_lookup = MappingProxyType(dict(self._display_terms))
        self._hash = hash(frozenset(self._terms))

    @property
    def terms(self) -> Mapping[Projector, Fraction]:
        """Terms with each projector normalized to displayed coefficient one.

        Canonical representatives may carry an orientation sign internally.
        Public terms move that sign into the scalar prefactor so printed and
        rendered sums never conceal it inside the projector object.
        """
        return self._display_lookup

    def coefficient(self, projector: Projector) -> Fraction:
        if not isinstance(projector, Projector):
            raise TypeError("coefficient expects a Projector object")
        if not projector.canonical_value_coefficient:
            return Fraction()
        canonical = projector / projector.canonical_value_coefficient
        return (
            self._lookup.get(canonical, Fraction())
            / projector.canonical_value_coefficient
        )

    def items(self) -> Iterator[tuple[Projector, Fraction]]:
        return iter(self._display_terms)

    def collapse(
        self, *, dimension: int | float | Fraction | None = None
    ) -> PermutationSum | PolynomialPermutationSum:
        collapsed = [
            coefficient * projector.collapse(dimension=dimension)
            for projector, coefficient in self._terms
        ]
        if not collapsed:
            return PermutationSum.zero()
        if any(isinstance(value, PolynomialPermutationSum) for value in collapsed):
            return sum(collapsed, PolynomialPermutationSum({}))
        return sum(collapsed, PermutationSum.zero())

    def trace(self) -> ProjectorSum:
        return ProjectorSum(
            (projector.trace(), coefficient)
            for projector, coefficient in self._terms
        )

    def evaluate(
        self,
        *,
        style: str | PathLike[str] | None = None,
        session: str | PathLike[str] | None = None,
        detangler: str | PathLike[str] | object | None = None,
    ) -> object:
        """Open this exact sum in an interactive evaluation canvas."""
        if session is not None:
            from .canvas_session import (
                ProjectorCanvasSession,
                _resolve_canvas_session_path,
            )

            if _resolve_canvas_session_path(session).exists():
                return ProjectorCanvasSession.load(session).open(
                    style=style, detangler=detangler
                )
        from .widget import projector_sum_widget

        return projector_sum_widget(
            self, style=style, session=session, detangler=detangler
        )

    def __add__(self, other: object) -> ProjectorSum:
        promoted = _promote_addend(other)
        if promoted is NotImplemented:
            return NotImplemented
        return ProjectorSum((*self._terms, *promoted._terms))

    def __radd__(self, other: object) -> ProjectorSum:
        if other == 0 and type(other) is int:
            return self
        return self.__add__(other)

    def __neg__(self) -> ProjectorSum:
        return ProjectorSum(
            (projector, -coefficient)
            for projector, coefficient in self._terms
        )

    def __sub__(self, other: object) -> ProjectorSum:
        promoted = _promote_addend(other)
        if promoted is NotImplemented:
            return NotImplemented
        return self + (-promoted)

    def __rsub__(self, other: object) -> ProjectorSum:
        promoted = _promote_addend(other)
        if promoted is NotImplemented:
            return NotImplemented
        return promoted - self

    def __mul__(self, scalar: object) -> ProjectorSum:
        try:
            exact = require_coefficient(scalar)
        except TypeError:
            return NotImplemented
        return ProjectorSum(
            (projector, coefficient * exact)
            for projector, coefficient in self._terms
        )

    def __rmul__(self, scalar: object) -> ProjectorSum:
        return self.__mul__(scalar)

    def __iter__(self) -> Iterator[tuple[Projector, Fraction]]:
        return self.items()

    def __len__(self) -> int:
        return len(self._terms)

    def __bool__(self) -> bool:
        return bool(self._terms)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ProjectorSum) and self._lookup == other._lookup

    def __hash__(self) -> int:
        return self._hash

    def __repr__(self) -> str:
        return f"ProjectorSum({dict(self._display_terms)!r})"


def _promote_addend(value: object) -> ProjectorSum | type(NotImplemented):
    if isinstance(value, ProjectorSum):
        return value
    if isinstance(value, Projector):
        return ProjectorSum((value,))
    return NotImplemented


__all__ = ["ProjectorSum"]
