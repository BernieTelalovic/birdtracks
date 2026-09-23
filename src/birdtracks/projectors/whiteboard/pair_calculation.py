"""Parse and evaluate pair expressions embedded in whiteboard source."""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Mapping

from ...pair_evaluation import evaluate
from ...young_diagrams import PairExpression, PairTerm
from ...symbolic import SymbolicCoefficient, as_symbolic, parse_symbolic


_PAIR_MARKER = re.compile(r"\\pair\b(?!\s*\{)")
_ASSIGNMENT = re.compile(r"^\s*(?P<name>\S+?)\s*(?:\\def\b|:=)")
_NUMBER = re.compile(r"\d+")
_PAIR_TOKEN = re.compile(r"PAIR(?P<index>\d+)")
_PAIR_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_ADJACENT_PREFACTOR = re.compile(
    r"(?<![A-Za-z0-9_.])(?P<coefficient>\d+)(?:_(?P<n0>\d+))?\s*$"
)


@dataclass(frozen=True)
class _Node:
    kind: str
    children: tuple[_Node, ...] = ()
    expression: PairExpression | None = None
    coefficient: SymbolicCoefficient = SymbolicCoefficient(1)
    n0: int = 1


def pair_expression_from_blocks(
    blocks: tuple[Mapping[str, object], ...] | list[Mapping[str, object]],
    explicit_pairs: Mapping[str, object],
    definitions: Mapping[str, PairExpression] | None = None,
) -> PairExpression:
    """Build one exact pair expression from connected whiteboard blocks."""

    marker_expressions: list[PairExpression] = []
    sources: list[str] = []
    for block in blocks:
        source = str(block.get("source") or "")
        if source.lstrip().startswith("&"):
            source = source.lstrip()[1:]
        occurrence = 0

        def replace_marker(match: re.Match[str]) -> str:
            nonlocal occurrence
            key = f"{block.get('id', '')}:pair:{occurrence}"
            occurrence += 1
            editor = explicit_pairs.get(key)
            value = getattr(editor, "pair_expression", None)
            if value is None:
                value = getattr(editor, "_pair_expression", None)
            try:
                expression = (
                    value
                    if isinstance(value, PairExpression)
                    else PairExpression.from_state(value)
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(f"pair marker {key!r} has no valid saved value") from exc
            prefactor = pair_prefactor_before(source, match.start())
            if prefactor is not None:
                expression = _remove_embedded_prefactor(expression, prefactor)
            marker_expressions.append(expression)
            return f"PAIR{len(marker_expressions) - 1}"

        sources.append(_PAIR_MARKER.sub(replace_marker, source))

    source = " ".join(sources)
    assignment = _ASSIGNMENT.match(source)
    if assignment:
        source = source[assignment.end():]
    if re.search(r"\\birdtracks\b", source):
        raise NotImplementedError(
            "operations mixing pairs and birdtracks are not implemented"
        )
    if "+" in source or "-" in source:
        raise NotImplementedError(
            "adding or subtracting scalars and pairs is not implemented; "
            "use \\\\oplus for pair direct sums"
        )
    parser = _PairSourceParser(source, marker_expressions, definitions or {})
    node = parser.parse()
    terms, syntax = _as_parts(node)
    return PairExpression(tuple(terms), tuple(syntax))


def pair_prefactor_before(
    source: str,
    marker_start: int,
) -> tuple[int, int] | None:
    """Return an adjacent integer coefficient and optional N0 subscript."""

    end = marker_start
    while end > 0 and source[end - 1].isspace():
        end -= 1
    match = _ADJACENT_PREFACTOR.search(source[:end])
    if match is None:
        return None
    return int(match.group("coefficient")), int(match.group("n0") or 1)


def pair_expression_with_prefactor(
    source: str,
    marker_start: int,
) -> PairExpression:
    """Create the default embedded pair expression for an adjacent prefix."""

    expression = PairExpression()
    prefactor = pair_prefactor_before(source, marker_start)
    if prefactor is None:
        return expression
    coefficient, n0 = prefactor
    return PairExpression((
        replace(expression.terms[0], coefficient=coefficient, n0=n0),
    ))


def pair_expression_with_updated_prefactor(
    expression: PairExpression,
    source: str,
    marker_start: int,
) -> PairExpression:
    """Apply an adjacent source prefactor to an existing embedded pair."""

    prefactor = pair_prefactor_before(source, marker_start)
    if prefactor is None or not expression.terms:
        return expression
    coefficient, n0 = prefactor
    first = expression.terms[0]
    n0 = max(n0, len(first.barred) + len(first.unbarred))
    if first.coefficient == coefficient and first.n0 == n0:
        return expression
    return PairExpression(
        (replace(first, coefficient=coefficient, n0=n0), *expression.terms[1:]),
        expression.syntax,
    )


def _remove_embedded_prefactor(
    expression: PairExpression,
    prefactor: tuple[int, int],
) -> PairExpression:
    coefficient, n0 = prefactor
    terms = []
    for term in expression.terms:
        if term.coefficient != coefficient or term.n0 < n0:
            terms.append(term)
            continue
        inherent_n0 = len(term.barred) + len(term.unbarred)
        terms.append(replace(term, coefficient=1, n0=inherent_n0))
    return PairExpression(tuple(terms), expression.syntax)


class _PairSourceParser:
    def __init__(
        self,
        source: str,
        marker_expressions: list[PairExpression],
        definitions: Mapping[str, PairExpression | SymbolicCoefficient],
    ) -> None:
        self.source = source
        self.marker_expressions = marker_expressions
        self.definitions = definitions
        self.index = 0

    def parse(self) -> _Node:
        if not self.source.strip():
            return _Node("empty")
        result = self._sum()
        self._spaces()
        if self.index != len(self.source):
            raise ValueError(f"unexpected pair expression text at {self.index}")
        return result

    def _sum(self) -> _Node:
        children = [self._tensor()]
        while True:
            self._spaces()
            if not self._take(r"\oplus"):
                return _join("sum", children)
            children.append(self._tensor())

    def _tensor(self) -> _Node:
        children = [self._factor()]
        while True:
            before = self.index
            self._spaces()
            if self._take(r"\otimes"):
                children.append(self._factor())
                continue
            if self._take(r"\times"):
                children.append(self._factor())
                continue
            if self._starts_factor():
                children.append(self._factor())
                continue
            self.index = before
            return _join("tensor", children)

    def _factor(self) -> _Node:
        self._spaces()
        if self._take("("):
            value = self._sum()
            self._spaces()
            if not self._take(")"):
                raise ValueError("missing closing bracket ')' in pair expression")
            return value
        marker = _PAIR_TOKEN.match(self.source, self.index)
        if marker:
            self.index = marker.end()
            index = int(marker.group("index"))
            try:
                return _Node("pair", expression=self.marker_expressions[index])
            except IndexError as exc:
                raise ValueError("pair marker count does not match source") from exc
        number = _NUMBER.match(self.source, self.index)
        if number:
            self.index = number.end()
            n0 = 1
            if self._take("_"):
                subscript = _NUMBER.match(self.source, self.index)
                if subscript is None:
                    raise ValueError("a pair prefactor subscript must be an integer")
                self.index = subscript.end()
                n0 = int(subscript.group())
            return _Node("scalar", coefficient=SymbolicCoefficient(int(number.group())), n0=n0)
        name = _PAIR_NAME.match(self.source, self.index)
        if name:
            candidates = sorted(self.definitions, key=len, reverse=True)
            for candidate in candidates:
                if not self.source.startswith(candidate, self.index):
                    continue
                end = self.index + len(candidate)
                if end < len(self.source) and re.match(
                    r"[A-Za-z0-9_]", self.source[end]
                ):
                    continue
                self.index = end
                defined = self.definitions[candidate]
                return (_Node("pair", expression=defined)
                        if isinstance(defined, PairExpression)
                        else _Node("scalar", coefficient=defined))
            raise ValueError(f"unknown pair symbol {name.group()!r}")
        raise ValueError(f"expected a pair or scalar at {self.index}")

    def _starts_factor(self) -> bool:
        self._spaces()
        return (
            self.source.startswith("PAIR", self.index)
            or self.source.startswith("(", self.index)
            or self.index < len(self.source) and self.source[self.index].isdigit()
            or self.index < len(self.source) and self.source[self.index].isalpha()
        )

    def _take(self, text: str) -> bool:
        if self.source.startswith(text, self.index):
            self.index += len(text)
            return True
        return False

    def _spaces(self) -> None:
        while self.index < len(self.source) and self.source[self.index].isspace():
            self.index += 1


def _group_blocks(
    blocks: tuple[Mapping[str, object], ...] | list[Mapping[str, object]],
) -> list[list[Mapping[str, object]]]:
    groups: list[list[Mapping[str, object]]] = []
    for block in blocks:
        line_id = str(block.get("line_id") or block.get("id") or "")
        if groups:
            previous_id = str(
                groups[-1][0].get("line_id") or groups[-1][0].get("id") or ""
            )
            if previous_id == line_id:
                groups[-1].append(block)
                continue
        groups.append([block])
    return groups


def _latest_pair_result(group: list[Mapping[str, object]]) -> PairExpression | None:
    candidates = [
        block for block in group
        if isinstance(block.get("pair_calculation"), dict)
        and isinstance(block["pair_calculation"].get("result"), dict)  # type: ignore[index]
    ]
    if not candidates:
        return None
    latest = max(candidates, key=lambda block: int(block.get("calculation_step", 0)))
    state = latest["pair_calculation"]["result"]  # type: ignore[index]
    try:
        return PairExpression.from_state(state)
    except (TypeError, ValueError):
        return None


def pair_definitions_before(
    blocks: tuple[Mapping[str, object], ...] | list[Mapping[str, object]],
    explicit_pairs: Mapping[str, object],
    target_group: str,
    initial_definitions: Mapping[str, PairExpression] | None = None,
) -> dict[str, PairExpression]:
    """Resolve pair definitions appearing before one whiteboard line group."""

    definitions = dict(initial_definitions or {})
    for group in _group_blocks(blocks):
        group_id = str(group[0].get("line_id") or group[0].get("id") or "")
        if group_id == target_group:
            break
        _add_pair_definition(group, explicit_pairs, definitions)
    return definitions


def pair_definitions(
    blocks: tuple[Mapping[str, object], ...] | list[Mapping[str, object]],
    explicit_pairs: Mapping[str, object],
    initial_definitions: Mapping[str, PairExpression] | None = None,
) -> dict[str, PairExpression]:
    """Resolve all pair definitions in document order."""

    definitions = dict(initial_definitions or {})
    for group in _group_blocks(blocks):
        _add_pair_definition(group, explicit_pairs, definitions)
    return definitions


def _add_pair_definition(
    group: list[Mapping[str, object]],
    explicit_pairs: Mapping[str, object],
    definitions: dict[str, PairExpression],
) -> None:
    source = str(group[0].get("source") or "")
    assignment = _ASSIGNMENT.match(source)
    if assignment is None:
        return
    latest = _latest_pair_result(group)
    if latest is not None:
        definitions[assignment.group("name")] = latest
        return
    inputs = [block for block in group if "calculation_step" not in block]
    try:
        value = pair_expression_from_blocks(inputs, explicit_pairs, definitions)
    # Definitions are rescanned on every keystroke.  An ordinary `+` or `-`
    # in an unfinished non-pair assignment is just ordinary whiteboard text;
    # keep it out of the pair parser until the line contains an actual pair.
    except (TypeError, ValueError, LookupError, NotImplementedError):
        return
    definitions[assignment.group("name")] = value


def pair_source_uses_definitions(
    source: str,
    definitions: Mapping[str, PairExpression],
) -> bool:
    """Return whether source contains a known pair variable reference."""

    for name in sorted(definitions, key=len, reverse=True):
        for match in re.finditer(re.escape(name), source):
            before = source[match.start() - 1] if match.start() else ""
            after = source[match.end()] if match.end() < len(source) else ""
            if before and (before.isalnum() or before in "_\\"):
                continue
            if after and (after.isalnum() or after == "_"):
                continue
            return True
    return False


def _join(kind: str, children: list[_Node]) -> _Node:
    if len(children) == 1:
        return children[0]
    return _Node(kind, tuple(children))


def _as_parts(node: _Node, parent: str | None = None) -> tuple[list[PairTerm], list[str]]:
    if node.kind == "empty":
        return [], []
    if node.kind == "pair":
        assert node.expression is not None
        terms = [replace(term, n0=max(term.n0, 1)) for term in node.expression.terms]
        if node.expression.syntax:
            syntax = list(node.expression.syntax)
        else:
            syntax = [
                token
                for index in range(len(terms))
                for token in (("sum", "pair") if index else ("pair",))
            ]
        if parent == "tensor" and "sum" in syntax:
            syntax = ["(", *syntax, ")"]
        return terms, syntax
    if node.kind == "scalar":
        raise ValueError("a pair expression must contain at least one pair")
    if node.kind == "tensor" and any(child.kind == "scalar" for child in node.children):
        coefficient = SymbolicCoefficient(1)
        n0 = 1
        remaining: list[_Node] = []
        for child in node.children:
            if child.kind == "scalar":
                coefficient *= child.coefficient
                n0 = max(n0, child.n0)
            else:
                remaining.append(child)
        if not remaining:
            raise ValueError("a pair expression must contain at least one pair")
        if len(remaining) == 1:
            terms, syntax = _as_parts(remaining[0], parent)
        else:
            terms, syntax = _as_parts(_Node("tensor", tuple(remaining)), parent)
        return [
            replace(term, coefficient=term.coefficient * coefficient, n0=max(term.n0, n0))
            for term in terms
        ], syntax

    terms: list[PairTerm] = []
    syntax: list[str] = []
    for index, child in enumerate(node.children):
        if index:
            syntax.append(node.kind)
        child_terms, child_syntax = _as_parts(child, node.kind)
        if node.kind == "tensor" and child.kind == "sum":
            syntax.append("(")
            syntax.extend(child_syntax)
            syntax.append(")")
        else:
            syntax.extend(child_syntax)
        terms.extend(child_terms)
    return terms, syntax


def evaluate_pair_blocks(
    blocks: tuple[Mapping[str, object], ...] | list[Mapping[str, object]],
    explicit_pairs: Mapping[str, object],
    definitions: Mapping[str, PairExpression] | None = None,
) -> dict[str, object]:
    """Evaluate pair source and return the existing staged Python calculation."""

    expression = pair_expression_from_blocks(blocks, explicit_pairs, definitions)
    assignment = _ASSIGNMENT.match(str(blocks[0].get("source") or "")) if blocks else None
    return evaluate(
        expression,
        leading_equals=True,
        leading_assignment=assignment.group("name") if assignment else None,
    )


__all__ = [
    "evaluate_pair_blocks",
    "pair_definitions",
    "pair_definitions_before",
    "pair_expression_from_blocks",
    "pair_expression_with_prefactor",
    "pair_expression_with_updated_prefactor",
    "pair_prefactor_before",
    "pair_source_uses_definitions",
]
