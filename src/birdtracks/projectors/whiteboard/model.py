"""Small, serializable expression values shared by whiteboard frontends.

These values describe meaning, not presentation.  In particular, a
``SymbolReference`` is not a copy of a diagram and carries no position,
colour, or renderer-specific state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, TypeAlias, TypeVar


ValueT = TypeVar("ValueT")
DefinitionKind: TypeAlias = Literal["projector", "diagram"]


def _contains_control_character(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def validate_symbol_name(name: str) -> str:
    """Return a valid user-defined, LaTeX-like name.

    Names are intentionally stored as source text.  The whiteboard frontend
    may later parse names such as ``P_{1}`` or ``\\mathcal{P}_{1}``, but the
    backend must preserve them without pretending to be a LaTeX parser.
    Control characters and line breaks are rejected because names are also
    persisted as single definition lines.
    """

    if not isinstance(name, str):
        raise TypeError("symbol names must be strings")
    name = name.strip()
    if not name or _contains_control_character(name):
        raise ValueError("symbol names must be non-empty single-line text")
    return name


@dataclass(frozen=True, slots=True)
class SymbolReference:
    """A reference to an immutable named value in an environment."""

    name: str

    def __post_init__(self) -> None:
        validate_symbol_name(self.name)


@dataclass(frozen=True, slots=True)
class ProductExpression:
    """An ordered product; operand order is mathematically significant."""

    factors: tuple[Expression, ...]

    def __post_init__(self) -> None:
        if len(self.factors) < 2:
            raise ValueError("a product must contain at least two factors")
        if not all(
            isinstance(factor, (SymbolReference, ProductExpression))
            for factor in self.factors
        ):
            raise TypeError("product factors must be whiteboard expressions")


Expression: TypeAlias = SymbolReference | ProductExpression


@dataclass(frozen=True, slots=True)
class SymbolDefinition(Generic[ValueT]):
    """An immutable name-to-value binding returned by an environment."""

    name: str
    value: ValueT

    def __post_init__(self) -> None:
        validate_symbol_name(self.name)


@dataclass(frozen=True, slots=True)
class DefinitionLine:
    """One ordered source line belonging to one typed whiteboard store."""

    id: str
    kind: DefinitionKind
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("definition line ids must be non-empty text")
        if _contains_control_character(self.id):
            raise ValueError("definition line ids must be non-empty single-line text")
        if self.kind not in {"projector", "diagram"}:
            raise ValueError("definition line kind must be projector or diagram")
        if not isinstance(self.source, str):
            raise TypeError("definition line source must be text")


def reference(name: str) -> SymbolReference:
    """Construct a symbol reference from a frontend token."""

    return SymbolReference(validate_symbol_name(name))


def product(*factors: Expression) -> ProductExpression:
    """Construct an ordered product expression."""

    return ProductExpression(tuple(factors))


__all__ = [
    "Expression",
    "DefinitionKind",
    "DefinitionLine",
    "ProductExpression",
    "SymbolDefinition",
    "SymbolReference",
    "product",
    "reference",
    "validate_symbol_name",
]
