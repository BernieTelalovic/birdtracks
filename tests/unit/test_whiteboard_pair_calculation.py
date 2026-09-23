import json

import pytest

from birdtracks.projectors.whiteboard.pair_calculation import (
    evaluate_pair_blocks,
    pair_definitions,
    pair_definitions_before,
    pair_expression_from_blocks,
    pair_expression_with_prefactor,
    pair_expression_with_updated_prefactor,
)
from birdtracks.pair_evaluation import expand, parse
from birdtracks.symbolic import SymbolicCoefficient
from birdtracks.young_diagrams import PairExpression, PairTerm


class Editor:
    def __init__(self, expression: PairExpression) -> None:
        self.pair_expression = expression.state()


def test_pair_source_uses_commands_scalars_and_prefactor_n0() -> None:
    blocks = [
        {"id": "line", "source": r"2_4\pair \oplus 3\times\pair"},
    ]
    expression = pair_expression_from_blocks(
        blocks,
        {
            "line:pair:0": Editor(PairExpression((PairTerm(n0=2),))),
            "line:pair:1": Editor(PairExpression((PairTerm(n0=7),))),
        },
    )

    assert expression.syntax == ("pair", "sum", "pair")
    assert [(term.coefficient, term.n0) for term in expression.terms] == [
        (2, 4),
        (3, 7),
    ]


def test_bare_pair_uses_implicit_prefactor_n0_one() -> None:
    expression = pair_expression_from_blocks(
        [{"id": "line", "source": r"\pair"}],
        {"line:pair:0": Editor(PairExpression((PairTerm(n0=0),)))},
    )

    assert expression.terms[0].n0 == 1


def test_adjacent_prefactor_seeds_the_embedded_pair_editor() -> None:
    expression = pair_expression_with_prefactor(r"2_3\pair", 3)

    assert expression.terms[0].coefficient == 2
    assert expression.terms[0].n0 == 3


def test_adjacent_prefactor_updates_an_existing_embedded_pair_editor() -> None:
    original = PairExpression((PairTerm(unbarred=(1,), n0=1),))

    expression = pair_expression_with_updated_prefactor(
        original, r"12_4\pair", 4
    )

    assert expression.terms[0].coefficient == 12
    assert expression.terms[0].n0 == 4
    assert expression.terms[0].unbarred == (1,)


def test_whiteboard_applies_a_prefactor_typed_before_an_existing_pair() -> None:
    pytest.importorskip("anywidget")
    from birdtracks import whiteboard

    document = whiteboard(debug=True)
    document.blocks = [{"id": "line", "source": r"\pair"}]
    document.embedded_pairs[0].pair_expression = PairExpression((
        PairTerm(unbarred=(1,), n0=1),
    )).state()

    document.blocks = [{"id": "line", "source": r"7_3\pair"}]

    expression = PairExpression.from_state(
        document.embedded_pairs[0].pair_expression
    )
    assert expression.terms[0].coefficient == 7
    assert expression.terms[0].n0 == 3
    assert expression.terms[0].unbarred == (1,)


def test_adjacent_prefactor_is_not_counted_twice_during_evaluation() -> None:
    expression = pair_expression_from_blocks(
        [{"id": "line", "source": r"2_3\pair"}],
        {"line:pair:0": Editor(pair_expression_with_prefactor(r"2_3\pair", 3))},
    )

    assert expression.terms[0].coefficient == 2
    assert expression.terms[0].n0 == 3


def test_definition_render_keeps_assignment_and_implicit_n0() -> None:
    source = r"A\def 2\pair"
    marker = source.index(r"\pair")
    calculation = evaluate_pair_blocks(
        [{"id": "line", "source": source}],
        {"line:pair:0": Editor(pair_expression_with_prefactor(source, marker))},
    )

    final = calculation["lines"][-1]["svg"]
    assert 'font-size="22">A</text>' in final
    assert '>2<tspan baseline-shift="sub" font-size="12">1</tspan>' in final


