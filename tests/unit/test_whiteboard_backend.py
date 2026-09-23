"""Tests for the renderer-independent whiteboard backend seam."""

from dataclasses import dataclass

import pytest
from fractions import Fraction

from birdtracks import Antisymmetriser, Projector, ProjectorSum, Symmetriser
from birdtracks.linear_combinations import DimensionPolynomial
from birdtracks.young_diagrams import PairExpression
from birdtracks.projectors.whiteboard import (
    DiagramAlgebraBackend,
    DiagramValueCodec,
    DefinitionLine,
    EvaluationEnvironment,
    ProjectorAlgebraBackend,
    diagram_backend,
    diagram_codec,
    product,
    reference,
)
from birdtracks.projectors.whiteboard.calculation import (
    calculate_projector_blocks,
    evaluate_projector_expression,
)
from birdtracks.projectors.whiteboard.projector_codec import projector_codec


def test_projector_environment_keeps_named_values_outside_canvas_state() -> None:
    projector = Projector([Symmetriser({1, 2})])
    environment = EvaluationEnvironment(ProjectorAlgebraBackend())

    definition = environment.define("P1", projector)

    assert definition.name == "P1"
    assert environment.resolve(reference("P1")) is projector
    assert environment.definitions == (definition,)


def test_projector_backend_evaluates_ordered_products_exactly() -> None:
    left = Projector([Symmetriser({1, 2})])
    right = Projector([Symmetriser({2, 3})])
    environment = EvaluationEnvironment(ProjectorAlgebraBackend())
    environment.define("P1", left)
    environment.define("P2", right)

    assert environment.evaluate(product(reference("P1"), reference("P2"))) == left * right


def test_whiteboard_calculation_defines_joined_expression_and_expands_reference() -> None:
    first = Projector([Symmetriser({1, 2})])
    second = Projector([Symmetriser({2, 3})])

    class Editor:
        _configured_projector = first

    class SecondEditor:
        _configured_projector = second

    blocks = [
        {"id": "line-1", "source": r"A := \birdtracks", "line_id": "line-1"},
        {"id": "line-2", "source": r"&+\birdtracks", "line_id": "line-1"},
        {"id": "line-3", "source": "-A", "line_id": "line-3"},
    ]
    environment, terms = calculate_projector_blocks(
        blocks,
        {
            "line-1:projector:0": Editor(),
            "line-2:projector:0": SecondEditor(),
        },
    )

    assigned = environment.resolve("A")
    assert len(assigned) == 2  # type: ignore[arg-type]
    assert len(terms) == 2
    assert {term.block_id for term in terms} == {"line-3"}
    assert all(term.start == 1 and term.end == 2 for term in terms)
    assert all(term.value.coefficient > 0 for term in terms)


def test_whiteboard_calculation_accepts_def_command() -> None:
    projector = Projector([])

    class Editor:
        _configured_projector = projector

    environment, terms = calculate_projector_blocks(
        [{"id": "line-1", "source": r"A \def \birdtracks"}],
        {"line-1:projector:0": Editor()},
    )

    assert environment.resolve("A") == projector
    assert terms == ()


def test_whiteboard_plain_references_remain_signifiers_until_explicitly_signed() -> None:
    projector = Projector([])

    class Editor:
        _configured_projector = projector

    environment, plain_terms = calculate_projector_blocks(
        [
            {"id": "line-1", "source": r"A \def \birdtracks"},
            {"id": "line-2", "source": "A"},
        ],
        {"line-1:projector:0": Editor()},
    )
    _environment, signed_terms = calculate_projector_blocks(
        [{"id": "line-2", "source": "+A"}],
        {},
        {"A": projector},
    )

    assert environment.resolve("A") == projector
    assert plain_terms == ()
    assert len(signed_terms) == 1
    assert signed_terms[0].start == 1


def test_whiteboard_calculation_accepts_bare_projector_symbol() -> None:
    projector = Projector([])

    class Editor:
        _configured_projector = projector

    environment, terms = calculate_projector_blocks(
        [{"id": "line-1", "source": r"A \def \birdtracks"}],
        {"line-1:projector:0": Editor()},
    )

    assert environment.resolve("A") == projector
    assert terms == ()


