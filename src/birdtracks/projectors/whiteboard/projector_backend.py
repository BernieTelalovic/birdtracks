"""Concrete algebra adapter for immutable birdtrack projectors."""

from __future__ import annotations

from fractions import Fraction

from ..projector import Projector
from ..projector_sum import ProjectorSum
from ...symbolic import SymbolicCoefficient


ProjectorValue = Projector | ProjectorSum | SymbolicCoefficient


class ProjectorAlgebraBackend:
    """Adapt the existing exact ``Projector`` algebra to the whiteboard API."""

    name = "projector"

    def validate(self, value: object) -> ProjectorValue:
        if not isinstance(value, (Projector, ProjectorSum, SymbolicCoefficient)):
            raise TypeError(
                "projector definitions must contain projector or scalar values"
            )
        return value

    def multiply(self, left: ProjectorValue, right: ProjectorValue) -> ProjectorValue:
        if isinstance(left, SymbolicCoefficient) or isinstance(right, SymbolicCoefficient):
            if isinstance(left, SymbolicCoefficient) and isinstance(right, SymbolicCoefficient):
                return left * right
            raise TypeError("symbolic projector scaling is handled by the expression model")
        if isinstance(left, Projector) and isinstance(right, Projector):
            return left * right
        left_terms = _terms(left)
        right_terms = _terms(right)
        return ProjectorSum(
            (left_projector * right_projector, left_coefficient * right_coefficient)
            for left_projector, left_coefficient in left_terms
            for right_projector, right_coefficient in right_terms
        )


def _terms(value: ProjectorValue) -> tuple[tuple[Projector, Fraction], ...]:
    if isinstance(value, Projector):
        return ((value, Fraction(1)),)
    return tuple(value.items())


projector_backend = ProjectorAlgebraBackend()


__all__ = ["ProjectorAlgebraBackend", "projector_backend"]
