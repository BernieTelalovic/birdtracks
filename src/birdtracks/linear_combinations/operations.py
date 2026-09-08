"""Multiplication engines for exact permutation sums."""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from fractions import Fraction
from math import ceil

from birdtracks.permutations.backends import python_backend
from birdtracks.permutations.backends.protocol import PermutationBackend
from birdtracks.permutations.types import Permutation

from .permutation_sum import PermutationSum

Term = tuple[Permutation, Fraction]

_worker_right_terms: tuple[Term, ...] = ()
_worker_backend: PermutationBackend = python_backend
_worker_pair_chunksize = 256


def multiply_sums(
    left: PermutationSum,
    right: PermutationSum,
    *,
    backend: PermutationBackend = python_backend,
    workers: int = 1,
    chunksize: int = 256,
) -> PermutationSum:
    """Multiply two sums, applying the right permutation first.

    Work is batched in deterministic Cartesian-product order. With multiple
    workers, processes accumulate independent blocks before the parent merges
    their exact coefficients in block order.
    """
    if not isinstance(left, PermutationSum) or not isinstance(
        right, PermutationSum
    ):
        raise TypeError("multiply_sums expects two PermutationSum objects")
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if chunksize < 1:
        raise ValueError("chunksize must be at least 1")
    if not left or not right:
        return PermutationSum.zero()
    from .permutation_sum import _combined_line_count

    line_count = _combined_line_count(left, right)

    left_terms = tuple(left.items())
    right_terms = tuple(right.items())
    if workers == 1:
        return PermutationSum._from_accumulator(
            _multiply_term_blocks(left_terms, right_terms, backend, chunksize),
            line_count=line_count,
        )

    # Return at most one locally combined result per worker. Fine-grained
    # process tasks duplicate large sparse partial sums during serialization.
    left_block_size = ceil(len(left_terms) / min(workers, len(left_terms)))
    blocks = tuple(_blocks(left_terms, left_block_size))
    accumulator: dict[Permutation, Fraction] = {}
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=_initialize_sum_worker,
        initargs=(right_terms, backend, chunksize),
    ) as executor:
        for partial in executor.map(_multiply_worker_block, blocks):
            _merge_terms(accumulator, partial)
    return PermutationSum._from_accumulator(accumulator, line_count=line_count)


def _blocks(terms: Sequence[Term], size: int) -> Sequence[tuple[Term, ...]]:
    return tuple(
        tuple(terms[start : start + size])
        for start in range(0, len(terms), size)
    )


def _initialize_sum_worker(
    right_terms: tuple[Term, ...],
    backend: PermutationBackend,
    chunksize: int,
) -> None:
    global _worker_right_terms, _worker_backend, _worker_pair_chunksize
    _worker_right_terms = right_terms
    _worker_backend = backend
    _worker_pair_chunksize = chunksize


def _multiply_worker_block(left_terms: tuple[Term, ...]) -> tuple[Term, ...]:
    accumulator = _multiply_term_blocks(
        left_terms,
        _worker_right_terms,
        _worker_backend,
        _worker_pair_chunksize,
    )
    return tuple(accumulator.items())


def _multiply_term_blocks(
    left_terms: Sequence[Term],
    right_terms: Sequence[Term],
    backend: PermutationBackend,
    chunksize: int,
) -> dict[Permutation, Fraction]:
    accumulator: dict[Permutation, Fraction] = {}
    pairs: list[tuple[Permutation, Permutation]] = []
    coefficients: list[Fraction] = []
    for left, left_coefficient in left_terms:
        for right, right_coefficient in right_terms:
            pairs.append((left, right))
            coefficients.append(left_coefficient * right_coefficient)
            if len(pairs) == chunksize:
                _accumulate_batch(accumulator, pairs, coefficients, backend)
                pairs.clear()
                coefficients.clear()
    if pairs:
        _accumulate_batch(accumulator, pairs, coefficients, backend)
    return accumulator


def _accumulate_batch(
    accumulator: dict[Permutation, Fraction],
    pairs: Sequence[tuple[Permutation, Permutation]],
    coefficients: Sequence[Fraction],
    backend: PermutationBackend,
) -> None:
    products = backend.multiply_many(pairs)
    if len(products) != len(pairs):
        raise RuntimeError("permutation backend returned the wrong result count")
    for product, coefficient in zip(products, coefficients):
        previous = accumulator.get(product)
        accumulator[product] = (
            coefficient if previous is None else previous + coefficient
        )


def _merge_terms(
    accumulator: dict[Permutation, Fraction], terms: Sequence[Term]
) -> None:
    for permutation, coefficient in terms:
        previous = accumulator.get(permutation)
        accumulator[permutation] = (
            coefficient if previous is None else previous + coefficient
        )
