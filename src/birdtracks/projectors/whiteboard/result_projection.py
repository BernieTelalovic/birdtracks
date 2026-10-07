"""Pure projection of accepted algebraic occurrences to whiteboard result text."""

from collections.abc import Iterable, Mapping, Sequence
import re
from fractions import Fraction

from ..layout import rendering_projector
from ..projector import Projector
from ..projector_sum import ProjectorSum
from .calculation import SymbolicProjectorSum
from .projector_codec import projector_codec
from ...symbolic import SymbolicCoefficient


def inline_sign_owned(source: str, start: int) -> bool:
    """Whether inline source, rather than the canvas, draws the prefactor."""
    return bool(re.search(r"(?:[+-]|\d|\\frac\s*\{\s*\d+\s*\}\s*\{\s*\d+\s*\})\s*$", source[:start]))


def flip_inline_sign(source: str, start: int) -> str:
    """Project a relative minus into source text, without algebra or parsing."""
    prefix = source[:start]
    number = re.search(r"(?:\\frac\s*\{\s*\d+\s*\}\s*\{\s*\d+\s*\}|\d+(?:[.,_]\d+)?(?:\s*/\s*\d+)?)\s*$", prefix)
    magnitude_start = number.start() if number else start
    before = source[:magnitude_start].rstrip()
    if before.endswith(("+", "-")):
        index = len(before) - 1
        unary = not before[:index].strip() or bool(re.search(r"(?:[=({\[]|\\def|:=)\s*$", before[:index]))
        replacement = "" if before[index] == "-" and unary else "+" if before[index] == "-" else "-"
        return source[:index] + replacement + source[index + 1:]
    return source[:magnitude_start] + "-" + source[magnitude_start:]


def project_inline_occurrence(
    source: str, start: int, accepted: Projector, previous_coefficient: Fraction, source_value: Projector,
) -> tuple[str, Projector]:
    """Project a committed redraw into source and its matching occurrence.

    The shared command has already compensated the exact value. Where source
    owns the visible scalar, transfer only its relative minus to the source and
    retain the occurrence's scalar convention, so parsing cannot count it twice.
    """
    if not accepted.coefficient:
        return source, accepted
    if not inline_sign_owned(source, start):
        unary_atom = not source[:start].strip() or bool(re.search(r"(?:=|\\def|:=)\s*$", source[:start]))
        if abs(accepted.coefficient) != 1 or not unary_atom:
            return source, accepted
    if previous_coefficient and accepted.coefficient / previous_coefficient == -1:
        source = flip_inline_sign(source, start)
    elif previous_coefficient and abs(accepted.coefficient / previous_coefficient) != 1:
        # Structural identities can introduce a rational scalar, not just a
        # parity minus. Transfer it to the source-owned prefactor exactly once.
        ratio = accepted.coefficient / previous_coefficient
        number = re.search(r"(?:\\frac\s*\{\s*\d+\s*\}\s*\{\s*\d+\s*\}|\d+(?:[.,_]\d+)?(?:\s*/\s*\d+)?)\s*$", source[:start])
        magnitude = Fraction(1)
        if number:
            raw = number.group().strip()
            fraction = re.fullmatch(r"\\frac\s*\{\s*(\d+)\s*\}\s*\{\s*(\d+)\s*\}",raw)
            magnitude = Fraction(int(fraction[1]),int(fraction[2])) if fraction else Fraction(raw.replace('_','').replace(',','.').replace(' ',''))
        value = magnitude * abs(ratio)
        literal = str(value.numerator) if value.denominator == 1 else rf"\frac{{{value.numerator}}}{{{value.denominator}}}"
        index = number.start() if number else start
        source = source[:index] + literal + source[start:]
        if ratio < 0:
            source = flip_inline_sign(source, index + len(literal))
    body = accepted * (source_value.coefficient / accepted.coefficient)
    return source, body


