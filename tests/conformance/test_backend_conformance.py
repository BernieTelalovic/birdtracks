"""Shared conformance tests for permutation backends."""

from fractions import Fraction
import random

import pytest

from birdtracks import Permutation, multiply_many, multiply_sums
from birdtracks.linear_combinations import PermutationSum
from birdtracks.permutations.backends import python_backend
from birdtracks.permutations.backends import cython_available, cython_backend


def test_python_backend_and_parallel_batch_agree() -> None:
    huge = 1 << 500
    pairs = [
        (Permutation.from_cycle(1, 2, 3), Permutation.from_cycle(2, 4)),
        (Permutation.from_cycle(-huge, 0, huge), Permutation.from_cycle(0, 7)),
    ] * 4
    expected = [left * right for left, right in pairs]
    assert multiply_many(pairs, backend=python_backend) == expected
    assert multiply_many(pairs, workers=2, chunksize=1) == expected


def test_serial_and_parallel_sum_multiplication_agree() -> None:
    identity = Permutation.identity()
    p = Permutation.from_cycle(1, 2)
    q = Permutation.from_cycle(2, 3)
    left = Fraction(2, 3) * identity - Fraction(5, 7) * p
    right = Fraction(11, 13) * q + Fraction(17, 19) * identity

    expected = multiply_sums(left, right, workers=1, chunksize=2)
    assert multiply_sums(left, right, workers=2, chunksize=2) == expected


@pytest.mark.skipif(not cython_available, reason="optional Cython backend not built")
def test_cython_backend_agrees_for_permutations_and_sums() -> None:
    identity = Permutation.identity()
    p = Permutation.from_cycle(1, 2, 3)
    q = Permutation.from_cycle(2, 4)
    pairs = [(identity, p), (p, identity), (p, q), (q, p)]
    assert cython_backend.multiply_many(pairs) == python_backend.multiply_many(pairs)

    left = PermutationSum(((identity, Fraction(1, 3)), (p, Fraction(-2, 5))))
    right = PermutationSum(((q, Fraction(7, 11)), (identity, Fraction(13, 17))))
    assert multiply_sums(left, right, backend=cython_backend) == multiply_sums(
        left, right, backend=python_backend
    )


@pytest.mark.skipif(not cython_available, reason="optional Cython backend not built")
def test_cython_native_boundaries_and_exact_fallback_agree() -> None:
    int64_min = -(1 << 63)
    int64_max = (1 << 63) - 1
    huge = 1 << 500
    native_low = Permutation.from_cycle(int64_min, int64_min + 1, 0)
    native_high = Permutation.from_cycle(0, int64_max - 1, int64_max)
    below = Permutation.from_cycle(int64_min - 1, -1)
    above = Permutation.from_cycle(1, int64_max + 1)
    enormous = Permutation.from_cycle(-huge, 0, huge)
    identity = Permutation.identity()
    pairs = [
        (native_low, native_high),
        (native_high, native_low),
        (below, native_low),
        (native_high, above),
        (enormous, above),
        (identity, enormous),
        (native_low, identity),
    ]

    assert cython_backend.multiply_many(pairs) == python_backend.multiply_many(pairs)


@pytest.mark.skipif(not cython_available, reason="optional Cython backend not built")
def test_cython_native_batch_agrees_on_randomized_products() -> None:
    rng = random.Random(0)
    pairs: list[tuple[Permutation, Permutation]] = []
    labels = tuple(range(-32, 32))
    for _ in range(500):
        left_support = tuple(rng.sample(labels, rng.randrange(2, 17)))
        right_support = tuple(rng.sample(labels, rng.randrange(2, 17)))
        left_images = tuple(rng.sample(left_support, len(left_support)))
        right_images = tuple(rng.sample(right_support, len(right_support)))
        pairs.append(
            (
                Permutation(zip(left_support, left_images)),
                Permutation(zip(right_support, right_images)),
            )
        )

    assert cython_backend.multiply_many(pairs) == python_backend.multiply_many(pairs)
