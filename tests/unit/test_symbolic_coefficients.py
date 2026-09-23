from fractions import Fraction

from birdtracks import Projector, Symmetriser, parse_symbolic
from birdtracks.projectors.whiteboard.calculation import (
    SymbolicProjectorSum,
    calculate_projector_blocks,
    evaluate_projector_expression,
    simplify_projector_value,
)
from birdtracks.projectors.whiteboard.widget import _result_source
from birdtracks.projectors.whiteboard.pair_calculation import pair_expression_from_blocks
from birdtracks.projectors.whiteboard.projector_codec import projector_codec
from birdtracks.young_diagrams import PairExpression, PairTerm


def test_exact_symbolic_rational_function_arithmetic() -> None:
    x = parse_symbolic("x")
    value = parse_symbolic(r"\frac{x+1}{2}")

    assert value * 2 == x + 1
    assert parse_symbolic("(x+1)/(x+1)") == 1
    assert parse_symbolic("x^2-x^2") == 0
    assert projector_codec.decode(projector_codec.encode(value)) == value


def test_constant_hash_matches_equal_builtin_number() -> None:
    one = parse_symbolic("1")

    assert one == 1
    assert hash(one) == hash(1)
    assert {(one,)} == {(1,)}


def test_numeric_fraction_operations_canonicalize_to_one_fraction() -> None:
    assert parse_symbolic(r"\frac{4}{3}\times\frac{4}{3}").latex() == r"\frac{16}{9}"
    assert parse_symbolic(r"\frac{4}{3}+\frac{4}{3}").latex() == r"\frac{8}{3}"
    assert parse_symbolic(r"\frac{4}{3}-\frac{1}{3}").latex() == "1"
    assert parse_symbolic(r"\frac{4}{3}/\frac{2}{3}").latex() == "2"
    assert parse_symbolic(r"(x+1)/(x+1)").latex() == "1"


def test_raw_constant_arithmetic_uses_the_expression_model() -> None:
    environment, _ = calculate_projector_blocks(
        [{"id": "a", "source": r"A\def \frac{4}{3}"}], {}
    )
    cases = {
        "A+A": Fraction(8, 3),
        "A-A": Fraction(0),
        r"A\times A": Fraction(16, 9),
        "A*A": Fraction(16, 9),
        "A A": Fraction(16, 9),
        "A/A": Fraction(1),
        "A^2": Fraction(16, 9),
    }
    for source, expected in cases.items():
        result = evaluate_projector_expression([{"source": source}], {}, environment)
        assert result == expected
        assert isinstance(result, type(parse_symbolic("1")))

    literal_cases = {
        r"\frac{1}{2}+\frac{1}{3}": Fraction(5, 6),
        r"\frac{1}{2}-\frac{1}{3}": Fraction(1, 6),
        r"\frac{1}{2}\times\frac{2}{3}": Fraction(1, 3),
        r"\frac{1}{2}*\frac{2}{3}": Fraction(1, 3),
        r"\frac{1}{2}/\frac{2}{3}": Fraction(3, 4),
    }
    for source, expected in literal_cases.items():
        assert evaluate_projector_expression(
            [{"source": source}], {}, environment
        ) == expected


def test_named_scalar_scales_birdtracks_on_either_side_with_times() -> None:
    projector = Projector([Symmetriser((1, 2))], coefficient=Fraction(2, 3))

    class Editor:
        _configured_projector = projector
        saved_revision = 1

    environment, _ = calculate_projector_blocks(
        [
            {"id": "a", "source": r"A\def \frac{x+1}{2}"},
            {"id": "b", "source": r"B\def \birdtracks"},
        ],
        {"b:projector:0": Editor()},
    )
    expected = parse_symbolic(r"\frac{x+1}{2}")
    for source in (r"A B", r"A \times B", r"B \times A"):
        result = evaluate_projector_expression([{"source": source}], {}, environment)
        assert isinstance(result, SymbolicProjectorSum)
        assert result.terms == ((projector, expected),)
        rendered, _terms = _result_source(result)
        assert rendered == r"= \frac{x + 1}{3}R"


def test_fraction_times_fractional_birdtrack_renders_as_one_fraction() -> None:
    projector = Projector([Symmetriser((1, 2))], coefficient=Fraction(4, 3))

    class Editor:
        _configured_projector = projector
        saved_revision = 1

    environment, _ = calculate_projector_blocks(
        [
            {"id": "a", "source": r"A\def \frac{4}{3}"},
            {"id": "b", "source": r"B\def \birdtracks"},
        ],
        {"b:projector:0": Editor()},
    )
    for source in (r"A\times B", r"B\times A", "A B"):
        result = evaluate_projector_expression([{"source": source}], {}, environment)
        assert isinstance(result, SymbolicProjectorSum)
        rendered, _terms = _result_source(simplify_projector_value(result))
        assert rendered == r"= \frac{16}{9}R"


def test_trace_distributes_a_symbolic_scalar_over_the_projector_trace() -> None:
    projector = Projector([Symmetriser((1, 2))])

    class Editor:
        _configured_projector = projector
        saved_revision = 1

    environment, _ = calculate_projector_blocks(
        [
            {"id": "a", "source": r"A\def \frac{4}{3}"},
            {"id": "b", "source": r"B\def \birdtracks"},
        ],
        {"b:projector:0": Editor()},
    )
    expected = parse_symbolic(r"\frac{2*N^2+2*N}{3}")
    for source in (
        r"\tr(A B)",
        r"\tr(A\times B)",
        r"\tr(B\times A)",
        r"\tr\left(A B\right)",
    ):
        assert evaluate_projector_expression(
            [{"source": source}], {}, environment
        ) == expected


def test_trace_is_the_identity_on_scalars() -> None:
    environment, _ = calculate_projector_blocks(
        [{"id": "a", "source": r"A\def \frac{x+1}{3}"}], {}
    )
    expected = parse_symbolic(r"\frac{x+1}{3}")

    for source in (
        r"\tr A",
        r"\tr(A)",
        r"\tr\left(A\right)",
        r"\tr\tr A",
        r"\tr\frac{x+1}{3}",
    ):
        assert evaluate_projector_expression(
            [{"source": source}], {}, environment
        ) == expected


def test_named_symbolic_scalar_scales_every_pair_prefactor() -> None:
    scalar = parse_symbolic(r"\frac{x+1}{2}")
    pair = PairExpression((PairTerm(coefficient=2), PairTerm(coefficient=3)))

    expression = pair_expression_from_blocks(
        [{"source": r"A \times B"}],
        {},
        {"A": scalar, "B": pair},  # type: ignore[arg-type]
    )

    assert [term.coefficient for term in expression.terms] == [scalar * 2, scalar * 3]


def test_whiteboard_generates_a_canonical_result_for_constant_only_arithmetic() -> None:
    pytest = __import__("pytest")
    pytest.importorskip("anywidget")
    from birdtracks import whiteboard

    document = whiteboard(debug=True)
    document.blocks = [
        {"id": "definition", "line_id": "definition", "source": r"A\def \frac{4}{3}"},
        {"id": "result", "line_id": "result", "source": r"A\times A"},
    ]
    document.simplify_request = {
        "line_id": "result", "action": "evaluate", "revision": 8675309,
    }

    assert document.blocks[-1]["source"] == r"= \frac{16}{9}"
    assert document.blocks[-1]["calculation_scalar"] is True
