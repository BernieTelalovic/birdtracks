"""Exact polynomials in the symbolic representation dimension."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from fractions import Fraction
from types import MappingProxyType

from birdtracks.permutations import Permutation

from .coefficients import require_coefficient
from .permutation_sum import PermutationSum


class DimensionPolynomial:
    """An immutable sparse polynomial in ``N`` with rational coefficients."""

    __slots__ = ("_terms", "_lookup", "_hash")

    def __init__(
        self, coefficients: Mapping[int, int | float | Fraction] | None = None
    ) -> None:
        checked: dict[int, Fraction] = {}
        for power, coefficient in (coefficients or {}).items():
            if isinstance(power, bool) or not isinstance(power, int):
                raise TypeError("polynomial powers must be integers")
            if power < 0:
                raise ValueError("polynomial powers cannot be negative")
            exact = require_coefficient(coefficient)
            if exact:
                checked[power] = exact
        self._terms = tuple(sorted(checked.items()))
        self._lookup = MappingProxyType(dict(self._terms))
        self._hash = hash(self._terms)

    @property
    def coefficients(self) -> Mapping[int, Fraction]:
        return self._lookup

    def coefficient(self, power: int) -> Fraction:
        return self._lookup.get(power, Fraction())

    def evaluate(self, dimension: int | float | Fraction) -> Fraction:
        value = require_coefficient(dimension)
        return sum(
            (coefficient * value**power for power, coefficient in self._terms),
            Fraction(),
        )

    def __iter__(self) -> Iterator[tuple[int, Fraction]]:
        return iter(self._terms)

    def __bool__(self) -> bool:
        return bool(self._terms)

    def __add__(self, other: object) -> DimensionPolynomial:
        if not isinstance(other, DimensionPolynomial):
            return NotImplemented
        combined = dict(self._terms)
        for power, coefficient in other._terms:
            combined[power] = combined.get(power, Fraction()) + coefficient
        return DimensionPolynomial(combined)

    def __neg__(self) -> DimensionPolynomial:
        return DimensionPolynomial(
            {power: -coefficient for power, coefficient in self._terms}
        )

    def __sub__(self, other: object) -> DimensionPolynomial:
        if not isinstance(other, DimensionPolynomial):
            return NotImplemented
        return self + (-other)

    def __mul__(self, other: object) -> DimensionPolynomial:
        if isinstance(other, DimensionPolynomial):
            coefficients: dict[int, Fraction] = {}
            for left_power, left_coefficient in self._terms:
                for right_power, right_coefficient in other._terms:
                    power = left_power + right_power
                    coefficients[power] = (
                        coefficients.get(power, Fraction())
                        + left_coefficient * right_coefficient
                    )
            return DimensionPolynomial(coefficients)
        try:
            exact = require_coefficient(other)
        except TypeError:
            return NotImplemented
        return DimensionPolynomial(
            {power: coefficient * exact for power, coefficient in self._terms}
        )

    def __rmul__(self, other: object) -> DimensionPolynomial:
        return self.__mul__(other)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, DimensionPolynomial) and self._terms == other._terms

    def __hash__(self) -> int:
        return self._hash

    def __repr__(self) -> str:
        return _polynomial_plain(self)

    def __str__(self) -> str:
        return _polynomial_plain(self)

    def _repr_latex_(self) -> str:
        return "$" + _polynomial_latex(self) + "$"


def _polynomial_plain(polynomial: DimensionPolynomial) -> str:
    """Render an exact polynomial for terminals in descending degree order."""
    if not polynomial:
        return "0"
    parts: list[str] = []
    for power, coefficient in reversed(tuple(polynomial)):
        magnitude = abs(coefficient)
        if parts:
            parts.append(" - " if coefficient < 0 else " + ")
        elif coefficient < 0:
            parts.append("-")
        scalar = (
            str(magnitude.numerator)
            if magnitude.denominator == 1
            else f"({magnitude.numerator}/{magnitude.denominator})"
        )
        variable = "" if power == 0 else " N"
        if power > 1:
            variable += f" ** {power}"
        parts.append(scalar + variable)
    return "".join(parts)


class PolynomialPermutationSum:
    """An immutable permutation sum with dimension-polynomial coefficients."""

    __slots__ = ("_terms", "_lookup", "_hash")

    def __init__(
        self,
        terms: Mapping[Permutation, DimensionPolynomial]
        | Iterable[tuple[Permutation, DimensionPolynomial]],
    ) -> None:
        source = terms.items() if isinstance(terms, Mapping) else terms
        combined: dict[Permutation, DimensionPolynomial] = {}
        for permutation, coefficient in source:
            if not isinstance(permutation, Permutation):
                raise TypeError("term keys must be Permutation objects")
            if not isinstance(coefficient, DimensionPolynomial):
                raise TypeError("term coefficients must be DimensionPolynomial objects")
            combined[permutation] = combined.get(
                permutation, DimensionPolynomial()
            ) + coefficient
        checked = [
            (permutation, coefficient)
            for permutation, coefficient in combined.items()
            if coefficient
        ]
        self._terms = tuple(sorted(checked, key=lambda term: tuple(term[0])))
        self._lookup = MappingProxyType(dict(self._terms))
        self._hash = hash(self._terms)

    @property
    def terms(self) -> Mapping[Permutation, DimensionPolynomial]:
        return self._lookup

    def coefficient(self, permutation: Permutation) -> DimensionPolynomial:
        if not isinstance(permutation, Permutation):
            raise TypeError("coefficient expects a Permutation object")
        return self._lookup.get(permutation, DimensionPolynomial())

    def items(self) -> Iterator[tuple[Permutation, DimensionPolynomial]]:
        return iter(self._terms)

    def evaluate(self, dimension: int | float | Fraction) -> PermutationSum:
        """Evaluate ``N`` exactly and return an ordinary permutation sum."""
        return PermutationSum(
            (permutation, coefficient.evaluate(dimension))
            for permutation, coefficient in self._terms
        )

    def __add__(self, other: object) -> PolynomialPermutationSum:
        promoted = _promote_polynomial_sum(other)
        if promoted is NotImplemented:
            return NotImplemented
        return PolynomialPermutationSum((*self._terms, *promoted._terms))

    def __radd__(self, other: object) -> PolynomialPermutationSum:
        if other == 0 and type(other) is int:
            return self
        return self.__add__(other)

    def __neg__(self) -> PolynomialPermutationSum:
        return PolynomialPermutationSum(
            (permutation, -coefficient)
            for permutation, coefficient in self._terms
        )

    def __sub__(self, other: object) -> PolynomialPermutationSum:
        promoted = _promote_polynomial_sum(other)
        if promoted is NotImplemented:
            return NotImplemented
        return self + (-promoted)

    def __mul__(self, scalar: object) -> PolynomialPermutationSum:
        try:
            exact = require_coefficient(scalar)
        except TypeError:
            return NotImplemented
        return PolynomialPermutationSum(
            (permutation, coefficient * exact)
            for permutation, coefficient in self._terms
        )

    def __rmul__(self, scalar: object) -> PolynomialPermutationSum:
        return self.__mul__(scalar)

    def __iter__(self) -> Iterator[tuple[Permutation, DimensionPolynomial]]:
        return self.items()

    def __len__(self) -> int:
        return len(self._terms)

    def __bool__(self) -> bool:
        return bool(self._terms)

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, PolynomialPermutationSum)
            and self._terms == other._terms
        )

    def __hash__(self) -> int:
        return self._hash

    def __repr__(self) -> str:
        return f"PolynomialPermutationSum({dict(self._terms)!r})"

    def _repr_latex_(self) -> str:
        from birdtracks.permutations.rendering import latex

        if not self:
            return "$0$"
        parts = []
        for permutation, coefficient in self._terms:
            polynomial = _polynomial_latex(coefficient)
            parts.append(
                polynomial
                if not permutation
                else rf"\left({polynomial}\right)\,{latex(permutation)}"
            )
        return "$" + " + ".join(parts) + "$"


def _polynomial_latex(polynomial: DimensionPolynomial) -> str:
    if not polynomial:
        return "0"
    parts: list[str] = []
    for power, coefficient in reversed(tuple(polynomial)):
        magnitude = abs(coefficient)
        rational = (
            str(magnitude.numerator)
            if magnitude.denominator == 1
            else rf"\frac{{{magnitude.numerator}}}{{{magnitude.denominator}}}"
        )
        variable = "" if power == 0 else ("N" if power == 1 else rf"N^{{{power}}}")
        body = variable if magnitude == 1 and variable else rational + variable
        if not parts:
            parts.append("-" + body if coefficient < 0 else body)
        else:
            parts.append((" - " if coefficient < 0 else " + ") + body)
    return "".join(parts)


def _promote_polynomial_sum(
    value: object,
) -> PolynomialPermutationSum | type(NotImplemented):
    if isinstance(value, PolynomialPermutationSum):
        return value
    if isinstance(value, PermutationSum):
        return PolynomialPermutationSum(
            (permutation, DimensionPolynomial({0: coefficient}))
            for permutation, coefficient in value
        )
    return NotImplemented


__all__ = ["DimensionPolynomial", "PolynomialPermutationSum"]
