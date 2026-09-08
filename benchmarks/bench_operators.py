"""Benchmark exact multiplication of sparse permutation operators."""

from __future__ import annotations

import argparse
import math
import random
import time
from fractions import Fraction

from birdtracks import Permutation, PermutationSum, multiply_sums
from birdtracks.permutations.backends import (
    cython_available,
    cython_backend,
    python_backend,
)


def operator(terms: int, support: int, seed: int) -> PermutationSum:
    rng = random.Random(seed)
    labels = tuple(range(support))
    coefficients: dict[Permutation, Fraction] = {}
    while len(coefficients) < terms:
        images = rng.sample(labels, support)
        permutation = Permutation(zip(labels, images))
        index = len(coefficients)
        coefficients[permutation] = Fraction(index + 1, index + 2)
    return PermutationSum(coefficients)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--terms", type=int, default=100)
    parser.add_argument("--support", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--chunksize", type=int, default=256)
    parser.add_argument("--backend", choices=("python", "cython"), default="python")
    args = parser.parse_args()

    if args.terms < 1 or args.support < 2 or args.repeats < 1:
        parser.error("terms and repeats must be positive; support must be at least 2")
    if args.terms > math.factorial(args.support):
        parser.error("terms cannot exceed the number of support permutations")
    if args.backend == "cython" and not cython_available:
        parser.error("the optional Cython backend is not built")
    backend = cython_backend if args.backend == "cython" else python_backend
    left = operator(args.terms, args.support, 0)
    right = operator(args.terms, args.support, 1)

    started = time.perf_counter()
    result = PermutationSum.zero()
    for _ in range(args.repeats):
        result = multiply_sums(
            left,
            right,
            backend=backend,
            workers=args.workers,
            chunksize=args.chunksize,
        )
    elapsed = time.perf_counter() - started
    pair_count = len(left) * len(right) * args.repeats
    print(
        f"{pair_count / elapsed:,.0f} term-pairs/s; "
        f"{elapsed / args.repeats * 1000:.3f} ms/operator product; "
        f"{len(result)} output terms"
    )


if __name__ == "__main__":
    main()
