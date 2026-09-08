"""Unit tests for exact permutation sums."""

import math
import sys
import warnings
from fractions import Fraction

import pytest

from birdtracks import (
    CoefficientPrecisionWarning,
    Permutation,
    PermutationSum,
    configure_coefficient_safety,
    multiply_sums,
)


def test_mathematical_syntax_promotes_permutations() -> None:
    p = Permutation.from_cycle(1, 2)
    q = Permutation.from_cycle(2, 3)

    value = Fraction(1, 2) * p - q

    assert isinstance(value, PermutationSum)
    assert value.coefficient(p) == Fraction(1, 2)
    assert value.coefficient(q) == -1


def test_duplicate_terms_combine_and_zero_terms_disappear() -> None:
    p = Permutation.from_cycle(1, 2)
    assert p + p == 2 * p
    assert p - p == PermutationSum.zero()
    assert not (p - p)


def test_sum_multiplication_distributes_with_existing_composition_order() -> None:
    identity = Permutation.identity()
    p = Permutation.from_cycle(1, 2)
    q = Permutation.from_cycle(2, 3)

    result = (identity + p) * (identity - q)

    assert result == identity - q + p - (p * q)
    assert p * (identity + q) == p + (p * q)
    assert (identity + p) * q == q + (p * q)


def test_plain_permutation_product_remains_a_permutation() -> None:
    p = Permutation.from_cycle(1, 2)
    q = Permutation.from_cycle(2, 3)
    assert isinstance(p * q, Permutation)


def test_integer_and_fraction_scalar_arithmetic_is_exact_on_either_side() -> None:
    p = Permutation.from_cycle(1, 2)
    identity = Permutation.identity()
    assert p * Fraction(2, 3) == Fraction(2, 3) * p
    assert (p + identity) / 3 == (
        Fraction(1, 3) * p + Fraction(1, 3) * identity
    )


def test_floats_use_their_decimal_value_for_multiplication_and_division() -> None:
    p = Permutation.from_cycle(1, 2)
    value = p + Permutation.identity()

    assert 0.1 * p == p * Fraction(1, 10)
    assert p * 0.1 == p * Fraction(1, 10)
    assert p / 0.2 == 5 * p
    assert value * 0.1 == value * Fraction(1, 10)
    assert value / 0.2 == 5 * value


def test_nan_coefficient_raises_value_error() -> None:
    p = Permutation.from_cycle(1, 2)
    with pytest.raises(ValueError, match="NaN"):
        p * float("nan")


@pytest.mark.parametrize("coefficient", [float("inf"), -float("inf")])
def test_infinite_coefficient_raises_overflow_error(coefficient: float) -> None:
    p = Permutation.from_cycle(1, 2)
    with pytest.raises(OverflowError, match="overflowed"):
        p * coefficient
    with pytest.raises(OverflowError, match="overflowed"):
        p / coefficient


@pytest.mark.parametrize(
    ("coefficient", "boundary"),
    [
        (sys.float_info.max, "overflow"),
        (math.ulp(0.0), "underflow"),
        (-sys.float_info.max, "overflow"),
        (-math.ulp(0.0), "underflow"),
    ],
)
def test_float_coefficients_near_boundaries_warn(
    coefficient: float, boundary: str
) -> None:
    p = Permutation.from_cycle(1, 2)
    with pytest.warns(CoefficientPrecisionWarning, match=boundary):
        result = coefficient * p
    assert result.coefficient(p) == Fraction(str(coefficient))


def test_zero_float_is_valid_and_does_not_warn() -> None:
    p = Permutation.from_cycle(1, 2)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert 0.0 * p == PermutationSum.zero()


def test_float_boundary_warning_factor_is_configurable() -> None:
    p = Permutation.from_cycle(1, 2)
    coefficient = sys.float_info.max / 500
    try:
        configure_coefficient_safety(warning_factor=100)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            coefficient * p

        configure_coefficient_safety(warning_factor=1000)
        with pytest.warns(CoefficientPrecisionWarning, match="overflow"):
            coefficient * p
    finally:
        configure_coefficient_safety()


