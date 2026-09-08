"""Performance contract for exhaustive multiplication in small symmetric groups."""

from itertools import permutations
from time import perf_counter

from birdtracks import Permutation, multiply_many

S3_PRODUCT_LIMIT_SECONDS = 0.0004


def symmetric_group_3() -> tuple[Permutation, ...]:
    """Return all six permutations of labels 1, 2, 3 deterministically."""
    labels = (1, 2, 3)
    return tuple(
        Permutation(zip(labels, images))
        for images in permutations(labels)
    )


def test_all_ordered_s3_products_complete_under_half_a_second() -> None:
    group = symmetric_group_3()
    assert len(group) == 6
    assert len(set(group)) == 6

    pairs = [(left, right) for left in group for right in group]

    started = perf_counter()
    products = multiply_many(pairs)
    elapsed = perf_counter() - started

    assert len(products) == 36
    assert elapsed < S3_PRODUCT_LIMIT_SECONDS, (
        "multiplying the 36 ordered pairs in S_3 took "
        f"{elapsed:.6f}s; target is under {S3_PRODUCT_LIMIT_SECONDS:.6f}s"
    )
