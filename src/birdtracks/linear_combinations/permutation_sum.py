"""Sparse exact linear combinations of permutations."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from fractions import Fraction
from types import MappingProxyType
from typing import ClassVar

from birdtracks.permutations.types import Permutation

from .coefficients import require_coefficient


class PermutationSum:
    """An immutable, canonical element of the rational permutation algebra."""

    __slots__ = ("_terms", "_lookup", "_hash", "_line_count")
    _zero: ClassVar[PermutationSum | None] = None

    def __init__(
        self,
        terms: Mapping[Permutation, int | float | Fraction]
        | Iterable[tuple[Permutation, int | float | Fraction]] = (),
        *,
        line_count: int | None = None,
    ) -> None:
        self._line_count = _validated_line_count(line_count)
        source = terms.items() if isinstance(terms, Mapping) else terms
        combined: dict[Permutation, Fraction] = {}
        for permutation, coefficient in source:
            if not isinstance(permutation, Permutation):
                raise TypeError("term keys must be Permutation objects")
            exact = require_coefficient(coefficient)
            previous = combined.get(permutation)
            combined[permutation] = exact if previous is None else previous + exact

        self._initialize(combined)

    @classmethod
    def _from_accumulator(
        cls,
        accumulator: Mapping[Permutation, Fraction],
        *,
        line_count: int | None = None,
    ) -> PermutationSum:
        """Build from already validated exact coefficients."""
        result = cls.__new__(cls)
        result._line_count = _validated_line_count(line_count)
        result._initialize(accumulator)
        return result if result._terms or line_count is not None else cls.zero()

    def _initialize(self, combined: Mapping[Permutation, Fraction]) -> None:
        self._terms = tuple(
            sorted(
                (
                    (permutation, coefficient)
                    for permutation, coefficient in combined.items()
                    if coefficient
                ),
                key=lambda term: tuple(term[0]),
            )
        )
        self._lookup = MappingProxyType(dict(self._terms))
        self._hash = hash(self._terms)

    @classmethod
    def zero(cls) -> PermutationSum:
        if cls._zero is None:
            cls._zero = cls()
        return cls._zero

    @classmethod
    def from_permutation(
        cls,
        permutation: Permutation,
        coefficient: int | float | Fraction = 1,
    ) -> PermutationSum:
        if not isinstance(permutation, Permutation):
            raise TypeError("from_permutation expects a Permutation object")
        exact = require_coefficient(coefficient)
        return cls.zero() if not exact else cls(((permutation, exact),))

    @property
    def terms(self) -> Mapping[Permutation, Fraction]:
        """The read-only mapping from permutations to nonzero coefficients."""
        return self._lookup

    @property
    def line_count(self) -> int | None:
        """Number of boundary lines retained from a collapsed projector."""
        return self._line_count

    def trace(self, *, domain_size: int | None = None) -> object:
        """Close all lines into an exact polynomial, including fixed strands.

        ``domain_size`` overrides retained projector provenance, but cannot
        discard lines that were present in the source projector.
        """
        from .dimension_polynomial import DimensionPolynomial

        if domain_size is not None:
            domain_size = _validated_line_count(domain_size)
            assert domain_size is not None
            if self._line_count is not None and domain_size < self._line_count:
                raise ValueError(
                    "domain_size cannot be smaller than the retained line count "
                    f"({self._line_count})"
                )
        elif self._line_count is not None:
            domain_size = self._line_count
        elif self:
            raise ValueError(
                "trace requires domain_size or a PermutationSum collapsed "
                "from a projector"
            )
        else:
            return DimensionPolynomial()

        assert domain_size is not None
        coefficients: dict[int, Fraction] = {}
        for permutation, coefficient in self._terms:
            moved = len(permutation.support)
            if moved > domain_size:
                raise ValueError("permutation support exceeds domain_size")
            cycles = len(permutation.cycles()) + domain_size - moved
            coefficients[cycles] = coefficients.get(cycles, Fraction()) + coefficient
        return DimensionPolynomial(coefficients)

    def coefficient(self, permutation: Permutation) -> Fraction:
        if not isinstance(permutation, Permutation):
            raise TypeError("coefficient expects a Permutation object")
        return self._lookup.get(permutation, Fraction())

    def items(self) -> Iterator[tuple[Permutation, Fraction]]:
        return iter(self._terms)

    def __add__(self, other: object) -> PermutationSum:
        promoted = _promote_addend(other)
        if promoted is NotImplemented:
            return NotImplemented
        accumulator = dict(self._terms)
        for permutation, coefficient in promoted._terms:
            previous = accumulator.get(permutation)
            accumulator[permutation] = (
                coefficient if previous is None else previous + coefficient
            )
        return PermutationSum._from_accumulator(
            accumulator,
            line_count=_combined_line_count(self, promoted),
        )

    def __radd__(self, other: object) -> PermutationSum:
        if other == 0 and type(other) is int:
            return self
        return self.__add__(other)

    def __neg__(self) -> PermutationSum:
        return PermutationSum._from_accumulator(
            {
                permutation: -coefficient
                for permutation, coefficient in self._terms
            },
            line_count=self._line_count,
        )

    def __sub__(self, other: object) -> PermutationSum:
        promoted = _promote_addend(other)
        if promoted is NotImplemented:
            return NotImplemented
        return self + (-promoted)

    def __rsub__(self, other: object) -> PermutationSum:
        promoted = _promote_addend(other)
        if promoted is NotImplemented:
            return NotImplemented
        return promoted - self

    def __mul__(self, other: object) -> PermutationSum:
        if _is_coefficient(other):
            scalar = require_coefficient(other)
            return PermutationSum(
                (
                    (permutation, coefficient * scalar)
                    for permutation, coefficient in self._terms
                ),
                line_count=self._line_count,
            )

        promoted = _promote_addend(other)
        if promoted is NotImplemented:
            return NotImplemented
        from .operations import multiply_sums

        return multiply_sums(self, promoted)

    def __rmul__(self, other: object) -> PermutationSum:
        if _is_coefficient(other):
            return self * other
        if isinstance(other, Permutation):
            return PermutationSum.from_permutation(other) * self
        return NotImplemented

    def __truediv__(self, scalar: object) -> PermutationSum:
        exact = require_coefficient(scalar)
        if not exact:
            raise ZeroDivisionError("cannot divide a permutation sum by zero")
        return self * (1 / exact)

    def __iter__(self) -> Iterator[tuple[Permutation, Fraction]]:
        return self.items()

    def __len__(self) -> int:
        return len(self._terms)

    def __bool__(self) -> bool:
        return bool(self._terms)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, PermutationSum) and self._terms == other._terms

    def __hash__(self) -> int:
        return self._hash

    def __reduce__(self) -> tuple[
        object, tuple[tuple[tuple[Permutation, Fraction], ...], int | None]
    ]:
        return (_restore_permutation_sum, (self._terms, self._line_count))

    def _repr_latex_(self) -> str:
        """Return Jupyter's rich-display representation in current notation."""
        from birdtracks.permutations.rendering import latex

        return "$" + latex(self) + "$"

    def __repr__(self) -> str:
        provenance = (
            "" if self._line_count is None else f", line_count={self._line_count}"
        )
        return f"PermutationSum({dict(self._terms)!r}{provenance})"


def _is_coefficient(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float, Fraction))


def _validated_line_count(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("line_count must be an integer or None")
    if value < 0:
        raise ValueError("line_count cannot be negative")
    return value


def _combined_line_count(left: PermutationSum, right: PermutationSum) -> int | None:
    if left.line_count == right.line_count:
        return left.line_count
    if left.line_count is not None and _fits_line_count(right, left.line_count):
        return left.line_count
    if right.line_count is not None and _fits_line_count(left, right.line_count):
        return right.line_count
    return None


def _fits_line_count(value: PermutationSum, line_count: int) -> bool:
    return value.line_count is None and all(
        len(permutation.support) <= line_count for permutation, _coefficient in value
    )


def _restore_permutation_sum(
    terms: tuple[tuple[Permutation, Fraction], ...], line_count: int | None
) -> PermutationSum:
    return PermutationSum(terms, line_count=line_count)


def _promote_addend(value: object) -> PermutationSum | type(NotImplemented):
    if isinstance(value, PermutationSum):
        return value
    if isinstance(value, Permutation):
        return PermutationSum.from_permutation(value)
    return NotImplemented
