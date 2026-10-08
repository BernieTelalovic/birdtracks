"""Standard Young tableaux for ordinary and barred representation shapes."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import prod
from typing import Any, Iterable

from .permutations import Permutation
from .projectors import Antisymmetriser, Projector, Symmetriser
from .representations import pair_backend


@dataclass(frozen=True, slots=True)
class Tableau:
    """An immutable standard Young tableau.

    ``rows`` uses the usual top-to-bottom, left-to-right Young-diagram layout.
    ``barred`` records whether the input representation was contravariant; it
    does not change the ordering rules for the entries.
    """

    rows: tuple[tuple[int, ...], ...]
    barred: bool = False

    @property
    def partition(self) -> tuple[int, ...]:
        """Return the underlying Young-diagram partition."""
        return tuple(len(row) for row in self.rows)

    @property
    def row_word(self) -> tuple[int, ...]:
        """Return entries read left-to-right, one row at a time."""
        return tuple(value for row in self.rows for value in row)

    @property
    def column_word(self) -> tuple[int, ...]:
        """Return entries read top-to-bottom, one column at a time."""
        width = self.partition[0] if self.rows else 0
        return tuple(
            self.rows[row][column]
            for column in range(width)
            for row in range(len(self.rows))
            if column < len(self.rows[row])
        )


def _shape(diagram: Any) -> tuple[tuple[int, ...], bool]:
    backend = pair_backend()
    if not isinstance(diagram, backend.YoungDiagram):
        raise TypeError("diagram must be a pair_multiplication YoungDiagram or Pair")

    if isinstance(diagram, backend.Pair):
        barred, unbarred = diagram.partition
        if barred and unbarred:
            raise ValueError("tableaux require a Pair with only one nonempty part")
        if barred:
            return tuple(map(int, barred)), True
        if unbarred:
            return tuple(map(int, unbarred)), False
        raise ValueError("tableaux require a Pair with one nonempty part")

    return tuple(map(int, diagram.partition)), bool(diagram.barred)


def _rows_from_word(
    partition: tuple[int, ...], word: tuple[int, ...], *, by_column: bool
) -> tuple[tuple[int, ...], ...]:
    size = sum(partition)
    if len(word) != size or set(word) != set(range(1, size + 1)):
        raise ValueError(f"tableau entries must be exactly the integers 1 through {size}")

    cells = (
        ((row, column) for column in range(partition[0] if partition else 0)
         for row, length in enumerate(partition) if column < length)
        if by_column
        else ((row, column) for row, length in enumerate(partition)
              for column in range(length))
    )
    mutable = [[0] * length for length in partition]
    for (row, column), value in zip(cells, word, strict=True):
        mutable[row][column] = value
    rows = tuple(tuple(row) for row in mutable)
    if any(a >= b for row in rows for a, b in zip(row, row[1:])) or any(
        rows[row][column] >= rows[row + 1][column]
        for row in range(len(rows) - 1)
        for column in range(partition[row + 1])
    ):
        raise ValueError("tableau entries must increase across rows and down columns")
    return rows


def tableau(
    diagram: Any,
    *,
    row_word: Iterable[int] | None = None,
    column_word: Iterable[int] | None = None,
) -> Tableau:
    """Create a standard tableau from exactly one row or column word."""
    if (row_word is None) == (column_word is None):
        raise ValueError("supply exactly one of row_word or column_word")
    partition, barred = _shape(diagram)
    try:
        word = tuple(row_word if row_word is not None else column_word)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError("the tableau word must be an iterable of integers") from exc
    if any(isinstance(value, bool) or not isinstance(value, int) for value in word):
        raise TypeError("tableau entries must be integers")
    return Tableau(
        _rows_from_word(partition, word, by_column=column_word is not None), barred
    )


def standard_tableaux(diagram: Any) -> tuple[Tableau, ...]:
    """Return all standard tableaux of ``diagram`` in row-word order."""
    partition, barred = _shape(diagram)
    size = sum(partition)
    rows = [[0] * length for length in partition]
    result: list[Tableau] = []

    def fill(value: int) -> None:
        if value > size:
            result.append(Tableau(tuple(tuple(row) for row in rows), barred))
            return
        for row, length in enumerate(partition):
            for column in range(length):
                if rows[row][column]:
                    continue
                if column and not rows[row][column - 1]:
                    continue
                if row and column < partition[row - 1] and not rows[row - 1][column]:
                    continue
                rows[row][column] = value
                fill(value + 1)
                rows[row][column] = 0

    fill(1)
    return tuple(result)


def mold_projector(value: Tableau) -> Projector:
    """Construct the normalized Hermitian MOLD projector of ``value``.

    This implements Theorem 5 of Alcock-Zeilinger and Weigert,
    *Compact Hermitian Young Projection Operators* (arXiv:1610.10088v2).
    Products act right-to-left as elsewhere in :mod:`birdtracks`; the returned
    node sequence is palindromic, making Hermiticity explicit.
    """
    if not isinstance(value, Tableau):
        raise TypeError("mold_projector expects a Tableau")
    _validate_standard_rows(value.rows)

    ancestors = [_ancestor(value.rows, generation) for generation in range(
        sum(map(len, value.rows)) + 1
    )]
    mold = next(
        generation
        for generation, rows in enumerate(ancestors)
        if _lexical_kind(rows) is not None
    )
    lexical_kind = _lexical_kind(ancestors[mold])
    assert lexical_kind is not None

    outer_type = Symmetriser if lexical_kind == "row" else Antisymmetriser
    inner_type = outer_type if mold % 2 == 0 else _opposite(outer_type)
    left_groups = [
        _young_set(ancestors[generation], (
            outer_type if (mold - generation) % 2 == 0
            else _opposite(outer_type)
        ))
        for generation in range(mold, 0, -1)
    ]
    center_left = _young_set(value.rows, inner_type)
    center_middle = _young_set(value.rows, _opposite(inner_type))
    left = tuple(node for group in left_groups for node in group) + center_left
    nodes = left + center_middle + tuple(reversed(left))

    raw = Projector(nodes)
    identity_coefficient = raw.collapse().terms.get(Permutation.identity(), Fraction())
    if not identity_coefficient:
        raise ValueError("MOLD construction unexpectedly produced the zero operator")
    # A primitive idempotent of shape lambda has identity coefficient
    # f^lambda / n! = 1 / (product of hook lengths).  Comparing that with the
    # raw MOLD operator determines beta exactly without squaring the operator.
    coefficient = Fraction(1, _hook_product(value.partition)) / identity_coefficient
    return coefficient * raw


def _validate_standard_rows(rows: tuple[tuple[int, ...], ...]) -> None:
    partition = tuple(map(len, rows))
    if any(not length for length in partition) or any(
        left < right for left, right in zip(partition, partition[1:])
    ):
        raise ValueError("tableau rows must have Young-diagram shape")
    word = tuple(entry for row in rows for entry in row)
    if any(isinstance(entry, bool) or not isinstance(entry, int) for entry in word):
        raise TypeError("tableau entries must be integers")
    if set(word) != set(range(1, len(word) + 1)):
        raise ValueError("tableau entries must be exactly the integers 1 through its size")
    if any(a >= b for row in rows for a, b in zip(row, row[1:])) or any(
        rows[row][column] >= rows[row + 1][column]
        for row in range(len(rows) - 1)
        for column in range(len(rows[row + 1]))
    ):
        raise ValueError("tableau entries must increase across rows and down columns")


def _ancestor(
    rows: tuple[tuple[int, ...], ...], generation: int
) -> tuple[tuple[int, ...], ...]:
    maximum = sum(map(len, rows)) - generation
    return tuple(filtered for row in rows if (filtered := tuple(
        entry for entry in row if entry <= maximum
    )))


def _lexical_kind(rows: tuple[tuple[int, ...], ...]) -> str | None:
    size = sum(map(len, rows))
    lexical = tuple(range(1, size + 1))
    row_word = tuple(entry for row in rows for entry in row)
    if row_word == lexical:
        return "row"
    width = len(rows[0]) if rows else 0
    column_word = tuple(
        rows[row][column]
        for column in range(width)
        for row in range(len(rows))
        if column < len(rows[row])
    )
    return "column" if column_word == lexical else None


def _young_set(
    rows: tuple[tuple[int, ...], ...],
    operator: type[Symmetriser] | type[Antisymmetriser],
) -> tuple[Symmetriser | Antisymmetriser, ...]:
    if operator is Symmetriser:
        supports = rows
    else:
        width = len(rows[0]) if rows else 0
        supports = tuple(
            tuple(rows[row][column] for row in range(len(rows))
                  if column < len(rows[row]))
            for column in range(width)
        )
    return tuple(operator(support) for support in supports if len(support) > 1)


def _opposite(
    operator: type[Symmetriser] | type[Antisymmetriser],
) -> type[Symmetriser] | type[Antisymmetriser]:
    return Antisymmetriser if operator is Symmetriser else Symmetriser


def _hook_product(partition: tuple[int, ...]) -> int:
    return prod(
        length - column + sum(other > column for other in partition[row + 1:])
        for row, length in enumerate(partition)
        for column in range(length)
    )
