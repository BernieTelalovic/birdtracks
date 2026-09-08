"""Immutable permutation nodes for birdtrack projector graphs."""

from __future__ import annotations

from collections.abc import Iterable

from birdtracks.linear_combinations import PermutationSum
from birdtracks.permutations import Permutation


class PermutationNode:
    """A birdtrack node whose right strand ``i`` exits left at ``p(i)``."""

    __slots__ = ("_permutation", "_support", "_hash")

    def __init__(
        self,
        permutation: Permutation,
        support: Iterable[int] | None = None,
    ) -> None:
        if not isinstance(permutation, Permutation):
            raise TypeError("permutation must be a Permutation object")
        ambient = permutation.support if support is None else frozenset(support)
        if any(isinstance(label, bool) or not isinstance(label, int) for label in ambient):
            raise TypeError("permutation-node support labels must be integers")
        if not permutation.support <= ambient:
            raise ValueError("permutation-node support must contain the permutation support")
        self._permutation = permutation
        self._support = frozenset(ambient)
        self._hash = hash((type(self), permutation, self._support))

    @property
    def permutation(self) -> Permutation:
        return self._permutation

    @property
    def support(self) -> frozenset[int]:
        """The finite set of non-fixed strands shown by this node."""
        return self._support

    def collapse(self) -> PermutationSum:
        """Return this node as a one-term exact permutation sum."""
        return PermutationSum.from_permutation(self._permutation)

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, PermutationNode)
            and self._permutation == other._permutation
            and self._support == other._support
        )

    def __hash__(self) -> int:
        return self._hash

    def __reduce__(self) -> tuple[object, tuple[Permutation, frozenset[int]]]:
        return (type(self), (self._permutation, self._support))

    def __repr__(self) -> str:
        support = tuple(sorted(self._support))
        return f"PermutationNode({self._permutation!r}, support={support!r})"


__all__ = ["PermutationNode"]
