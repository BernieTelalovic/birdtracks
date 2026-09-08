"""Backend interface shared by reference and optimized implementations."""

from collections.abc import Sequence
from typing import Protocol

from ..types import Permutation


class PermutationBackend(Protocol):
    name: str

    def multiply_many(
        self, pairs: Sequence[tuple[Permutation, Permutation]],
    ) -> list[Permutation]: ...
