"""Generic whiteboard symbol environment and expression evaluator."""

from __future__ import annotations

from functools import reduce
from typing import Generic, TypeVar

from .model import (
    Expression,
    ProductExpression,
    SymbolDefinition,
    SymbolReference,
    validate_symbol_name,
)
from .protocol import AlgebraBackend


ValueT = TypeVar("ValueT")


class EvaluationEnvironment(Generic[ValueT]):
    """A mutable symbol table over immutable algebraic values.

    The environment is the application boundary used by a future parser or
    widget.  It knows about names and expression structure, but not about
    projector graphs, Jupyter, or rendering.  Definitions cannot be removed
    through this API; deleting a canvas item therefore cannot invalidate a
    named value already used by another canvas.
    """

    def __init__(self, backend: AlgebraBackend[ValueT]) -> None:
        self._backend = backend
        self._definitions: dict[str, SymbolDefinition[ValueT]] = {}

    @property
    def backend(self) -> AlgebraBackend[ValueT]:
        """Return the computation backend used by this environment."""

        return self._backend

    @property
    def definitions(self) -> tuple[SymbolDefinition[ValueT], ...]:
        """Return deterministic, read-only snapshots of named definitions."""

        return tuple(self._definitions[name] for name in sorted(self._definitions))

    def define(self, name: str, value: object) -> SymbolDefinition[ValueT]:
        """Bind a new name to a validated immutable algebraic value.

        Rebinding is intentionally rejected.  A future versioning operation
        can make replacement explicit without silently changing existing
        expressions.
        """

        name = validate_symbol_name(name)
        if name in self._definitions:
            raise ValueError(f"symbol {name!r} is already defined")
        definition = SymbolDefinition(name, self._backend.validate(value))
        self._definitions[name] = definition
        return definition

    def resolve(self, reference_or_name: SymbolReference | str) -> ValueT:
        """Resolve a symbol reference without copying or mutating its value."""

        name = (
            reference_or_name.name
            if isinstance(reference_or_name, SymbolReference)
            else validate_symbol_name(reference_or_name)
        )
        try:
            return self._definitions[name].value
        except KeyError as exc:
            raise LookupError(f"unknown symbol {name!r}") from exc

    def evaluate(self, expression: Expression) -> ValueT:
        """Evaluate an expression using the configured backend."""

        if isinstance(expression, SymbolReference):
            return self.resolve(expression)
        if isinstance(expression, ProductExpression):
            values = (self.evaluate(factor) for factor in expression.factors)
            return reduce(self._backend.multiply, values)
        raise TypeError("evaluate expects a SymbolReference or ProductExpression")


__all__ = ["EvaluationEnvironment"]
