"""Intentional compatibility with the standalone column algorithm."""
import pytest

from birdtracks.pair_evaluation import evaluate, parse, render_tokens
from birdtracks.representations import pair_backend
from birdtracks.young_diagrams import PairExpression, PairTerm

pytest.importorskip('pair_multiplication')


def expression(*terms):
    return PairExpression(terms, tuple(t for i in range(len(terms)) for t in (('tensor', 'pair') if i else ('pair',))))


def test_written_operations_are_rendered_between_pair_terms():
    pair = PairTerm(unbarred=(1,), n0=1)
    drawing = pair_backend().draw_pair(pair.native())

    svg = render_tokens([(pair, drawing), 'sum', (pair, drawing), 'tensor', (pair, drawing)])

    assert 'data-operation="sum"' in svg
    assert 'data-operation="tensor"' in svg
    assert svg.count('data-operation="sum"') == 1
    assert svg.count('data-operation="tensor"') == 1
    assert svg.count('data-pair-token="pair"') == 3
    assert 'data-pair-token="sum"' in svg
    assert 'data-pair-token="tensor"' in svg
    assert 'data-natural-width=' in svg
    assert 'data-line-height=' in svg
    assert 'x1="14" y1="4" x2="14" y2="24"' in svg
    assert '⊕' not in svg
    assert '⊗' not in svg


def test_pair_boxes_have_opaque_backgrounds_and_inherit_equation_colour():
    from pair_multiplication.drawing import Cell, Drawing, Label

    drawing = Drawing(
        (
            Cell(0, 0),
            Cell(0, 1, dashed=True, labels=(Label('1'), Label('2', barred=True))),
            Cell(0, 2, bullet=True),
        ),
        1,
        3,
    )

    svg = render_tokens([(PairTerm(), drawing)])

    assert 'style="color:inherit"' in svg
    assert 'style="color:#111"' not in svg
    assert svg.count('fill="white"') == 3
    # The nested drawing root also carries the inherited stroke colour.
    assert svg.count('stroke="currentColor"') == 4
    assert svg.count('pointer-events="all"') == 3
    assert 'stroke="none">1' in svg


def test_pair_box_keys_are_unique_across_terms_in_an_equation():
    from pair_multiplication.drawing import Cell, Drawing

    drawing = Drawing((Cell(0, 0),), 1, 1)
    term = PairTerm(unbarred=(1,), n0=1)

    svg = render_tokens([(term, drawing), 'sum', (term, drawing)])

    assert 'data-cell="0:0"' in svg
    assert 'data-cell="1:0"' in svg


def test_evaluation_lines_can_include_a_leading_equals_sign():
    svg = render_tokens(['sum'], leading_equals=True)

    assert '>=</text>' in svg
    assert 'font-size="22"' in svg


def test_assigned_evaluation_lines_include_the_variable_and_default_n0():
    pair = PairTerm(unbarred=(1,), coefficient=2, n0=1)

    result = evaluate(
        expression(pair), leading_equals=True, leading_assignment="A"
    )

    assert len(result['lines']) == 2
    final = result['lines'][-1]['svg']
    assert 'font-size="22">A</text>' in final
    assert '>2<tspan baseline-shift="sub" font-size="12">1</tspan>' in final


def test_fundamental_square_columns_and_exact_result():
    pair = PairTerm(unbarred=(1,), n0=1)
    result = evaluate(expression(pair, pair))
    final = PairExpression.from_state(result['result'])
    assert {(t.unbarred, t.coefficient, t.n0) for t in final.terms} == {((2,), 1, 1), ((1, 1), 1, 2)}
    assert len(result['lines']) >= 3
    assert any('labeled' in line['caption'] for line in result['lines'])
    assert all('young-grid' not in line['svg'] and 'young-axis' not in line['svg'] for line in result['lines'])


