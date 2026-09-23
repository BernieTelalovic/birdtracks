"""Exact projector calculations for whiteboard source blocks."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
import re

from ...linear_combinations import (
    DimensionPolynomial,
    PermutationSum,
    PolynomialPermutationSum,
)
from ..projector import Projector
from ..projector_sum import ProjectorSum
from ...symbolic import SymbolicCoefficient, as_symbolic
from .engine import EvaluationEnvironment
from .projector_backend import projector_backend


_ASSIGNMENT = re.compile(r"^\s*(?P<name>\S+?)\s*(?P<operator>\\def\b|:=)")
_NUMBER = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)")
_TOKEN_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")

ProjectorExpressionValue = Projector | ProjectorSum

@dataclass(frozen=True, slots=True)
class SymbolicProjectorSum:
    """Projector terms whose commuting prefactors belong to the symbolic domain."""

    terms: tuple[tuple[Projector, SymbolicCoefficient], ...]


ExpressionValue = ProjectorExpressionValue | DimensionPolynomial | SymbolicCoefficient | SymbolicProjectorSum


@dataclass(frozen=True, slots=True)
class BackendTerm:
    """One exact projector value replacing a source symbol in the display."""

    block_id: str
    start: int
    end: int
    value: Projector


def evaluate_projector_expression(
    blocks: Iterable[Mapping[str, object]],
    explicit_projectors: Mapping[str, object],
    environment: EvaluationEnvironment[object],
) -> ExpressionValue:
    """Translate a whiteboard expression into an exact algebraic value.

    Names are matched as the longest known environment symbol, so adjacent
    names such as ``A_2 B_1`` become an ordered product.  Parentheses,
    brackets, and braces are ordinary grouping delimiters.  ``\tr`` applies
    to the next atom or to the complete bracketed expression following it.
    """

    source_blocks = tuple(blocks)
    source_parts: list[str] = []
    projector_values: list[Projector] = []
    for block in source_blocks:
        source = str(block.get("source") or "").lstrip()
        if source.startswith("&"):
            source = source[1:]
        source_parts.append(source)
        block_id = str(block.get("id") or "")
        occurrence = 0
        for _match in re.finditer(r"\\birdtracks\b", source):
            key = f"{block_id}:projector:{occurrence}"
            editor = explicit_projectors.get(key)
            value = getattr(editor, "_configured_projector", None)
            if not isinstance(value, Projector):
                raise ValueError(f"projector marker {key!r} has no saved value")
            projector_values.append(value)
            occurrence += 1

    assignment = _ASSIGNMENT.match(source_parts[0]) if source_parts else None
    if assignment:
        source_parts[0] = source_parts[0][assignment.end():]
    source = " ".join(source_parts)
    return _ExpressionParser(source, projector_values, environment).parse()


class _ExpressionParser:
    def __init__(
        self,
        source: str,
        projector_values: list[Projector],
        environment: EvaluationEnvironment[object],
    ) -> None:
        self.source = source
        self.projector_values = projector_values
        self.environment = environment
        self.index = 0
        self.projector_index = 0

    def parse(self) -> ExpressionValue:
        value = self._sum()
        self._spaces()
        if self.index != len(self.source):
            raise ValueError(f"unexpected expression text at {self.index}")
        return value

    def _sum(self) -> ExpressionValue:
        value = self._product()
        while True:
            self._spaces()
            if self._take("+"):
                value = _add_values(value, self._product())
            elif self._take("-"):
                value = _add_values(value, _scale_value(self._product(), -1))
            else:
                return value

    def _product(self) -> ExpressionValue:
        value = self._power()
        while True:
            before = self.index
            self._spaces()
            if self._take(r"\times") or self._take("*"):
                value = _multiply_values(value, self._power())
                continue
            if self._take("/"):
                divisor = self._power()
                if not isinstance(divisor, SymbolicCoefficient):
                    raise ValueError("only scalar expressions can be divisors")
                value = _multiply_values(value, divisor ** -1)
                continue
            if self._starts_factor():
                value = _multiply_values(value, self._power())
                continue
            self.index = before
            return value

    def _power(self) -> ExpressionValue:
        value = self._factor()
        self._spaces()
        if not self._take("^"):
            return value
        self._spaces()
        braced = self._take("{")
        match = re.match(r"-?\d+", self.source[self.index:])
        if match is None:
            raise ValueError("a power must be an integer")
        self.index += match.end()
        if braced and not self._take("}"):
            raise ValueError("missing closing power brace")
        if not isinstance(value, SymbolicCoefficient):
            raise ValueError("powers are only supported for scalar expressions")
        return value ** int(match.group())

    def _factor(self) -> ExpressionValue:
        self._spaces()
        if self._take("+"):
            return self._factor()
        if self._take("-"):
            return _scale_value(self._factor(), -1)
        number = re.match(
            rf"(?P<top>{_NUMBER.pattern})(?:\s*/\s*(?P<bottom>{_NUMBER.pattern}))?",
            self.source[self.index:],
        )
        if self.source.startswith(r"\frac", self.index):
            self.index += len(r"\frac")
            numerator_value = self._braced_scalar()
            denominator_value = self._braced_scalar()
            scalar = numerator_value / denominator_value
            exact_scalar = scalar.as_fraction()
            multiplier: Fraction | SymbolicCoefficient = (
                exact_scalar if exact_scalar is not None else scalar
            )
            self._spaces()
            if self._take(r'\times') or self._take('*') or self._starts_factor():
                return _scale_value(self._power(), multiplier)
            return scalar
        if number:
            self.index += number.end()
            numerator = number.group('top')
            denominator = number.group('bottom') or '1'
            if not Fraction(Decimal(denominator)):
                raise ValueError('a coefficient denominator cannot be zero')
            scalar = Fraction(Decimal(numerator)) / Fraction(Decimal(denominator))
            self._spaces()
            if self._take(r'\times') or self._take('*') or self._starts_factor():
                return _scale_value(self._factor(), scalar)
            return SymbolicCoefficient(scalar)
        if self.source.startswith(r"\tr", self.index):
            self.index += 3
            return _trace_value(self._factor())
        opening = self._group_opening()
        if opening is not None:
            closing = {"(": ")", "[": "]", "{": "}"}[opening]
            value = self._sum()
            self._spaces()
            sized = self._take(r"\right")
            if sized:
                self._spaces()
            if not self._take(closing):
                raise ValueError(f"missing closing bracket {closing!r}")
            return value
        if self.source.startswith(r"\birdtracks", self.index):
            match = re.match(
                r"\\birdtracks\b", self.source[self.index:]
            )
            if not match:
                raise ValueError("invalid projector expression")
            self.index += match.end()
            try:
                value = self.projector_values[self.projector_index]
            except IndexError as exc:
                raise ValueError("projector marker count does not match source") from exc
            self.projector_index += 1
            return value
        name = self._name()
        if name is None:
            raise ValueError(f"expected an expression at {self.index}")
        try:
            return self.environment.resolve(name)
        except LookupError:
            return SymbolicCoefficient.symbol(name)

    def _name(self) -> str | None:
        self._spaces()
        match = _TOKEN_NAME.match(self.source, self.index)
        if not match:
            return None
        candidates = sorted(
            (definition.name for definition in self.environment.definitions),
            key=len,
            reverse=True,
        )
        for candidate in candidates:
            if self.source.startswith(candidate, self.index):
                self.index += len(candidate)
                return candidate
        self.index = match.end()
        return match.group(0)

    def _starts_factor(self) -> bool:
        self._spaces()
        if self.source.startswith(r"\right", self.index):
            return False
        return self.index < len(self.source) and (
            self.source[self.index].isalpha()
            or self.source[self.index].isdigit()
            or self.source[self.index] == '.'
            or self.source[self.index] in "([{"
            or self.source.startswith("\\", self.index)
        )

    def _group_opening(self) -> str | None:
        """Consume an ordinary or LaTeX-sized grouping delimiter."""

        if self.index < len(self.source) and self.source[self.index] in "([{":
            opening = self.source[self.index]
            self.index += 1
            return opening
        if not self._take(r"\left"):
            return None
        self._spaces()
        if self.index >= len(self.source) or self.source[self.index] not in "([{":
            raise ValueError(r"\left must be followed by (, [, or {")
        opening = self.source[self.index]
        self.index += 1
        return opening

    def _braced_scalar(self) -> SymbolicCoefficient:
        self._spaces()
        if not self._take("{"):
            raise ValueError(r"\frac arguments must be braced")
        value = self._sum()
        self._spaces()
        if not self._take("}"):
            raise ValueError("missing closing fraction brace")
        if not isinstance(value, SymbolicCoefficient):
            raise ValueError(r"\frac arguments must be scalar expressions")
        return value

    def _take(self, text: str) -> bool:
        if self.source.startswith(text, self.index):
            self.index += len(text)
            return True
        return False

    def _spaces(self) -> None:
        while self.index < len(self.source) and self.source[self.index].isspace():
            self.index += 1


def simplify_projector_value(
    value: Projector | ProjectorSum | SymbolicProjectorSum,
) -> ProjectorSum | SymbolicProjectorSum:
    """Apply automatic algebraic simplification without expanding nodes."""

    if isinstance(value, SymbolicProjectorSum):
        symbolic_terms: list[tuple[Projector, SymbolicCoefficient]] = []
        for projector, coefficient in value.terms:
            symbolic_terms.extend(
                (term, coefficient * term_coefficient)
                for term, term_coefficient in projector.simplify().items()
            )
        combined: dict[Projector, SymbolicCoefficient] = {}
        for projector, coefficient in symbolic_terms:
            combined[projector] = combined.get(projector, SymbolicCoefficient()) + coefficient
        return SymbolicProjectorSum(tuple(
            (projector, coefficient) for projector, coefficient in combined.items() if coefficient
        ))
    terms: list[tuple[Projector, Fraction]] = []
    source_terms = (
        ((value, Fraction(1)),)
        if isinstance(value, Projector)
        else tuple(value.items())
    )
    for projector, coefficient in source_terms:
        terms.extend(
            (term, coefficient * term_coefficient)
            for term, term_coefficient in projector.simplify().items()
        )
    return ProjectorSum(terms)


def _as_sum(value: ProjectorExpressionValue) -> ProjectorSum:
    return value if isinstance(value, ProjectorSum) else ProjectorSum((value,))


def _add_values(left: ExpressionValue, right: ExpressionValue) -> ExpressionValue:
    if isinstance(left, SymbolicCoefficient) and isinstance(right, SymbolicCoefficient):
        return left + right
    if isinstance(left, (SymbolicCoefficient, SymbolicProjectorSum)) or isinstance(right, (SymbolicCoefficient, SymbolicProjectorSum)):
        if isinstance(left, SymbolicCoefficient) or isinstance(right, SymbolicCoefficient):
            raise NotImplementedError(
                "adding or subtracting scalars and birdtracks is not implemented"
            )
        return SymbolicProjectorSum((*left.terms, *right.terms))
    if isinstance(left, DimensionPolynomial) and isinstance(right, DimensionPolynomial):
        return left + right
    if isinstance(left, DimensionPolynomial) or isinstance(right, DimensionPolynomial):
        raise NotImplementedError(
            "adding or subtracting scalars and birdtracks is not implemented"
        )
    return _as_sum(left) + _as_sum(right)


def _scale_value(value: ExpressionValue, scalar: int | Fraction | SymbolicCoefficient) -> ExpressionValue:
    if isinstance(value, SymbolicCoefficient):
        return value * scalar
    if isinstance(value, SymbolicProjectorSum):
        return SymbolicProjectorSum(tuple((term, coefficient * scalar) for term, coefficient in value.terms))
    if isinstance(scalar, SymbolicCoefficient):
        return _symbolic_scale(value, scalar)
    if isinstance(value, DimensionPolynomial):
        return value * scalar
    return value * scalar if isinstance(value, Projector) else value * scalar


def _multiply_values(left: ExpressionValue, right: ExpressionValue) -> ExpressionValue:
    if isinstance(left, SymbolicCoefficient) and isinstance(right, SymbolicCoefficient):
        return left * right
    if isinstance(left, SymbolicCoefficient):
        return _symbolic_scale(right, left)
    if isinstance(right, SymbolicCoefficient):
        return _symbolic_scale(left, right)
    if isinstance(left, SymbolicProjectorSum) or isinstance(right, SymbolicProjectorSum):
        left_terms = left.terms if isinstance(left, SymbolicProjectorSum) else _symbolic_terms(left)
        right_terms = right.terms if isinstance(right, SymbolicProjectorSum) else _symbolic_terms(right)
        return SymbolicProjectorSum(tuple(
            (projector_backend.multiply(a, b), x * y)  # type: ignore[arg-type]
            for a, x in left_terms for b, y in right_terms
        ))
    if isinstance(left, DimensionPolynomial) and isinstance(right, DimensionPolynomial):
        return left * right
    if isinstance(left, DimensionPolynomial) or isinstance(right, DimensionPolynomial):
        raise ValueError("a traced scalar cannot be multiplied by an open projector")
    return projector_backend.multiply(left, right)


def _symbolic_terms(value: ExpressionValue) -> tuple[tuple[Projector, SymbolicCoefficient], ...]:
    if isinstance(value, Projector):
        return ((value, SymbolicCoefficient(1)),)
    if isinstance(value, ProjectorSum):
        return tuple((projector, SymbolicCoefficient(coefficient)) for projector, coefficient in value.items())
    raise ValueError("a symbolic scalar can only multiply an open projector")


def _symbolic_scale(value: ExpressionValue, scalar: SymbolicCoefficient) -> SymbolicProjectorSum:
    return SymbolicProjectorSum(tuple((projector, coefficient * scalar) for projector, coefficient in _symbolic_terms(value)))


def _trace_value(value: ExpressionValue) -> DimensionPolynomial | SymbolicCoefficient:
    if isinstance(value, (DimensionPolynomial, SymbolicCoefficient)):
        return value
    if isinstance(value, SymbolicProjectorSum):
        result = SymbolicCoefficient()
        for projector, coefficient in value.terms:
            result += coefficient * _dimension_polynomial_as_symbolic(
                _trace_projector_value(projector)
            )
        return result
    return _trace_projector_value(value)


def _trace_projector_value(
    value: ProjectorExpressionValue,
) -> DimensionPolynomial:
    collapsed = _as_sum(value).trace().collapse()
    if isinstance(collapsed, PolynomialPermutationSum):
        terms = tuple(collapsed)
        if any(permutation for permutation, _coefficient in terms):
            raise AssertionError("a fully traced projector must collapse to a scalar")
        return sum(
            (coefficient for _permutation, coefficient in terms),
            DimensionPolynomial(),
        )
    if isinstance(collapsed, PermutationSum):
        terms = tuple(collapsed)
        if any(permutation for permutation, _coefficient in terms):
            raise AssertionError("a fully traced projector must collapse to a scalar")
        return DimensionPolynomial(
            {0: sum((coefficient for _permutation, coefficient in terms), 0)}
        )
    raise AssertionError("trace collapse returned an unsupported algebraic value")


def _dimension_polynomial_as_symbolic(
    value: DimensionPolynomial,
) -> SymbolicCoefficient:
    dimension = SymbolicCoefficient.symbol("N")
    return sum(
        (SymbolicCoefficient(coefficient) * dimension ** power
         for power, coefficient in value),
        SymbolicCoefficient(),
    )


def dimension_polynomial_source(value: DimensionPolynomial) -> str:
    """Render an exact dimension polynomial as whiteboard LaTeX source."""

    if not value:
        return "0"
    parts: list[str] = []
    for power, coefficient in reversed(tuple(value)):
        magnitude = abs(coefficient)
        if parts:
            parts.append(" - " if coefficient < 0 else " + ")
        elif coefficient < 0:
            parts.append("-")
        variable = "" if power == 0 else "N"
        if power > 1:
            variable += rf"^{{{power}}}"
        if magnitude == 1 and variable:
            scalar = ""
        elif magnitude.denominator == 1:
            scalar = str(magnitude.numerator)
        else:
            scalar = rf"\frac{{{magnitude.numerator}}}{{{magnitude.denominator}}}"
        parts.append(scalar + variable)
    return "".join(parts)


def calculate_projector_blocks(
    blocks: Iterable[Mapping[str, object]],
    explicit_projectors: Mapping[str, object],
    initial_definitions: Mapping[str, object] | None = None,
) -> tuple[EvaluationEnvironment[object], tuple[BackendTerm, ...]]:
    """Evaluate definitions and source references in document order.

    A projector marker is supplied by the embedded editor identified by its
    positional ``block-id:projector:occurrence`` key.  Source references are
    expanded only after a definition has been encountered, which makes a
    definition behave like the ordinary sequential calculator notation.
    """

    source_blocks = tuple(blocks)
    initial = dict(initial_definitions or {})
    assigned_names = {
        match.group("name")
        for block in source_blocks
        if (match := _ASSIGNMENT.match(str(block.get("source") or "")))
    }
    environment: EvaluationEnvironment[object] = EvaluationEnvironment(
        projector_backend
    )
    for name, value in initial.items():
        if name not in assigned_names:
            environment.define(name, value)
    display_terms: list[BackendTerm] = []
    groups: list[list[Mapping[str, object]]] = []
    for block in source_blocks:
        line_id = str(block.get("line_id") or block.get("id") or "")
        if groups and str(groups[-1][0].get("line_id") or groups[-1][0].get("id") or "") == line_id:
            groups[-1].append(block)
        else:
            groups.append([block])

    for group in groups:
        if not group:
            continue
        first_source = str(group[0].get("source") or "")
        assignment = _ASSIGNMENT.match(first_source)
        if assignment:
            name = assignment.group("name")
            rhs_start = assignment.end()
            fallback_terms = _group_terms(
                group,
                rhs_start=rhs_start,
                environment=environment,
                explicit_projectors=explicit_projectors,
                preserve_existing=True,
            )
            if name in initial and (
                not fallback_terms
                or any(block.get("read_only") for block in group)
            ):
                environment.define(name, initial[name])
            else:
                try:
                    value = evaluate_projector_expression(
                        group, explicit_projectors, environment
                    )
                except ValueError:
                    if not fallback_terms:
                        continue
                    if len(fallback_terms) == 1:
                        projector, coefficient = fallback_terms[0]
                        value = projector * coefficient
                    else:
                        value = ProjectorSum(
                            (projector, coefficient)
                            for projector, coefficient in fallback_terms
                        )
                environment.define(name, value)
            continue

        for block in group:
            if block.get("read_only"):
                continue
            source = str(block.get("source") or "")
            for start, end, value in _source_references(source, environment):
                if not _reference_is_explicitly_expanded(source, start):
                    continue
                for projector, coefficient in _value_terms(value):
                    display_terms.append(
                        BackendTerm(
                            str(block.get("id") or ""),
                            start,
                            end,
                            projector * coefficient,
                        )
                    )

    return environment, tuple(display_terms)


def _reference_is_explicitly_expanded(source: str, start: int) -> bool:
    """Only a standalone signed reference requests in-place expansion."""

    prefix = source[:start].rstrip()
    return prefix in {"+", "-"}


def _group_terms(
    group: list[Mapping[str, object]],
    *,
    rhs_start: int,
    environment: EvaluationEnvironment[object],
    explicit_projectors: Mapping[str, object],
    preserve_existing: bool,
) -> list[tuple[Projector, Fraction]]:
    terms: list[tuple[Projector, Fraction]] = []
    for block_index, block in enumerate(group):
        source = str(block.get("source") or "")
        offset = rhs_start if block_index == 0 else 0
        marker_index = 0
        for match in re.finditer(r"\\birdtracks\b", source):
            if match.start() < offset:
                continue
            key = f"{block.get('id', '')}:projector:{marker_index}"
            marker_index += 1
            editor = explicit_projectors.get(key)
            projector = getattr(editor, "_configured_projector", None)
            if preserve_existing and not int(
                getattr(editor, "saved_revision", 0)
            ):
                continue
            if not isinstance(projector, Projector):
                continue
            sign = _sign_before(source, match.start())
            coefficient = sign * _numeric_prefactor(source, match.start())
            terms.append((projector, coefficient))

        reference_start = offset
        for start, end, value in _source_references(
            source[reference_start:], environment
        ):
            for projector, coefficient in _value_terms(value):
                terms.append(
                    (
                        projector,
                        _sign_before(source, reference_start + start) * coefficient,
                    )
                )
    return terms


def _source_references(
    source: str,
    environment: EvaluationEnvironment[object],
) -> tuple[tuple[int, int, object], ...]:
    references: list[tuple[int, int, object]] = []
    for name in sorted(
        (definition.name for definition in environment.definitions),
        key=len,
        reverse=True,
    ):
        start = 0
        while True:
            index = source.find(name, start)
            if index < 0:
                break
            end = index + len(name)
            if _token_boundary(source, index, end):
                references.append((index, end, environment.resolve(name)))
            start = end
    return tuple(
        sorted(references, key=lambda item: (item[0], -(item[1] - item[0])))
    )


def _token_boundary(source: str, start: int, end: int) -> bool:
    before = source[start - 1] if start else ""
    after = source[end] if end < len(source) else ""
    return not (before and (before.isalnum() or before in "_\\")) and not (
        after and (after.isalnum() or after in "_")
    )


def _value_terms(value: object) -> tuple[tuple[Projector, Fraction], ...]:
    if isinstance(value, Projector):
        return ((value, Fraction(1)),)
    if isinstance(value, ProjectorSum):
        return tuple(value.items())
    return ()


def _sign_before(source: str, index: int) -> Fraction:
    prefix = source[:index].rstrip()
    if prefix.endswith("-"):
        return Fraction(-1)
    return Fraction(1)


def _numeric_prefactor(source: str, index: int) -> Fraction:
    prefix = source[:index].rstrip()
    match = re.search(
        rf"(?:^|[+-])\s*(?P<number>{_NUMBER.pattern})\s*$", prefix
    )
    if not match:
        return Fraction(1)
    value = Fraction(Decimal(match.group("number")))
    return value


__all__ = ["BackendTerm", "calculate_projector_blocks"]