@pytest.mark.parametrize("factor", [0, 0.5, float("inf"), float("nan")])
def test_invalid_float_boundary_warning_factor_is_rejected(factor: float) -> None:
    with pytest.raises(ValueError):
        configure_coefficient_safety(warning_factor=factor)


def test_boolean_float_boundary_warning_factor_is_rejected() -> None:
    with pytest.raises(TypeError):
        configure_coefficient_safety(warning_factor=True)


def test_boolean_coefficients_are_rejected() -> None:
    p = Permutation.from_cycle(1, 2)
    with pytest.raises(TypeError):
        PermutationSum({p: True})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        PermutationSum.from_permutation(p, True)  # type: ignore[arg-type]


def test_division_by_integer_or_float_zero_is_rejected() -> None:
    p = Permutation.from_cycle(1, 2)
    with pytest.raises(ZeroDivisionError):
        p / 0
    with pytest.raises(ZeroDivisionError):
        (p + Permutation.identity()) / 0.0


def test_sum_builtin_uses_zero_as_the_additive_identity() -> None:
    p = Permutation.from_cycle(1, 2)
    q = Permutation.from_cycle(2, 3)
    assert sum((p, q)) == p + q


def test_value_is_hashable_and_terms_are_read_only() -> None:
    p = Permutation.from_cycle(1, 2)
    value = Fraction(1, 2) * p
    assert hash(value) == hash(PermutationSum({p: Fraction(1, 2)}))
    with pytest.raises(TypeError):
        value.terms[p] = Fraction(2)  # type: ignore[index]


def test_extreme_fraction_addition_and_subtraction_are_exact() -> None:
    p = Permutation.from_cycle(1, 2)
    q = Permutation.from_cycle(2, 3)
    huge = Fraction(10**1000, 3)
    tiny = Fraction(7, 10**1000)

    value = huge * p + tiny * q
    assert (value + tiny * p).coefficient(p) == huge + tiny
    assert (value - huge * p).coefficient(p) == 0
    assert (value - huge * p).coefficient(q) == tiny
    assert value - value == PermutationSum.zero()


def test_extreme_fraction_multiplication_is_exact_and_distributive() -> None:
    identity = Permutation.identity()
    p = Permutation.from_cycle(1, 2)
    q = Permutation.from_cycle(2, 3)
    huge = Fraction(10**1000, 13)
    tiny = Fraction(17, 10**1000)

    product = (huge * p + tiny * identity) * (tiny * q - huge * identity)
    expected = (
        (huge * tiny) * (p * q)
        - (huge * huge) * p
        + (tiny * tiny) * q
        - (tiny * huge) * identity
    )
    assert product == expected


def test_zero_and_identity_edges_for_sum_arithmetic() -> None:
    identity = Permutation.identity()
    p = Permutation.from_cycle(1, 2)
    value = Fraction(-2, 7) * identity + Fraction(3, 11) * p
    zero = PermutationSum.zero()

    assert value + zero == value == zero + value
    assert value - zero == value
    assert zero - value == -value
    assert value * zero == zero == zero * value
    assert value * identity == value == identity * value
    assert value * 0 == zero == 0 * value


def test_duplicate_products_cancel_during_multiplication() -> None:
    identity = Permutation.identity()
    p = Permutation.from_cycle(1, 2)

    assert (identity + p) * (identity - p) == PermutationSum.zero()


@pytest.mark.parametrize(
    ("workers", "chunksize", "message"),
    [(0, 1, "workers"), (1, 0, "chunksize")],
)
def test_sum_multiplication_rejects_invalid_parallel_settings(
    workers: int, chunksize: int, message: str
) -> None:
    zero = PermutationSum.zero()
    with pytest.raises(ValueError, match=message):
        multiply_sums(zero, zero, workers=workers, chunksize=chunksize)


def test_multiply_sums_requires_sum_operands() -> None:
    p = Permutation.from_cycle(1, 2)
    with pytest.raises(TypeError, match="two PermutationSum"):
        multiply_sums(p, p)  # type: ignore[arg-type]
