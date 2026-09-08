"""Unit tests for permutation values and operations."""

import pickle

import pytest

from birdtracks import Permutation


def test_agreed_arbitrary_domain_product() -> None:
    left = Permutation.from_cycle(1, 2, 3)
    right = Permutation.from_cycle(2, 4)
    assert (left * right).cycles() == ((1, 2, 4, 3),)
    assert (left * right).cycles() == ((1, 2, 4, 3),)


def test_arbitrary_precision_signed_labels_are_exact() -> None:
    huge = 1 << 1000
    permutation = Permutation.from_cycle(-huge, 0, huge)
    assert permutation(-huge) == 0
    assert permutation(0) == huge
    assert permutation(huge) == -huge
    assert (permutation * permutation.inverse()) == Permutation.identity()


def test_fixed_points_are_implicit_and_canonical() -> None:
    assert Permutation({1: 1}) == Permutation.identity()
    assert hash(Permutation({1: 1})) == hash(Permutation.identity())
    assert Permutation.from_cycle(3, 1, 2).cycles() == ((1, 2, 3),)


def test_explicit_ambient_fixed_points_do_not_change_a_permutation() -> None:
    canonical = Permutation.from_cycle(1, 2, 3)
    with_larger_ambient_support = Permutation(
        {
            1: 2,
            2: 3,
            3: 1,
            **{label: label for label in range(4, 101)},
        }
    )

    assert with_larger_ambient_support == canonical
    assert hash(with_larger_ambient_support) == hash(canonical)
    assert with_larger_ambient_support.support == canonical.support


def test_multiplication_uses_the_union_of_unequal_supports() -> None:
    smaller = Permutation.from_cycle(*range(16))
    larger = Permutation.from_cycle(*range(8, 32))

    product = smaller * larger

    assert product.support <= smaller.support | larger.support
    assert set(range(16, 32)) <= product.support
    for label in smaller.support | larger.support:
        assert product(label) == smaller(larger(label))


def test_mapping_must_be_a_bijection_on_its_support() -> None:
    with pytest.raises(ValueError):
        Permutation({1: 2})
    with pytest.raises(ValueError):
        Permutation({1: 2, 2: 2})


@pytest.mark.parametrize("label", [True, 1.0, "1", None])
def test_only_integer_labels_are_accepted(label: object) -> None:
    with pytest.raises(TypeError):
        Permutation.from_cycle(1, label)  # type: ignore[arg-type]


def test_cycle_rejects_duplicate_labels() -> None:
    with pytest.raises(ValueError):
        Permutation.from_cycle(1, 2, 1)


def test_value_is_picklable_for_process_workers() -> None:
    value = Permutation.from_cycle(-(1 << 200), 2, 1 << 200)
    assert pickle.loads(pickle.dumps(value)) == value