def test_coefficients_n0_and_barred_orientation():
    result = evaluate(expression(PairTerm(barred=(1,), coefficient=-3, n0=7), PairTerm(unbarred=(1,), coefficient=10**25, n0=4)))
    terms = PairExpression.from_state(result['result']).terms
    assert {(t.barred, t.unbarred) for t in terms} == {((1,), (1,)), ((), ())}
    assert all(t.coefficient == -3 * 10**25 and t.n0 >= 7 for t in terms)


def test_bracket_distribution_collection_and_identity():
    fundamental = PairTerm(unbarred=(1,), n0=1)
    value = PairExpression((fundamental, fundamental, PairTerm(n0=5)), ('(', 'pair', 'sum', 'pair', ')', 'tensor', 'pair'))
    result = evaluate(value)
    assert PairExpression.from_state(result['result']) == PairExpression((PairTerm(unbarred=(1,), coefficient=2, n0=5),))
    assert evaluate(PairExpression(()))['result']['terms'] == []
    assert evaluate(PairExpression((PairTerm(coefficient=0),)))['result']['terms'] == []


def test_square_of_a_two_term_direct_sum_finishes_in_process():
    pair = PairTerm(unbarred=(1,), n0=1)
    value = PairExpression(
        (pair, pair, pair, pair),
        ("(", "pair", "sum", "pair", ")", "tensor",
         "(", "pair", "sum", "pair", ")"),
    )

    final = PairExpression.from_state(evaluate(value)["result"])

    assert {
        (term.unbarred, str(term.coefficient), term.n0)
        for term in final.terms
    } == {((2,), "4", 1), ((1, 1), "4", 2)}


def test_repeated_distributed_products_reuse_backend_stages(monkeypatch):
    backend = pair_backend()
    calls = []
    original = backend.tableau_classes.process_iterate_cands_unbarred

    def multiply(arguments):
        calls.append(arguments)
        return original(arguments)

    monkeypatch.setattr(
        backend.tableau_classes, "process_iterate_cands_unbarred", multiply
    )
    pair = PairTerm(unbarred=(1,), n0=1)
    value = PairExpression(
        (pair, pair, pair, pair),
        ("(", "pair", "sum", "pair", ")", "tensor",
         "(", "pair", "sum", "pair", ")"),
    )

    evaluate(value)

    assert len(calls) == 1


@pytest.mark.parametrize('syntax', [('(', 'pair'), ('pair', ')'), ('pair', 'tensor'), ('(', ')', 'pair')])
def test_invalid_equations_are_rejected(syntax):
    with pytest.raises(ValueError):
        parse(PairExpression(syntax=syntax))


def test_widget_evaluates_and_clears_stale_result():
    pytest.importorskip('anywidget')
    from birdtracks.projectors.widget import _projector_toolbar_widget
    toolbar = _projector_toolbar_widget('pairs', 'create')
    toolbar.create_kind = 'young'
    pair = PairTerm(unbarred=(1,), n0=1)
    toolbar.pair_expression = expression(pair, pair).state()
    toolbar.mode = 'evaluate'
    assert len(toolbar.pair_evaluation['lines']) >= 3
    toolbar.mode = 'create'
    assert toolbar.pair_evaluation == {}
    toolbar.pair_expression = PairExpression(syntax=('(', 'pair')).state()
    toolbar.mode = 'evaluate'
    assert 'closing bracket' in toolbar.pair_evaluation['error']


def test_three_factors_and_distinct_threshold_collection():
    pair = PairTerm(unbarred=(1,), n0=1)
    final = PairExpression.from_state(evaluate(expression(pair, pair, pair))['result'])
    assert {(t.unbarred, t.coefficient, t.n0) for t in final.terms} == {
        ((3,), 1, 1), ((2, 1), 2, 2), ((1, 1, 1), 1, 3)}
    adjoint = PairTerm((1,), (1,), n0=2)
    final = PairExpression.from_state(evaluate(expression(adjoint, adjoint))['result'])
    assert sorted((t.n0, t.coefficient) for t in final.terms if t.barred == t.unbarred == (1,)) == [(2, 1), (3, 1)]