def test_pair_source_preserves_inner_sum_when_tensoring() -> None:
    inner = PairExpression(
        (PairTerm(coefficient=2), PairTerm(coefficient=3)),
        ("pair", "sum", "pair"),
    )
    expression = pair_expression_from_blocks(
        [{"id": "line", "source": r"\pair \otimes \pair"}],
        {
            "line:pair:0": Editor(inner),
            "line:pair:1": Editor(PairExpression((PairTerm(),))),
        },
    )

    assert expression.syntax == (
        "(", "pair", "sum", "pair", ")", "tensor", "pair"
    )


@pytest.mark.parametrize(
    ("source", "expected_syntax", "expected_products"),
    [
        (
            r"\pair\oplus\pair\otimes\pair",
            ("pair", "sum", "pair", "tensor", "pair"),
            ((1,), (2, 3)),
        ),
        (
            r"(\pair\oplus\pair)\otimes\pair",
            ("(", "pair", "sum", "pair", ")", "tensor", "pair"),
            ((1, 3), (2, 3)),
        ),
        (
            r"\pair\otimes(\pair\oplus\pair)",
            ("pair", "tensor", "(", "pair", "sum", "pair", ")"),
            ((1, 2), (1, 3)),
        ),
    ],
)
def test_pair_source_sum_tensor_precedence_and_grouping(
    source: str,
    expected_syntax: tuple[str, ...],
    expected_products: tuple[tuple[int, ...], ...],
) -> None:
    expression = pair_expression_from_blocks(
        [{"id": "line", "source": source}],
        {
            f"line:pair:{index}": Editor(PairExpression((
                PairTerm(coefficient=index + 1),
            )))
            for index in range(3)
        },
    )

    assert expression.syntax == expected_syntax
    assert tuple(
        tuple(str(term.coefficient) for term in product)
        for product in expand(parse(expression))
    ) == tuple(tuple(str(value) for value in product) for product in expected_products)


def test_pair_definition_can_be_reused_by_a_later_expression() -> None:
    blocks = [
        {"id": "definition", "line_id": "definition", "source": r"P\def \pair"},
        {"id": "use", "line_id": "use", "source": r"P \otimes P"},
    ]
    explicit = {
        "definition:pair:0": Editor(
            PairExpression((PairTerm(unbarred=(1,), n0=1),))
        ),
    }
    definitions = pair_definitions_before(blocks, explicit, "use")
    expression = pair_expression_from_blocks(
        [blocks[1]], explicit, definitions
    )

    assert set(definitions) == {"P"}
    assert expression.syntax == ("pair", "tensor", "pair")
    assert len(expression.terms) == 2


def test_pair_definition_wins_over_a_stale_scalar_with_the_same_name() -> None:
    pair = PairExpression((
        PairTerm(barred=(1,), unbarred=(1,), coefficient=2, n0=2),
        PairTerm(barred=(1,), unbarred=(1, 1), coefficient=3, n0=3),
    ), ("pair", "sum", "pair"))
    definitions = {"A": SymbolicCoefficient(2)}
    definitions.update({"A": pair})

    expression = pair_expression_from_blocks(
        [{"id": "use", "source": r"A\otimes A"}], {}, definitions
    )

    assert expression.syntax == (
        "(", "pair", "sum", "pair", ")", "tensor",
        "(", "pair", "sum", "pair", ")",
    )
    assert len(expression.terms) == 4


