"""Immutable permutation nodes for birdtrack projector graphs."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from birdtracks.linear_combinations import PermutationSum
from birdtracks.permutations import Permutation


class PermutationNode:
    """A birdtrack node whose right strand ``i`` exits left at ``p(i)``."""

    __slots__ = ("_permutation", "_support", "_in_direction", "_out_direction", "_hash")

    def __init__(
        self,
        permutation: Permutation,
        support: Iterable[int] | None = None,
        in_direction: Literal["left", "right", "neutral"] = "neutral",
        out_direction: Literal["left", "right", "neutral"] = "neutral",
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
        if (in_direction, out_direction) not in {
            ("left", "right"), ("right", "left"), ("neutral", "neutral")
        }:
            raise ValueError("in_direction and out_direction must be paired")
        self._in_direction = in_direction
        self._out_direction = out_direction
        self._hash = hash((type(self), permutation, self._support, in_direction, out_direction))

    @property
    def permutation(self) -> Permutation:
        return self._permutation

    @property
    def support(self) -> frozenset[int]:
        """The finite set of non-fixed strands shown by this node."""
        return self._support

    @property
    def in_direction(self) -> Literal["left", "right", "neutral"]:
        return self._in_direction

    @property
    def out_direction(self) -> Literal["left", "right", "neutral"]:
        return self._out_direction

    def collapse(self) -> PermutationSum:
        """Return this node as a one-term exact permutation sum."""
        return PermutationSum.from_permutation(self._permutation)

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, PermutationNode)
            and self._permutation == other._permutation
            and self._support == other._support
            and self._in_direction == other._in_direction
            and self._out_direction == other._out_direction
        )

    def __hash__(self) -> int:
        return self._hash

    def __reduce__(self) -> tuple[object, tuple[Permutation, frozenset[int]]]:
        return (type(self), (
            self._permutation,
            self._support,
            self._in_direction,
            self._out_direction,
        ))

    def __repr__(self) -> str:
        support = tuple(sorted(self._support))
        return (
            f"PermutationNode({self._permutation!r}, support={support!r}, "
            f"in_direction={self._in_direction!r}, "
            f"out_direction={self._out_direction!r})"
        )


__all__ = ["PermutationNode"]
