"""Reference permutation operations."""

from .types import Permutation


def compose(left: Permutation, right: Permutation) -> Permutation:
    """Return ``left ∘ right``: apply *right*, then *left*."""
    if not isinstance(left, Permutation) or not isinstance(right, Permutation):
        raise TypeError("compose expects two Permutation objects")
    if not left:
        return right
    if not right:
        return left
    left_map = left.mapping
    right_map = right.mapping
    result: list[tuple[int, int]] = []
    for source in sorted(left.support | right.support):
        middle = right_map.get(source, source)
        target = left_map.get(middle, middle)
        if target != source:
            result.append((source, target))
    return Permutation._from_sorted_items(result)
