"""Exact coefficient-domain support and float-boundary safeguards."""

import math
import sys
from fractions import Fraction


class CoefficientPrecisionWarning(RuntimeWarning):
    """A float coefficient is close to overflow or underflow."""


_warning_factor = 1000.0


def configure_coefficient_safety(*, warning_factor: float = 1000.0) -> None:
    """Set how close finite floats may get to a boundary without a warning.

    A factor of 1000 warns at or above ``max_float / 1000`` and at or
    below ``smallest_positive_float * 1000``. Exact integers and fractions
    are arbitrary-precision and are therefore not subject to this check.
    """
    if isinstance(warning_factor, bool):
        raise TypeError("warning_factor must be a finite number at least 1")
    try:
        factor = float(warning_factor)
    except (TypeError, ValueError, OverflowError) as error:
        raise TypeError(
            "warning_factor must be a finite number at least 1"
        ) from error
    if not math.isfinite(factor) or factor < 1:
        raise ValueError("warning_factor must be finite and at least 1")

    global _warning_factor
    _warning_factor = factor


def _warn_near_float_boundary(value: float) -> None:
    import warnings

    magnitude = abs(value)
    if magnitude >= sys.float_info.max / _warning_factor:
        warnings.warn(
            f"float coefficient {value!r} is within a factor of "
            f"{_warning_factor:g} of overflow",
            CoefficientPrecisionWarning,
            stacklevel=3,
        )
    elif magnitude and magnitude <= math.ulp(0.0) * _warning_factor:
        warnings.warn(
            f"float coefficient {value!r} is within a factor of "
            f"{_warning_factor:g} of underflow",
            CoefficientPrecisionWarning,
            stacklevel=3,
        )


def require_coefficient(value: object) -> Fraction:
    """Return an exact rational, interpreting floats by their decimal spelling."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Fraction)):
        raise TypeError("coefficients must be integers, floats, or fractions")
    if isinstance(value, float):
        if math.isnan(value):
            raise ValueError("NaN cannot be used as a coefficient")
        if math.isinf(value):
            raise OverflowError(
                f"infinite float coefficient {value!r} has overflowed"
            )
        _warn_near_float_boundary(value)
        return Fraction(str(value))
    return Fraction(value)