def test_loaded_pair_definition_wins_over_stale_projector_scalar(tmp_path) -> None:
    pytest.importorskip("anywidget")
    from birdtracks import whiteboard

    pair = PairExpression((
        PairTerm(barred=(1,), unbarred=(1,), coefficient=2, n0=2),
        PairTerm(barred=(1,), unbarred=(1, 1), coefficient=3, n0=3),
    ), ("pair", "sum", "pair"))
    path = tmp_path / "definition-collision.whiteboard"
    path.write_text(json.dumps({
        "format": "birdtracks-whiteboard",
        "version": 2,
        "document": {
            "title": "definition collision",
            "blocks": [
                {
                    "id": "definition", "line_id": "definition",
                    "source": r"A\def 2\pair\oplus 3\pair",
                    "pair_snapshots": {
                        "0": PairExpression((pair.terms[0],)).state(),
                        "1": PairExpression((pair.terms[1],)).state(),
                    },
                },
                {"id": "use", "line_id": "use", "source": r"A\otimes A"},
            ],
        },
        "stores": {
            "diagrams": {
                "backend": "diagram", "codec": "diagram-v1",
                "definitions": [{"name": "A", "value": pair.state()}],
            },
            "projectors": {
                "backend": "projector", "codec": "projector-v1",
                "definitions": [{
                    "name": "A",
                    "value": {"source": "2", "type": "symbolic_scalar"},
                }],
            },
        },
    }), encoding="utf-8")
    document = whiteboard(path, debug=True)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["stores"]["projectors"]["definitions"] == []
    assert [
        definition["name"]
        for definition in saved["stores"]["diagrams"]["definitions"]
    ] == ["A"]

    document.simplify_request = {
        "line_id": "use", "action": "evaluate", "revision": 1,
        "snapshots": {},
    }

    assert document.calculation_feedback["action"] == "completed"
    result = PairExpression.from_state(
        document.blocks[-1]["pair_calculation"]["result"]
    )
    assert len(result.terms) == 27

    document.blocks = [
        {"id": "plain", "line_id": "plain", "source": "plain text"},
    ]
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["stores"]["projectors"]["definitions"] == []
    assert saved["stores"]["diagrams"]["definitions"] == []


def test_pair_definition_with_prefactor_can_be_reused() -> None:
    blocks = [
        {"id": "definition", "line_id": "definition", "source": r"P\def 2_3\pair"},
        {"id": "use", "line_id": "use", "source": "P"},
    ]
    explicit = {
        "definition:pair:0": Editor(
            pair_expression_with_prefactor(r"2_3\pair", 3)
        ),
    }
    definitions = pair_definitions_before(blocks, explicit, "use")
    expression = pair_expression_from_blocks(
        [blocks[1]], explicit, definitions
    )

    assert expression.terms[0].coefficient == 2
    assert expression.terms[0].n0 == 3


def test_pair_sum_can_be_scaled_by_a_scalar_definition() -> None:
    pair = PairExpression(
        (PairTerm(coefficient=2), PairTerm(coefficient=5)),
        ("pair", "sum", "pair"),
    )

    expression = pair_expression_from_blocks(
        [{"id": "use", "source": r"B\times C"}],
        {},
        {"B": pair, "C": SymbolicCoefficient(3)},
    )

    assert expression.syntax == ("pair", "sum", "pair")
    assert [term.coefficient for term in expression.terms] == [6, 15]


def test_pair_definitions_are_kept_separate_from_unknown_pair_references() -> None:
    blocks = [{"id": "definition", "source": r"P\def \pair"}]
    explicit = {"definition:pair:0": Editor(PairExpression())}

    assert set(pair_definitions(blocks, explicit)) == {"P"}
    with pytest.raises(ValueError, match="unknown pair symbol"):
        pair_expression_from_blocks(
            [{"id": "use", "source": "Q"}], {},
            pair_definitions(blocks, explicit),
        )


def test_incomplete_non_pair_definition_ignores_ordinary_addition() -> None:
    assert pair_definitions(
        [{"id": "line", "source": r"A\def x +"}],
        {},
    ) == {}


def test_whiteboard_evaluates_a_later_line_using_a_pair_definition() -> None:
    pytest.importorskip("anywidget")
    pytest.importorskip("pair_multiplication")
    from birdtracks import whiteboard

    document = whiteboard(debug=True)
    document.blocks = [
        {"id": "definition", "source": r"P\def \pair", "line_id": "definition"},
    ]
    document.embedded_pairs[0].pair_expression = PairExpression((
        PairTerm(unbarred=(1,), n0=1),
    )).state()
    document.blocks = [
        *document.blocks,
        {"id": "use", "source": r"P\otimes P", "line_id": "use"},
    ]

    document.simplify_request = {
        "line_id": "use",
        "action": "evaluate",
        "revision": 1,
        "snapshots": {},
    }

    assert document.blocks[-1]["calculation_step"] == 1
    assert document.blocks[-1]["pair_calculation"]["result"]