def projector_terms_source(projectors: Iterable[Projector]) -> tuple[str, list[dict[str, object]]]:
    """Format ordered occurrences without collecting, expanding, or collapsing."""
    source = "= "
    terms = []
    for index, projector in enumerate(projectors):
        term = rendering_projector(projector)
        number = term.coefficient
        source += "- " if number < 0 else "+ " if index else ""
        magnitude = abs(number)
        if magnitude != 1 or not term.nodes:
            source += (str(magnitude.numerator) if magnitude.denominator == 1
                       else rf"\frac{{{magnitude.numerator}}}{{{magnitude.denominator}}}")
        if term.nodes:
            start = len(source)
            source += "R"
            terms.append({"start": start, "end": len(source), "value": projector_codec.encode(term)})
        source += " "
    return source.rstrip() if source != "= " else "= 0", terms


def inline_rewrite_factor(source: str, start: int, body: Projector, accepted: Projector) -> Fraction:
    """Translate an atomic authored occurrence's source scalar to descendants.

    Composite expressions expand on their evaluated result line, where the
    full term graph and its provenance are available. Do not parse/solve a
    containing product or trace from an interactive occurrence command.
    """
    if source[start:].strip() != r"\birdtracks":
        raise ValueError("expand composite expressions on their evaluated result line")
    prefix = re.sub(r"^\s*\S+?\s*(?:\\def\b|:=)\s*", "", source[:start]).strip()
    prefix = prefix.removeprefix("=").strip()
    literal = re.fullmatch(r"(?P<sign>[+-]?)\s*(?:(?P<frac>\\frac\s*\{\s*\d+\s*\}\s*\{\s*\d+\s*\})|(?P<number>\d+(?:[.,_]\d+)?(?:\s*/\s*\d+)?))?", prefix)
    if literal is None:
        raise ValueError("expand composite expressions on their evaluated result line")
    if literal.group("frac"):
        numerator, denominator = re.findall(r"\d+", literal.group("frac"))
        factor = Fraction(int(numerator),int(denominator))
    else:
        factor = Fraction((literal.group("number") or "1").replace(" ","").replace("_","").replace(",","."))
    if literal.group("sign") == "-":
        factor = -factor
    return factor * body.coefficient / accepted.coefficient if accepted.coefficient else factor


def result_source(value: ProjectorSum | SymbolicProjectorSum) -> tuple[str, list[dict[str, object]]]:
    """Use the shared exact port projection for both scalar text and diagrams."""
    if isinstance(value, ProjectorSum):
        return projector_terms_source(projector * coefficient for projector, coefficient in value.items())
    return symbolic_projector_terms_source(value.terms)


def symbolic_projector_terms_source(occurrences: Iterable[tuple[Projector, SymbolicCoefficient]]) -> tuple[str, list[dict[str, object]]]:
    """Project ordered symbolic occurrences without collecting their values."""
    source = "= "
    terms = []
    scalars = []
    has_occurrences = False
    for index, (projector, coefficient) in enumerate(occurrences):
        has_occurrences = True
        rendered = rendering_projector(projector)
        displayed = coefficient * rendered.coefficient
        if index:
            source += " + "
        source += displayed.latex_factor()
        if rendered.nodes:
            start = len(source)
            source += "R"
            terms.append({"start": start, "end": len(source), "value": projector_codec.encode(rendered),
                          "outer_factor": projector_codec.encode(coefficient), "occurrence_index": index,
                          "factor_preview": {"even": displayed.latex_factor(), "odd": (-displayed).latex_factor()}})
        else:
            scalars.append({"occurrence_index": index, "value": projector_codec.encode(rendered),
                            "outer_factor": projector_codec.encode(coefficient)})
    if terms and scalars:
        terms[0]["scalar_terms"] = scalars
    return source if has_occurrences else "= 0", terms


def project_symbolic_occurrences(projectors: Iterable[Projector], terms: Sequence[Mapping[str, object]]) -> tuple[str, list[dict[str, object]]]:
    """Retain symbolic factors, scalar-only terms, and occurrence order."""
    ordered = [(int(item.get("occurrence_index", index)), p, projector_codec.decode(item["outer_factor"]))
               for index, (p, item) in enumerate(zip(projectors, terms, strict=True))]
    for scalar in terms[0].get("scalar_terms", []) if terms else []:
        ordered.append((int(scalar["occurrence_index"]), projector_codec.decode(scalar["value"]),
                        projector_codec.decode(scalar["outer_factor"])))
    return symbolic_projector_terms_source((p, factor) for _index, p, factor in sorted(ordered, key=lambda item: item[0]))