def test_negative_bare_projector_has_unit_prefactor() -> None:
    projector = Projector([Symmetriser((1, 2))])

    class Editor:
        _configured_projector = projector

    result = evaluate_projector_expression(
        [{"id": "line-1", "source": r"-\birdtracks"}],
        {"line-1:projector:0": Editor()},
        EvaluationEnvironment(ProjectorAlgebraBackend()),
    )

    assert result == projector * -1


@pytest.mark.parametrize(
    "source",
    [r"2 + \birdtracks", r"\birdtracks + 2",
     r"2 - \birdtracks", r"\birdtracks - 2"],
)
def test_scalar_addition_and_subtraction_with_birdtracks_is_not_implemented(
    source: str,
) -> None:
    projector = Projector([])

    class Editor:
        _configured_projector = projector

    with pytest.raises(NotImplementedError, match="scalars and birdtracks"):
        evaluate_projector_expression(
            [{"id": "line", "source": source}],
            {"line:projector:0": Editor()},
            EvaluationEnvironment(ProjectorAlgebraBackend()),
        )


@pytest.mark.parametrize('text, coefficient', [
    ('2', Fraction(2)), ('-2', Fraction(-2)), ('0.125', Fraction(1, 8)),
    ('2/3', Fraction(2, 3)), (r'\frac{2}{3}', Fraction(2, 3)),
])
def test_evaluate_numeric_prefactors(text, coefficient) -> None:
    projector = Projector([Symmetriser((1, 2))])

    class Editor:
        _configured_projector = projector

    result = evaluate_projector_expression(
        [{'id': 'a', 'source': rf'A\def {text}\birdtracks'}],
        {'a:projector:0': Editor()},
        EvaluationEnvironment(ProjectorAlgebraBackend()),
    )
    assert result == projector * coefficient


def test_whiteboard_calculation_rejects_empty_group_after_birdtracks() -> None:
    projector = Projector([])

    class Editor:
        _configured_projector = projector

    environment = EvaluationEnvironment(ProjectorAlgebraBackend())
    with pytest.raises(ValueError, match="expected an expression"):
        evaluate_projector_expression(
            [{"id": "line-1", "source": r"\birdtracks{}"}],
            {"line-1:projector:0": Editor()},
            environment,
        )


def test_whiteboard_calculation_does_not_accept_legacy_projector_command() -> None:
    environment = EvaluationEnvironment(ProjectorAlgebraBackend())
    legacy_command = "\\" + "projector"

    with pytest.raises(ValueError, match="expected an expression"):
        evaluate_projector_expression(
            [{"id": "line-1", "source": legacy_command}],
            {},
            environment,
        )


def test_whiteboard_calculation_keeps_persisted_definition_until_editor_saves() -> None:
    persisted = Projector([Symmetriser({1, 2})])

    class UnmaterializedEditor:
        _configured_projector = Projector([])
        saved_revision = 0

    environment, terms = calculate_projector_blocks(
        [{"id": "line-1", "source": r"A := \birdtracks"}],
        {"line-1:projector:0": UnmaterializedEditor()},
        {"A": persisted},
    )

    assert environment.resolve("A") == persisted
    assert terms == ()


def test_whiteboard_calculation_uses_latest_simplified_definition_value() -> None:
    original = Projector([Symmetriser({1, 2})])
    simplified = Projector([Antisymmetriser({1, 2})])

    class SavedEditor:
        _configured_projector = original
        saved_revision = 1

    environment, _terms = calculate_projector_blocks(
        [
            {"id": "definition", "source": r"A \def \birdtracks",
             "line_id": "definition", "read_only": True,
             "calculation_group": "definition"},
            {"id": "step", "source": "= simplified", "line_id": "step",
             "read_only": True, "calculation_group": "definition",
             "calculation_step": 1, "calculation_value":
             projector_codec.encode(simplified)},
        ],
        {"definition:projector:0": SavedEditor()},
        {"A": simplified},
    )

    assert environment.resolve("A") == simplified


