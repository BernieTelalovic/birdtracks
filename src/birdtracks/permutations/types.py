"""Immutable sparse permutations of arbitrary-size integer labels."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from types import MappingProxyType
from typing import ClassVar

from .validation import require_label, validated_mapping


def _is_coefficient(value: object) -> bool:
    from fractions import Fraction

    return not isinstance(value, bool) and isinstance(value, (int, float, Fraction))


class Permutation:
    """A canonical finite-support permutation of the integers.

    Labels outside the support are fixed. Python integers are retained exactly
    and are never narrowed to a native fixed-width integer type.
    """

    __slots__ = ("_items", "_lookup", "_support", "_hash")
    _identity: ClassVar[Permutation | None] = None

    def __init__(
        self, mapping: Mapping[int, int] | Iterable[tuple[int, int]] = (),
    ) -> None:
        checked = validated_mapping(mapping)
        self._initialize(tuple(sorted(checked.items())))

    @classmethod
    def _from_sorted_items(
        cls, items: Iterable[tuple[int, int]],
    ) -> Permutation:
        """Build from validated, fixed-point-free items sorted by source.

        This is an internal multiplication fast path. Public construction must
        continue to use ``__init__`` so invalid permutations are rejected.
        """
        canonical = tuple(items)
        if not canonical:
            return cls.identity()
        result = cls.__new__(cls)
        result._initialize(canonical)
        return result

    def _initialize(self, canonical: tuple[tuple[int, int], ...]) -> None:
        lookup = dict(canonical)
        self._items = canonical
        self._lookup = MappingProxyType(lookup)
        self._support = frozenset(lookup)
        self._hash = hash(canonical)

    @classmethod
    def identity(cls) -> Permutation:
        if cls._identity is None:
            cls._identity = cls()
        return cls._identity

    @classmethod
    def from_cycle(cls, *labels: int) -> Permutation:
        checked = tuple(require_label(label) for label in labels)
        if len(set(checked)) != len(checked):
            raise ValueError("a cycle cannot repeat a label")
        if len(checked) < 2:
            return cls.identity()
        return cls(zip(checked, checked[1:] + checked[:1]))

    @classmethod
    def from_cycles(cls, *cycles: Iterable[int]) -> Permutation:
        """Compose cycles as written; the rightmost cycle acts first."""
        result = cls.identity()
        for cycle in cycles:
            result = result * cls.from_cycle(*cycle)
        return result

    @property
    def mapping(self) -> Mapping[int, int]:
        """The read-only sparse map, with fixed points omitted."""
        return self._lookup

    @property
    def support(self) -> frozenset[int]:
        return self._support

    def __call__(self, label: int) -> int:
        label = require_label(label)
        return self._lookup.get(label, label)

    def __mul__(self, other: object) -> object:
        if isinstance(other, Permutation):
            from .operations import compose

            return compose(self, other)
        from birdtracks.linear_combinations import PermutationSum

        if isinstance(other, PermutationSum):
            return PermutationSum.from_permutation(self) * other
        from birdtracks.projectors import Projector

        if isinstance(other, Projector):
            return other.__rmul__(self)
        if _is_coefficient(other):
            return PermutationSum.from_permutation(self, other)
        return NotImplemented

    def __rmul__(self, other: object) -> object:
        if _is_coefficient(other):
            from birdtracks.linear_combinations import PermutationSum

            return PermutationSum.from_permutation(self, other)
        return NotImplemented

    def __truediv__(self, scalar: object) -> object:
        if _is_coefficient(scalar):
            from birdtracks.linear_combinations import PermutationSum

            return PermutationSum.from_permutation(self) / scalar
        return NotImplemented

    def __add__(self, other: object) -> object:
        from birdtracks.linear_combinations import PermutationSum

        return PermutationSum.from_permutation(self) + other

    def __radd__(self, other: object) -> object:
        if other == 0 and type(other) is int:
            from birdtracks.linear_combinations import PermutationSum

            return PermutationSum.from_permutation(self)
        return self.__add__(other)

    def __neg__(self) -> object:
        from birdtracks.linear_combinations import PermutationSum

        return PermutationSum.from_permutation(self, -1)

    def __sub__(self, other: object) -> object:
        from birdtracks.linear_combinations import PermutationSum

        return PermutationSum.from_permutation(self) - other

    def __rsub__(self, other: object) -> object:
        from birdtracks.linear_combinations import PermutationSum

        return other - PermutationSum.from_permutation(self)

    def inverse(self) -> Permutation:
        return Permutation((target, source) for source, target in self._items)

    def cycles(self) -> tuple[tuple[int, ...], ...]:
        """Return deterministic cycles, each starting at its smallest label."""
        unseen = set(self._support)
        result: list[tuple[int, ...]] = []
        while unseen:
            current = min(unseen)
            cycle: list[int] = []
            while current in unseen:
                unseen.remove(current)
                cycle.append(current)
                current = self._lookup[current]
            result.append(tuple(cycle))
        return tuple(result)

    def __iter__(self) -> Iterator[tuple[int, int]]:
        return iter(self._items)

    def _repr_latex_(self) -> str:
        """Return Jupyter's rich-display representation in current notation."""
        from .rendering import latex

        return "$" + latex(self) + "$"

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Permutation) and self._items == other._items

    def __hash__(self) -> int:
        return self._hash

    def __reduce__(self) -> tuple[object, tuple[tuple[tuple[int, int], ...]]]:
        return (Permutation, (self._items,))

    def __repr__(self) -> str:
        if not self:
            return "Permutation.identity()"
        cycles = ", ".join(repr(cycle) for cycle in self.cycles())
        return f"Permutation.from_cycles({cycles})"