def test_whiteboard_squares_an_assigned_two_term_pair_sum() -> None:
    pytest.importorskip("anywidget")
    pytest.importorskip("pair_multiplication")
    from birdtracks import whiteboard

    document = whiteboard(debug=True)
    document.blocks = [
        {"id": "definition", "source": r"A\def \pair\oplus\pair",
         "line_id": "definition"},
    ]
    pair = PairExpression((PairTerm(unbarred=(1,), n0=1),)).state()
    for editor in document.embedded_pairs:
        editor.pair_expression = pair
    document.blocks = [
        *document.blocks,
        {"id": "use", "source": r"A\otimes A", "line_id": "use"},
    ]

    document.simplify_request = {
        "line_id": "use", "action": "evaluate", "revision": 1,
        "snapshots": {},
    }

    result = PairExpression.from_state(
        document.blocks[-1]["pair_calculation"]["result"]
    )
    assert {
        (term.unbarred, str(term.coefficient), term.n0)
        for term in result.terms
    } == {((2,), "4", 1), ((1, 1), "4", 2)}


def test_finished_pair_calculation_clears_pending_feedback() -> None:
    pytest.importorskip("anywidget")
    pytest.importorskip("pair_multiplication")
    from birdtracks import whiteboard

    document = whiteboard(debug=True)
    document.blocks = [
        {"id": "b", "source": r"B\def \pair\oplus\pair", "line_id": "b"},
        {"id": "c", "source": r"C\def 3", "line_id": "c"},
    ]
    document.simplify_request = {
        "line_id": "c",
        "action": "evaluate",
        "revision": 1,
        "snapshots": {},
    }
    document.blocks = [
        *document.blocks,
        {"id": "use", "source": r"B\times C", "line_id": "use"},
    ]
    document.simplify_request = {
        "line_id": "use",
        "action": "evaluate",
        "revision": 2,
        "snapshots": {},
    }
    assert document.calculation_feedback["action"] == "completed"
    result_id = document.blocks[-1]["id"]

    document.simplify_request = {
        "line_id": result_id,
        "action": "evaluate",
        "revision": 3,
        "snapshots": {},
    }

    assert document.calculation_feedback["line_id"] == result_id
    assert document.calculation_feedback["action"] == "completed"


def test_failed_pair_calculation_reports_its_traceback_and_stops(
    monkeypatch,
) -> None:
    pytest.importorskip("anywidget")
    import importlib

    from birdtracks import whiteboard

    widget_module = importlib.import_module(
        "birdtracks.projectors.whiteboard.widget"
    )
    opened = []
    monkeypatch.setattr(
        widget_module,
        "_open_text_file",
        lambda path: opened.append(path.read_text(encoding="utf-8")),
    )

    document = whiteboard(debug=True)
    document.blocks = [
        {"id": "line", "source": r"\pair\otimes", "line_id": "line"},
    ]
    document.simplify_request = {
        "line_id": "line", "action": "evaluate", "revision": 1,
        "snapshots": {},
    }

    feedback = document.calculation_feedback
    assert feedback["action"] == "rejected"
    assert feedback["reason"]
    assert "Traceback (most recent call last)" in feedback["traceback"]
    assert "ValueError" in feedback["traceback"]
    assert len(document.blocks) == 1
    assert "calculation_step" not in document.blocks[0]

    document.open_error_log_request = {
        "line_id": "line", "revision": 1,
    }

    assert len(opened) == 1
    assert "ValueError" in opened[0]


def test_pair_source_rejects_ordinary_addition_and_subtraction() -> None:
    with pytest.raises(NotImplementedError, match=r"\\\\oplus"):
        pair_expression_from_blocks(
            [{"id": "line", "source": r"\pair + \pair"}],
            {
                "line:pair:0": Editor(PairExpression()),
                "line:pair:1": Editor(PairExpression()),
            },
        )


@pytest.mark.parametrize("source", [r"\pair + 2", r"2 - \pair"])
def test_scalar_addition_and_subtraction_with_pairs_is_not_implemented(
    source: str,
) -> None:
    with pytest.raises(NotImplementedError, match="scalars and pairs"):
        pair_expression_from_blocks(
            [{"id": "line", "source": source}],
            {"line:pair:0": Editor(PairExpression())},
        )


