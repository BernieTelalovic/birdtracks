"""Dependency-free permutation multiplication microbenchmark."""

from __future__ import annotations

import argparse
import random
import time

from birdtracks import Permutation, multiply_many
from birdtracks.permutations.backends import (
    cython_available,
    cython_backend,
    python_backend,
)


def workload(count: int, support: int) -> list[tuple[Permutation, Permutation]]:
    rng = random.Random(0)
    result = []
    for _ in range(count):
        labels = rng.sample(range(-support * 10, support * 10), support * 2)
        left = Permutation.from_cycle(*labels[:support])
        right = Permutation.from_cycle(*labels[support:])
        result.append((left, right))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10_000)
    parser.add_argument("--support", type=int, default=16)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--backend", choices=("python", "cython"), default="python")
    args = parser.parse_args()
    if args.backend == "cython" and not cython_available:
        parser.error("the optional Cython backend is not built")
    backend = cython_backend if args.backend == "cython" else python_backend
    pairs = workload(args.count, args.support)
    started = time.perf_counter()
    multiply_many(pairs, backend=backend, workers=args.workers)
    elapsed = time.perf_counter() - started
    print(f"{args.count / elapsed:,.0f} products/s ({elapsed:.3f}s)")


if __name__ == "__main__":
    main()
