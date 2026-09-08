"""Optional compiled permutation backend."""

from collections.abc import Sequence

from ..types import Permutation

try:
    from ._cython import multiply_many as _multiply_many
except ImportError:
    _multiply_many = None


class CythonBackend:
    """Batch permutation composition through the optional Cython extension."""

    name = "cython"

    def multiply_many(
        self, pairs: Sequence[tuple[Permutation, Permutation]],
    ) -> list[Permutation]:
        if _multiply_many is None:
            raise RuntimeError(
                "the Cython backend is not built; see benchmarks/README.md"
            )
        return _multiply_many(pairs)


cython_backend = CythonBackend()
cython_available = _multiply_many is not None
