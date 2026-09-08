"""Symbolic normalised symmetrisers and antisymmetrisers."""

from __future__ import annotations

from collections.abc import Iterable, Set
from fractions import Fraction
from itertools import permutations
from math import factorial

from birdtracks.linear_combinations import PermutationSum
from birdtracks.permutations import Permutation


class _PermutationProjector:
    """Shared immutable value semantics for permutation projectors."""

    __slots__ = ("_labels", "_support", "_hash")

    _antisymmetric = False

    def __init__(self, support: Iterable[int]) -> None:
        try:
            labels = tuple(sorted(support)) if isinstance(support, Set) else tuple(support)
        except TypeError as exc:
            raise TypeError("support must be a collection of integer labels") from exc

        for label in labels:
            if isinstance(label, bool) or not isinstance(label, int):
                raise TypeError(
                    f"support labels must be integers, got {label!r}"
                )
        if len(set(labels)) != len(labels):
            raise ValueError("support cannot contain duplicate labels")

        self._labels = labels
        self._support = frozenset(labels)
        self._hash = hash((type(self), self._support))

    @property
    def labels(self) -> tuple[int, ...]:
        """The lines in the user-specified order used by algebraic identities."""
        return self._labels

    @property
    def support(self) -> frozenset[int]:
        """The lines on which this projector acts."""
        return self._support

    def collapse(self) -> PermutationSum:
        """Expand this normalised projector into the permutation algebra."""
        normalisation = Fraction(1, factorial(len(self._labels)))
        terms = []
        for targets in permutations(self._labels):
            permutation = Permutation(zip(self._labels, targets))
            coefficient = normalisation
            if self._antisymmetric and _is_odd(targets, self._labels):
                coefficient = -coefficient
            terms.append((permutation, coefficient))
        return PermutationSum(terms)

    def __eq__(self, other: object) -> bool:
        return (
            type(self) is type(other)
            and isinstance(other, _PermutationProjector)
            and self._support == other._support
        )

    def __hash__(self) -> int:
        return self._hash

    def __reduce__(self) -> tuple[object, tuple[tuple[int, ...]]]:
        return (type(self), (self._labels,))

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._labels!r})"


class Symmetriser(_PermutationProjector):
    """A symbolic normalised symmetriser on a collection of lines."""


class Antisymmetriser(_PermutationProjector):
    """A symbolic normalised antisymmetriser on a collection of lines."""

    _antisymmetric = True


def _is_odd(values: tuple[int, ...], order: tuple[int, ...]) -> bool:
    """Return the parity of a permutation written as its target sequence."""
    rank = {label: index for index, label in enumerate(order)}
    positions = tuple(rank[label] for label in values)
    inversions = sum(
        left > right
        for index, left in enumerate(positions)
        for right in positions[index + 1 :]
    )
    return bool(inversions % 2)


__all__ = ["Antisymmetriser", "Symmetriser"]
