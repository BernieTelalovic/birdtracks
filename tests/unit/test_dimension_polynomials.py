"""Exact symbolic-dimension coefficient tests."""

from fractions import Fraction

import pytest

from birdtracks import (
    DimensionPolynomial,
    Permutation,
    PolynomialPermutationSum,
)


def test_dimension_polynomial_is_exact_immutable_and_evaluable() -> None:
    polynomial = DimensionPolynomial({0: Fraction(1, 3), 2: Fraction(2, 5)})

    assert polynomial.coefficient(1) == 0
    assert polynomial.evaluate(3) == Fraction(59, 15)
    assert hash(polynomial) == hash(
        DimensionPolynomial({2: Fraction(2, 5), 0: Fraction(1, 3)})
    )
    assert str(polynomial) == "(2/5) N ** 2 + (1/3)"
    assert repr(polynomial) == "(2/5) N ** 2 + (1/3)"
    with pytest.raises(TypeError):
        polynomial.coefficients[1] = Fraction(2)  # type: ignore[index]


def test_dimension_polynomials_multiply_and_collect_equal_powers_exactly() -> None:
    left = DimensionPolynomial({0: Fraction(1, 2), 1: Fraction(1, 3)})
    right = DimensionPolynomial({0: -2, 1: Fraction(3, 5)})

    product = left * right

    assert product == DimensionPolynomial(
        {
            0: -1,
            1: Fraction(-11, 30),
            2: Fraction(1, 5),
        }
    )
    assert product.evaluate(7) == left.evaluate(7) * right.evaluate(7)
    assert product == right * left
    assert product * DimensionPolynomial() == DimensionPolynomial()


def test_polynomial_permutation_sum_evaluates_to_rational_sum() -> None:
    identity = Permutation.identity()
    swap = Permutation.from_cycle(1, 2)
    value = PolynomialPermutationSum(
        {
            identity: DimensionPolynomial({1: 1}),
            swap: DimensionPolynomial({0: Fraction(-1, 2), 2: Fraction(1, 2)}),
        }
    )

    evaluated = value.evaluate(3)

    assert evaluated.coefficient(identity) == 3
    assert evaluated.coefficient(swap) == 4


def test_identity_term_displays_as_the_polynomial_without_identity() -> None:
    value = PolynomialPermutationSum(
        {
            Permutation.identity(): DimensionPolynomial(
                {0: Fraction(1, 2), 2: Fraction(1, 2)}
            )
        }
    )

    assert value._repr_latex_() == r"$\frac{1}{2}N^{2} + \frac{1}{2}$"


def test_polynomial_permutation_sums_add_and_collect_equal_terms() -> None:
    identity = Permutation.identity()
    left = PolynomialPermutationSum(
        {identity: DimensionPolynomial({0: 1, 1: 2})}
    )
    right = PolynomialPermutationSum(
        {identity: DimensionPolynomial({0: -1, 2: 3})}
    )

    assert (left + right).coefficient(identity) == DimensionPolynomial(
        {1: 2, 2: 3}
    )
    assert (left + right).evaluate(2).coefficient(identity) == 16
