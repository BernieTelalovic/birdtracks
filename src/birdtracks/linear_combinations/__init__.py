"""Exact linear combinations of algebraic values."""

from .coefficients import (
    CoefficientPrecisionWarning,
    configure_coefficient_safety,
)
from .dimension_polynomial import DimensionPolynomial, PolynomialPermutationSum
from .operations import multiply_sums
from .permutation_sum import PermutationSum

__all__ = [
    "CoefficientPrecisionWarning",
    "DimensionPolynomial",
    "PermutationSum",
    "PolynomialPermutationSum",
    "configure_coefficient_safety",
    "multiply_sums",
]
