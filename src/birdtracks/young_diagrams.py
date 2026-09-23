"""Editable representation sums, independent of projector operator algebra.

Partitions use the standalone convention: barred first, unbarred second.
Coefficients, N0, and tableau labels use decimal strings to retain exact integers
across the browser boundary. Terms remain ordered and uncollected for editing.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import re
from typing import Any

from .symbolic import SymbolicCoefficient, as_symbolic, parse_symbolic


def _integer(value: object, label: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"[+-]?[0-9]+", value):
        raise ValueError(f"{label} must be an integer decimal string")
    return int(value)


def _partition(value: object) -> tuple[int, ...]:
    if not isinstance(value, list) or any(type(n) is not int or n <= 0 for n in value):
        raise ValueError("partition rows must be positive integers")
    if any(a < b for a, b in zip(value, value[1:])):
        raise ValueError("partition rows must be weakly decreasing")
    return tuple(value)


@dataclass(frozen=True)
class TableauLabel:
    """An integer annotation at a cell's partition coordinates."""

    side: str
    row: int
    column: int
    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.side, str) or self.side not in {"barred", "unbarred"}:
            raise ValueError("tableau label side must be barred or unbarred")
        if any(type(n) is not int for n in (self.row, self.column, self.value)):
            raise ValueError("tableau label coordinates and value must be integers")
        if self.row < 0 or self.column < 0:
            raise ValueError("tableau label coordinates must be nonnegative")

    def state(self) -> dict[str, Any]:
        return {"side": self.side, "row": self.row, "column": self.column, "value": str(self.value)}

    @classmethod
    def from_state(cls, state: object) -> TableauLabel:
        if not isinstance(state, dict):
            raise ValueError("expected a tableau label")
        return cls(state.get("side"), state.get("row"), state.get("column"),
                   _integer(state.get("value"), "tableau label"))


@dataclass(frozen=True)
class PairTerm:
    """One editable pair with an exact coefficient and admissibility threshold."""

    barred: tuple[int, ...] = ()
    unbarred: tuple[int, ...] = ()
    coefficient: int | Fraction | SymbolicCoefficient = 1
    n0: int = 0
    labels: tuple[TableauLabel, ...] = ()
    singleton: bool = False

    def __post_init__(self) -> None:
        for partition in (self.barred, self.unbarred):
            if not isinstance(partition, tuple):
                raise ValueError("partitions must be tuples")
            _partition(list(partition))
        try:
            coefficient = as_symbolic(self.coefficient)
        except TypeError as exc:
            raise ValueError("coefficient must be an exact symbolic coefficient") from exc
        if type(self.n0) is not int:
            raise ValueError("N0 must be an integer")
        object.__setattr__(self, "coefficient", coefficient)
        if self.n0 < len(self.barred) + len(self.unbarred):
            raise ValueError("N0 cannot be smaller than the total number of rows")
        if not isinstance(self.labels, tuple) or any(not isinstance(label, TableauLabel) for label in self.labels):
            raise ValueError("labels must be a tuple of TableauLabel values")
        if type(self.singleton) is not bool or (self.singleton and (self.barred or self.unbarred)):
            raise ValueError("a singleton must be an empty pair")
        occupied = set()
        for label in self.labels:
            rows = self.barred if label.side == "barred" else self.unbarred
            if label.row >= len(rows) or label.column >= rows[label.row]:
                raise ValueError("tableau labels must refer to existing cells")
            key = (label.side, label.row, label.column)
            if key in occupied:
                raise ValueError("a cell cannot contain duplicate tableau labels")
            occupied.add(key)

    def state(self) -> dict[str, Any]:
        state: dict[str, Any] = {"kind": "pair", "barred": list(self.barred),
                "unbarred": list(self.unbarred), "coefficient": self.coefficient.latex(),
                "n0": str(self.n0)}
        if self.singleton:
            state["singleton"] = True
        if self.labels:
            state["labels"] = [label.state() for label in self.labels]
        return state

    @classmethod
    def from_state(cls, state: object) -> PairTerm:
        if not isinstance(state, dict) or state.get("kind") != "pair":
            raise ValueError("expected a pair term")
        labels = state.get("labels", [])
        if not isinstance(labels, list):
            raise ValueError("tableau labels must be a list")
        coefficient = state.get("coefficient")
        if not isinstance(coefficient, str):
            raise ValueError("coefficient must be a symbolic-expression string")
        return cls(_partition(state.get("barred")), _partition(state.get("unbarred")),
                   parse_symbolic(coefficient),
                   _integer(state.get("n0"), "N0"),
                   tuple(TableauLabel.from_state(label) for label in labels),
                   state.get("singleton", False))

    def native(self) -> Any:
        """Return the standalone representation shape, without tableau annotations."""
        from .representations import pair_backend

        return pair_backend().Pair((self.barred, self.unbarred), inherited_N0=self.n0)

    def drawing(self) -> dict[str, Any]:
        """Reuse standalone SVG geometry without performing multiplication."""
        from .representations import pair_backend

        drawing = pair_backend().draw_pair(self.native()).as_dict()
        width = self.barred[0] if self.barred else 0
        labels = {}
        for label in self.labels:
            row, column = ((len(self.unbarred) + len(self.barred) - 1 - label.row,
                            width - 1 - label.column) if label.side == "barred"
                           else (label.row, width + label.column))
            labels[(row, column)] = label
        for cell in drawing["cells"]:
            label = labels.get((cell["row"], cell["column"]))
            if label is not None:
                cell["bullet"] = False
                cell["labels"] = [{"text": str(label.value), "barred": label.side == "barred"}]
        return drawing


@dataclass(frozen=True)
class PairExpression:
    """An ordered edit document, optionally containing unevaluated syntax."""

    terms: tuple[PairTerm, ...] = (PairTerm(),)
    # Empty syntax retains the legacy implicit direct sum. Unbalanced brackets
    # are allowed while editing; evaluation must parse and validate the document.
    syntax: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.terms, tuple) or any(
            not isinstance(term, PairTerm) for term in self.terms
        ):
            raise ValueError("a pair expression requires a tuple of pair terms")
        if not isinstance(self.syntax, tuple) or any(
            token not in ("pair", "sum", "tensor", "(", ")") for token in self.syntax
        ):
            raise ValueError("invalid pair expression syntax")
        if self.syntax and self.syntax.count("pair") != len(self.terms):
            raise ValueError("syntax must reference each pair exactly once")

    def state(self) -> dict[str, Any]:
        state = {"version": 1, "kind": "sum", "terms": [term.state() for term in self.terms]}
        if self.syntax:
            state["syntax"] = list(self.syntax)
        return state

    @classmethod
    def from_state(cls, state: object) -> PairExpression:
        if (not isinstance(state, dict) or type(state.get("version")) is not int
                or state.get("version") != 1 or state.get("kind") != "sum"
                or not isinstance(state.get("terms"), list)):
            raise ValueError("expected a version 1 pair sum")
        syntax = state.get("syntax", [])
        if not isinstance(syntax, list):
            raise ValueError("syntax must be a list")
        return cls(tuple(PairTerm.from_state(term) for term in state["terms"]), tuple(syntax))

    def to_native_terms(self) -> tuple[tuple[Any, SymbolicCoefficient], ...]:
        """Return native labels and exact coefficients without collecting terms."""
        direct_sum = tuple(token for i in range(len(self.terms))
                           for token in (("sum", "pair") if i else ("pair",)))
        if self.syntax and self.syntax != direct_sum:
            raise ValueError("bracketed and tensor expressions must be evaluated before exporting a sum")
        return tuple((term.native(), term.coefficient) for term in self.terms)
