"""Data-oriented batch permutation operations."""

from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor

from .backends.protocol import PermutationBackend
from .backends.python import python_backend
from .operations import compose
from .types import Permutation


def multiply_many(
    pairs: Sequence[tuple[Permutation, Permutation]],
    *,
    backend: PermutationBackend = python_backend,
    workers: int = 1,
    chunksize: int = 256,
) -> list[Permutation]:
    """Multiply independent pairs in input order, optionally in processes."""
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if chunksize < 1:
        raise ValueError("chunksize must be at least 1")
    if workers == 1:
        return backend.multiply_many(pairs)
    if backend is not python_backend:
        raise ValueError("external process parallelism requires the Python backend")
    with ProcessPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(_compose_pair, pairs, chunksize=chunksize))


def _compose_pair(pair: tuple[Permutation, Permutation]) -> Permutation:
    return compose(*pair)
