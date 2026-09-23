"""Small exact symbolic coefficient domain for model-layer prefactors."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import gcd, lcm
import re

Monomial = tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class Polynomial:
    """Immutable sparse multivariate polynomial with rational coefficients."""

    terms: tuple[tuple[Monomial, Fraction], ...] = ()

    def __init__(self, terms: object = 0) -> None:
        if isinstance(terms, Polynomial):
            object.__setattr__(self, "terms", terms.terms)
            return
        if isinstance(terms, str):
            data = {((terms, 1),): Fraction(1)}
        elif isinstance(terms, (int, Fraction)) and not isinstance(terms, bool):
            data = {(): Fraction(terms)} if terms else {}
        else:
            data = dict(terms)  # type: ignore[arg-type]
        cleaned = tuple(sorted(
            ((tuple((name, power) for name, power in monomial if power), Fraction(value))
             for monomial, value in data.items() if value),
            key=lambda item: item[0],
        ))
        object.__setattr__(self, "terms", cleaned)

    def __bool__(self) -> bool:
        return bool(self.terms)

    def __add__(self, other: object) -> Polynomial:
        other = Polynomial(other)
        values = dict(self.terms)
        for monomial, coefficient in other.terms:
            values[monomial] = values.get(monomial, Fraction()) + coefficient
        return Polynomial(values)

    __radd__ = __add__

    def __neg__(self) -> Polynomial:
        return Polynomial({monomial: -value for monomial, value in self.terms})

    def __sub__(self, other: object) -> Polynomial:
        return self + -Polynomial(other)

    def __rsub__(self, other: object) -> Polynomial:
        return Polynomial(other) - self

    def __mul__(self, other: object) -> Polynomial:
        other = Polynomial(other)
        values: dict[Monomial, Fraction] = {}
        for left, a in self.terms:
            for right, b in other.terms:
                powers = dict(left)
                for name, power in right:
                    powers[name] = powers.get(name, 0) + power
                monomial = tuple(sorted(powers.items()))
                values[monomial] = values.get(monomial, Fraction()) + a * b
        return Polynomial(values)

    __rmul__ = __mul__

    def __pow__(self, power: int) -> Polynomial:
        if isinstance(power, bool) or not isinstance(power, int) or power < 0:
            raise ValueError("polynomial powers must be nonnegative integers")
        result, factor = Polynomial(1), self
        while power:
            if power & 1:
                result = result * factor
            factor = factor * factor
            power //= 2
        return result


@dataclass(frozen=True, slots=True)
class SymbolicCoefficient:
    """An exact rational function over named commuting symbols.

    Equality uses exact polynomial cross multiplication.  A constant hash is
    intentional: equal rational functions may have differently factored
    numerator/denominator representations without an expensive polynomial GCD.
    """

    numerator: Polynomial = Polynomial()
    denominator: Polynomial = Polynomial(1)

    def __init__(self, numerator: object = 0, denominator: object = 1) -> None:
        top, bottom = Polynomial(numerator), Polynomial(denominator)
        if not bottom:
            raise ZeroDivisionError("a symbolic denominator cannot be zero")
        if not top:
            bottom = Polynomial(1)
        top_denominator = _coefficient_denominator(top)
        bottom_denominator = _coefficient_denominator(bottom)
        top = top * (top_denominator * bottom_denominator)
        bottom = bottom * (bottom_denominator * top_denominator)
        common_content = gcd(_coefficient_content(top), _coefficient_content(bottom))
        if common_content > 1:
            top = top * Fraction(1, common_content)
            bottom = bottom * Fraction(1, common_content)
        common_monomial = _common_monomial(top, bottom)
        if common_monomial:
            top = _divide_monomial(top, common_monomial)
            bottom = _divide_monomial(bottom, common_monomial)
        if bottom.terms[-1][1] < 0:
            top, bottom = top * -1, bottom * -1
        ratio = _proportional_ratio(top, bottom)
        if ratio is not None:
            top, bottom = Polynomial(ratio), Polynomial(1)
        top_constant = _constant_polynomial(top)
        bottom_constant = _constant_polynomial(bottom)
        if top_constant is not None and bottom_constant is not None:
            top, bottom = Polynomial(top_constant / bottom_constant), Polynomial(1)
        elif top == bottom:
            top, bottom = Polynomial(1), Polynomial(1)
        object.__setattr__(self, "numerator", top)
        object.__setattr__(self, "denominator", bottom)

    @classmethod
    def symbol(cls, name: str) -> SymbolicCoefficient:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
            raise ValueError(f"invalid symbolic coefficient name {name!r}")
        return cls(Polynomial(name))

    def __bool__(self) -> bool:
        return bool(self.numerator)

    def __add__(self, other: object) -> SymbolicCoefficient:
        other = as_symbolic(other)
        return SymbolicCoefficient(
            self.numerator * other.denominator + other.numerator * self.denominator,
            self.denominator * other.denominator,
        )

    __radd__ = __add__

    def __neg__(self) -> SymbolicCoefficient:
        return SymbolicCoefficient(-self.numerator, self.denominator)

    def __sub__(self, other: object) -> SymbolicCoefficient:
        return self + -as_symbolic(other)

    def __rsub__(self, other: object) -> SymbolicCoefficient:
        return as_symbolic(other) - self

    def __mul__(self, other: object) -> SymbolicCoefficient:
        other = as_symbolic(other)
        return SymbolicCoefficient(
            self.numerator * other.numerator,
            self.denominator * other.denominator,
        )

    __rmul__ = __mul__

    def __truediv__(self, other: object) -> SymbolicCoefficient:
        other = as_symbolic(other)
        if not other:
            raise ZeroDivisionError("division by zero")
        return SymbolicCoefficient(
            self.numerator * other.denominator,
            self.denominator * other.numerator,
        )

    def __rtruediv__(self, other: object) -> SymbolicCoefficient:
        return as_symbolic(other) / self

    def __pow__(self, power: int) -> SymbolicCoefficient:
        if isinstance(power, bool) or not isinstance(power, int):
            raise TypeError("symbolic powers must be integers")
        if power < 0:
            return SymbolicCoefficient(self.denominator ** -power, self.numerator ** -power)
        return SymbolicCoefficient(self.numerator ** power, self.denominator ** power)

    def __eq__(self, other: object) -> bool:
        try:
            other = as_symbolic(other)
        except TypeError:
            return False
        return self.numerator * other.denominator == other.numerator * self.denominator

    def __hash__(self) -> int:
        constant = self.as_fraction()
        return hash(constant) if constant is not None else 0

    def __str__(self) -> str:
        top = _polynomial_source(self.numerator)
        return top if self.denominator == Polynomial(1) else f"({top})/({_polynomial_source(self.denominator)})"

    def latex(self) -> str:
        top = _polynomial_source(self.numerator, latex=True)
        if self.denominator == Polynomial(1):
            return top
        return rf"\frac{{{top}}}{{{_polynomial_source(self.denominator, latex=True)}}}"

    def latex_factor(self) -> str:
        """Render as one multiplicative factor without redundant brackets."""
        rendered = self.latex()
        if self.denominator != Polynomial(1) or len(self.numerator.terms) <= 1:
            return rendered
        return rf"\left({rendered}\right)"

    def as_fraction(self) -> Fraction | None:
        """Return the rational value when this expression contains no symbols."""
        top = dict(self.numerator.terms)
        bottom = dict(self.denominator.terms)
        if set(top) <= {()} and set(bottom) == {()}:
            return top.get((), Fraction()) / bottom[()]
        return None


def as_symbolic(value: object) -> SymbolicCoefficient:
    if isinstance(value, SymbolicCoefficient):
        return value
    if isinstance(value, (int, Fraction)) and not isinstance(value, bool):
        return SymbolicCoefficient(value)
    raise TypeError("expected an integer, fraction, or symbolic coefficient")


class _Parser:
    def __init__(self, source: str, values: dict[str, SymbolicCoefficient]) -> None:
        self.source, self.values, self.index = source, values, 0

    def parse(self) -> SymbolicCoefficient:
        value = self.sum()
        self.spaces()
        if self.index != len(self.source):
            raise ValueError(f"unexpected symbolic expression text at {self.index}")
        return value

    def sum(self) -> SymbolicCoefficient:
        value = self.product()
        while True:
            self.spaces()
            if self.take("+"):
                value += self.product()
            elif self.take("-"):
                value -= self.product()
            else:
                return value

    def product(self) -> SymbolicCoefficient:
        value = self.power()
        while True:
            self.spaces()
            if self.take(r"\times") or self.take("*"):
                value *= self.power()
            elif self.take("/"):
                value /= self.power()
            else:
                return value

    def power(self) -> SymbolicCoefficient:
        value = self.factor()
        self.spaces()
        if self.take("^"):
            self.spaces()
            braced = self.take("{")
            match = re.match(r"-?\d+", self.source[self.index:])
            if match is None:
                raise ValueError("a symbolic power must be an integer")
            self.index += match.end()
            if braced and not self.take("}"):
                raise ValueError("missing closing power brace")
            value **= int(match.group())
        return value

    def factor(self) -> SymbolicCoefficient:
        self.spaces()
        if self.take("+"):
            return self.factor()
        if self.take("-"):
            return -self.factor()
        if self.take(r"\frac"):
            return self.braced() / self.braced()
        if self.take("("):
            value = self.sum()
            self.spaces()
            if not self.take(")"):
                raise ValueError("missing closing parenthesis")
            return value
        number = re.match(r"(?:\d+(?:\.\d*)?|\.\d+)", self.source[self.index:])
        if number:
            self.index += number.end()
            return SymbolicCoefficient(Fraction(number.group()))
        name = re.match(r"[A-Za-z][A-Za-z0-9_]*", self.source[self.index:])
        if name:
            self.index += name.end()
            return self.values.get(name.group(), SymbolicCoefficient.symbol(name.group()))
        raise ValueError(f"expected a symbolic coefficient at {self.index}")

    def braced(self) -> SymbolicCoefficient:
        self.spaces()
        if not self.take("{"):
            raise ValueError(r"\frac arguments must be braced")
        value = self.sum()
        self.spaces()
        if not self.take("}"):
            raise ValueError("missing closing brace")
        return value

    def take(self, text: str) -> bool:
        if self.source.startswith(text, self.index):
            self.index += len(text)
            return True
        return False

    def spaces(self) -> None:
        while self.index < len(self.source) and self.source[self.index].isspace():
            self.index += 1


def parse_symbolic(
    source: str,
    values: dict[str, SymbolicCoefficient] | None = None,
) -> SymbolicCoefficient:
    """Parse the deliberately small exact coefficient grammar."""
    return _Parser(source, values or {}).parse()


def _polynomial_source(polynomial: Polynomial, *, latex: bool = False) -> str:
    if not polynomial:
        return "0"
    denominator = 1
    for _monomial, coefficient in polynomial.terms:
        denominator = lcm(denominator, coefficient.denominator)
    if denominator != 1:
        integral = Polynomial({
            monomial: coefficient * denominator
            for monomial, coefficient in polynomial.terms
        })
        body = _polynomial_source(integral, latex=latex)
        return (rf"\frac{{{body}}}{{{denominator}}}"
                if latex else f"({body})/{denominator}")
    parts: list[str] = []
    for monomial, coefficient in reversed(polynomial.terms):
        negative = coefficient < 0
        magnitude = abs(coefficient)
        if parts:
            parts.append(" - " if negative else " + ")
        elif negative:
            parts.append("-")
        variable_factors = [
            name if power == 1 else (rf"{name}^{{{power}}}" if latex else f"{name}^{power}")
            for name, power in monomial
        ]
        variables = (r" \times " if latex else " * ").join(variable_factors)
        if magnitude != 1 or not variables:
            if magnitude.denominator == 1:
                parts.append(str(magnitude.numerator))
            elif latex:
                parts.append(rf"\frac{{{magnitude.numerator}}}{{{magnitude.denominator}}}")
            else:
                parts.append(f"{magnitude.numerator}/{magnitude.denominator}")
            if variables:
                parts.append(r" \times " if latex else " * ")
        parts.append(variables)
    return "".join(parts)


def _constant_polynomial(polynomial: Polynomial) -> Fraction | None:
    terms = dict(polynomial.terms)
    if set(terms) <= {()}:
        return terms.get((), Fraction())
    return None


def _coefficient_denominator(polynomial: Polynomial) -> int:
    result = 1
    for _monomial, coefficient in polynomial.terms:
        result = lcm(result, coefficient.denominator)
    return result


def _coefficient_content(polynomial: Polynomial) -> int:
    result = 0
    for _monomial, coefficient in polynomial.terms:
        if coefficient.denominator != 1:
            return 1
        result = gcd(result, abs(coefficient.numerator))
    return result


def _common_monomial(left: Polynomial, right: Polynomial) -> Monomial:
    monomials = [monomial for monomial, _coefficient in (*left.terms, *right.terms)]
    if not monomials:
        return ()
    common = dict(monomials[0])
    for monomial in monomials[1:]:
        powers = dict(monomial)
        for name in tuple(common):
            common[name] = min(common[name], powers.get(name, 0))
            if not common[name]:
                del common[name]
    return tuple(sorted(common.items()))


def _divide_monomial(polynomial: Polynomial, divisor: Monomial) -> Polynomial:
    removed = dict(divisor)
    return Polynomial({
        tuple((name, power - removed.get(name, 0)) for name, power in monomial
              if power - removed.get(name, 0)): coefficient
        for monomial, coefficient in polynomial.terms
    })


def _proportional_ratio(left: Polynomial, right: Polynomial) -> Fraction | None:
    left_terms, right_terms = dict(left.terms), dict(right.terms)
    if left_terms.keys() != right_terms.keys() or not left_terms:
        return None
    first = next(iter(left_terms))
    ratio = left_terms[first] / right_terms[first]
    return ratio if all(
        left_terms[monomial] == ratio * right_terms[monomial]
        for monomial in left_terms
    ) else None


__all__ = ["Polynomial", "SymbolicCoefficient", "as_symbolic", "parse_symbolic"]