def test_whiteboard_expression_parser_supports_adjacency_brackets_and_trace() -> None:
    left = Projector([Symmetriser({1, 2})])
    right = Projector([Symmetriser({2, 3})])

    class Editor:
        _configured_projector = left
        saved_revision = 1

    environment = EvaluationEnvironment(ProjectorAlgebraBackend())
    environment.define("A_2", left)
    environment.define("B_1", right)

    adjacent = evaluate_projector_expression(
        [{"source": "A_2 B_1"}], {}, environment
    )
    bracketed = evaluate_projector_expression(
        [{"source": "[A_2 + B_1]"}], {}, environment
    )
    traced_term = evaluate_projector_expression(
        [{"source": r"\tr A_2"}], {}, environment
    )
    traced_sum = evaluate_projector_expression(
        [{"source": r"\tr(A_2 + B_1)"}], {}, environment
    )
    traced_embedded = evaluate_projector_expression(
        [{"id": "embedded", "source": r"\tr\left(\birdtracks\right)"}],
        {"embedded:projector:0": Editor()}, environment,
    )
    definitions, _terms = calculate_projector_blocks(
        [{"id": "definition", "source": r"P \def \birdtracks"}],
        {"definition:projector:0": Editor()},
    )
    traced_definition = evaluate_projector_expression(
        [{"source": r"\tr\left(P\right)"}], {}, definitions
    )

    assert adjacent == left * right
    assert bracketed == left + right
    assert traced_term == DimensionPolynomial({1: Fraction(1, 2), 2: Fraction(1, 2)})
    assert traced_sum == DimensionPolynomial({1: 1, 2: 1})
    assert traced_embedded == traced_term
    assert traced_definition == traced_term


def test_environment_rejects_rebinding_and_unknown_symbols() -> None:
    environment = EvaluationEnvironment(ProjectorAlgebraBackend())
    environment.define("P1", Projector([]))

    with pytest.raises(ValueError, match="already defined"):
        environment.define("P1", Projector([]))
    with pytest.raises(LookupError, match="unknown symbol"):
        environment.resolve("P2")


@dataclass(frozen=True)
class TextValue:
    text: str


class TextBackend:
    """A tiny unrelated backend proving the environment is generic."""

    name = "text"

    def validate(self, value: object) -> TextValue:
        if not isinstance(value, TextValue):
            raise TypeError("expected a TextValue")
        return value

    def multiply(self, left: TextValue, right: TextValue) -> TextValue:
        return TextValue(f"({left.text} {right.text})")


def test_environment_does_not_depend_on_projector_computation() -> None:
    environment = EvaluationEnvironment(TextBackend())
    environment.define("a", TextValue("a"))
    environment.define("b", TextValue("b"))

    assert environment.evaluate(product(reference("a"), reference("b"))) == TextValue(
        "(a b)"
    )


def test_names_preserve_latex_like_source_text() -> None:
    environment = EvaluationEnvironment(ProjectorAlgebraBackend())
    name = r"\mathcal{P}_{1}"

    definition = environment.define(name, Projector([]))

    assert definition.name == name
    assert environment.resolve(name) == Projector([])


def test_definition_lines_keep_typed_source_lines_separate() -> None:
    projector_line = DefinitionLine("line-1", "projector", r"\mathcal{P}_{1} := \birdtracks")
    diagram_line = DefinitionLine("line-2", "diagram", r"D_{1} := \Diagram")

    assert projector_line.kind != diagram_line.kind
    assert projector_line.source != diagram_line.source


@pytest.mark.parametrize("name", ["", "P\n1", "P\x00_1"])
def test_symbol_names_reject_empty_or_multiline_source(name: str) -> None:
    with pytest.raises(ValueError):
        reference(name)


def test_diagram_backend_and_codec_are_separate_from_projectors() -> None:
    value = PairExpression()
    environment = EvaluationEnvironment(diagram_backend)

    environment.define(r"D_{1}", value)

    assert environment.resolve(r"D_{1}") == value
    assert diagram_codec.decode(diagram_codec.encode(value)) == value
    assert isinstance(DiagramAlgebraBackend(), DiagramAlgebraBackend)
    assert DiagramValueCodec().name == "diagram-v1"