@pytest.mark.parametrize(
    "operator", ["+", "-", r"\times", r"\oplus", r"\otimes"]
)
def test_every_pair_birdtrack_operation_is_not_implemented(
    operator: str,
) -> None:
    source = rf"\pair {operator} \birdtracks"
    with pytest.raises(NotImplementedError, match="mixing pairs and birdtracks"):
        pair_expression_from_blocks(
            [{"id": "line", "source": source}],
            {"line:pair:0": Editor(PairExpression())},
        )


def test_mixed_pair_birdtrack_error_stops_whiteboard_calculation() -> None:
    pytest.importorskip("anywidget")
    from birdtracks import whiteboard

    document = whiteboard(debug=True)
    document.blocks = [{
        "id": "line", "line_id": "line",
        "source": r"\pair\otimes\birdtracks",
    }]
    document.simplify_request = {
        "line_id": "line", "action": "evaluate", "revision": 1,
        "snapshots": {},
    }

    feedback = document.calculation_feedback
    assert feedback["action"] == "rejected"
    assert "mixing pairs and birdtracks" in feedback["reason"]
    assert "NotImplementedError" in feedback["traceback"]
    assert len(document.blocks) == 1
    assert "calculation_step" not in document.blocks[0]


def test_assigned_pair_and_birdtrack_operation_is_not_implemented() -> None:
    pytest.importorskip("anywidget")
    from birdtracks import Projector, whiteboard

    document = whiteboard(debug=True)
    document.blocks = [
        {"id": "pair-definition", "line_id": "pair-definition",
         "source": r"A\def \pair"},
        {"id": "projector-definition", "line_id": "projector-definition",
         "source": r"P\def \birdtracks"},
        {"id": "use", "line_id": "use", "source": r"A\oplus P"},
    ]
    document.embedded_pairs[0].pair_expression = PairExpression().state()
    projector = document.embedded_projectors[0]
    projector._configured_projector = Projector([])
    projector.saved_revision += 1

    document.simplify_request = {
        "line_id": "use", "action": "evaluate", "revision": 1,
        "snapshots": {},
    }

    feedback = document.calculation_feedback
    assert feedback["action"] == "rejected"
    assert "mixing pairs and birdtracks" in feedback["reason"]
    assert "NotImplementedError" in feedback["traceback"]


def test_whiteboard_pair_evaluation_reveals_successive_python_lines() -> None:
    pytest.importorskip("anywidget")
    pytest.importorskip("pair_multiplication")
    from birdtracks import whiteboard

    document = whiteboard(debug=True)
    document.blocks = [
        {"id": "line", "source": r"\pair\otimes\pair", "line_id": "line"}
    ]
    pair = PairExpression((PairTerm(unbarred=(1,), n0=1),)).state()
    for editor in document.embedded_pairs:
        editor.pair_expression = pair

    document.simplify_request = {
        "line_id": "line",
        "action": "evaluate",
        "revision": 1,
        "snapshots": {},
    }
    assert len(document.blocks) == 2
    assert document.blocks[-1]["calculation_step"] == 1
    assert document.blocks[-1]["calculation_svg"]
    assert ">=</text>" in document.blocks[-1]["calculation_svg"]

    document.simplify_request = {
        "line_id": document.blocks[-1]["id"],
        "action": "evaluate",
        "revision": 2,
        "snapshots": {},
    }
    assert len(document.blocks) == 3
    assert document.blocks[-1]["calculation_step"] == 2


def test_pair_cell_colours_are_isolated_by_marker_occurrence() -> None:
    pytest.importorskip("anywidget")
    from birdtracks import whiteboard

    document = whiteboard(debug=True)
    document.blocks = [
        {"id": "line", "source": r"\pair \otimes \pair", "line_id": "line"}
    ]
    style = {"0:unbarred:0:0": {"fill": "#ff0000"}}

    document.embedded_pairs[0].pair_cell_styles = style

    assert document.embedded_pairs[0].pair_cell_styles == style
    assert document.embedded_pairs[1].pair_cell_styles == {}
    assert document.blocks[0]["pair_cell_styles"] == {"0": style}
