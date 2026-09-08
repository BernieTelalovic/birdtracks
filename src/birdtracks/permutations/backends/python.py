"""Readable Python reference backend."""

from collections.abc import Sequence

from ..operations import compose
from ..types import Permutation


class PythonBackend:
    name = "python"

    def multiply_many(
        self, pairs: Sequence[tuple[Permutation, Permutation]],
    ) -> list[Permutation]:
        return [compose(left, right) for left, right in pairs]


python_backend = PythonBackend()
