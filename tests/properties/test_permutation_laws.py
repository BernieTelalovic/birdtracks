"""Algebraic-law tests for permutations."""

from itertools import permutations

from birdtracks import Permutation


def samples() -> list[Permutation]:
    values = [Permutation.identity()]
    for labels in permutations((-2, 0, 3), 2):
        values.append(Permutation.from_cycle(*labels))
    values.append(Permutation.from_cycle(-2, 0, 3))
    return values


def test_identity_inverse_and_associativity() -> None:
    identity = Permutation.identity()
    values = samples()
    for value in values:
        assert value * identity == value == identity * value
        assert value * value.inverse() == identity
        assert value.inverse() * value == identity
    for left in values:
        for middle in values:
            for right in values:
                assert (left * middle) * right == left * (middle * right)
