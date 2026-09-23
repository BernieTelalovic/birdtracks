"""Representation editing stays separate from operator composition."""

import pytest

from birdtracks.young_diagrams import PairExpression, PairTerm, TableauLabel


def test_exact_ordered_document_roundtrip():
    expression = PairExpression((PairTerm((2, 1), (3,), -(10**30), 12), PairTerm()))
    assert PairExpression.from_state(expression.state()) == expression
    assert expression.state()["terms"][0]["coefficient"] == str(-(10**30))
    state = expression.state()
    state["terms"][0]["barred"].append(1)
    assert expression.terms[0].barred == (2, 1)


def test_deleting_last_term_preserves_zero_sum_on_save(tmp_path):
    pytest.importorskip("anywidget")
    from birdtracks.projectors.widget import projector_creator
    from birdtracks.projectors.canvas_session import ProjectorCanvasSession, load

    zero = PairExpression(())
    assert PairExpression.from_state(zero.state()) == zero
    assert zero.to_native_terms() == ()
    assert zero != PairExpression()  # one empty pair is the trivial representation
    canvas = projector_creator(session=tmp_path / "zero-pairs", detangler=False, debug=True)
    canvas._toolbar.create_kind = "young"
    canvas._toolbar.pair_expression = zero.state()
    canvas._save_step_button.click()
    assert load(tmp_path / "zero-pairs") == zero
    restored = ProjectorCanvasSession.load(tmp_path / "zero-pairs").open(detangler=False, debug=True)
    assert restored.current_pair_expression == zero


@pytest.mark.parametrize("changes", [
    {"unbarred": [1, 2]}, {"barred": [0]}, {"barred": [True]},
    {"coefficient": "x+"}, {"coefficient": 2}, {"n0": "-1"},
    {"n0": "1", "unbarred": [1], "barred": [1]}, {"kind": "product"},
])
def test_invalid_terms_are_rejected(changes):
    state = PairTerm().state() | changes
    with pytest.raises(ValueError):
        PairTerm.from_state(state)


def test_pair_renderer_and_native_metadata():
    pytest.importorskip("pair_multiplication")
    term = PairTerm((2, 1), (3, 1), -7, 9)
    native, coefficient = PairExpression((term,)).to_native_terms()[0]
    assert native.partition == ((2, 1), (3, 1))
    assert native.N0 == 9
    assert coefficient == -7
    drawing = term.drawing()
    assert [(c["row"], c["column"]) for c in drawing["cells"] if c["bullet"]] == [
        (2, 1), (3, 0), (3, 1)
    ]


def test_modes_preserve_birdtrack_state_and_save_young_document(tmp_path):
    pytest.importorskip("anywidget")
    from birdtracks.projectors.widget import projector_creator
    from birdtracks.projectors.canvas_session import ProjectorCanvasSession, load

    canvas = projector_creator(session=tmp_path / "pairs", detangler=False, debug=True)
    original = canvas.current_projector_sum
    editors = canvas._term_editors
    canvas._toolbar.create_kind = "young"
    expression = PairExpression((PairTerm((1,), (2,), -3, 4), PairTerm()),
                                ("(", "pair", ")", "tensor", "pair"))
    canvas._toolbar.pair_expression = expression.state()
    assert canvas.current_pair_expression == expression
    assert all(row.layout.display == "none" for row in canvas._rows)
    canvas._save_step_button.click()
    assert canvas._save_step_button.description == "Saved"
    assert load(tmp_path / "pairs") == expression
    restored = ProjectorCanvasSession.load(tmp_path / "pairs").open(detangler=False, debug=True)
    assert restored._toolbar.create_kind == "young"
    assert restored.current_pair_expression == expression
    assert restored.current_projector_sum == original
    canvas._toolbar.create_kind = "birdtracks"
    assert canvas._term_editors == editors
    assert canvas.current_projector_sum == original
    assert all(row.layout.display == "flex" for row in canvas._rows)


def test_widget_rejects_invalid_browser_state():
    pytest.importorskip("anywidget")
    from traitlets import TraitError
    from birdtracks.projectors.widget import _projector_toolbar_widget

    widget = _projector_toolbar_widget("test", "create")
    state = PairExpression().state()
    state["terms"][0]["coefficient"] = "x+"
    with pytest.raises(TraitError):
        widget.pair_expression = state
    assert widget.pair_expression == PairExpression().state()


def test_tableau_labels_roundtrip_and_renderer(tmp_path):
    pytest.importorskip("anywidget")
    pytest.importorskip("pair_multiplication")
    from birdtracks.projectors.widget import projector_creator
    from birdtracks.projectors.canvas_session import ProjectorCanvasSession

    value = PairTerm((2, 1), (2,), 1, 4, labels=(
        TableauLabel("unbarred", 0, 1, 2),
        TableauLabel("barred", 1, 0, -(10**30)),
    ))
    expression = PairExpression((value,))
    assert PairExpression.from_state(expression.state()) == expression
    labels = {(cell["row"], cell["column"]): cell["labels"]
              for cell in value.drawing()["cells"] if cell["labels"]}
    assert labels == {(0, 3): [{"text": "2", "barred": False}],
                      (1, 1): [{"text": str(-(10**30)), "barred": True}]}
    canvas = projector_creator(session=tmp_path / "tableau", detangler=False, debug=True)
    canvas._toolbar.create_kind = "young"
    canvas._toolbar.pair_expression = expression.state()
    canvas._save_step_button.click()
    restored = ProjectorCanvasSession.load(tmp_path / "tableau").open(detangler=False, debug=True)
    assert restored.current_pair_expression == expression


@pytest.mark.parametrize("label", [
    {"side": "other", "row": 0, "column": 0, "value": "1"},
    {"side": [], "row": 0, "column": 0, "value": "1"},
    {"side": "unbarred", "row": 0, "column": 1, "value": "1"},
    {"side": "unbarred", "row": -1, "column": 0, "value": "1"},
    {"side": "unbarred", "row": True, "column": 0, "value": "1"},
    {"side": "unbarred", "row": 0, "column": 0, "value": "1/2"},
])
def test_invalid_tableau_labels_are_rejected(label):
    state = PairTerm((), (1,), n0=1).state()
    state["labels"] = [label]
    with pytest.raises(ValueError):
        PairTerm.from_state(state)


def test_duplicate_tableau_labels_are_rejected():
    label = TableauLabel("unbarred", 0, 0, 1)
    with pytest.raises(ValueError, match="duplicate"):
        PairTerm((), (1,), n0=1, labels=(label, label))


def test_unevaluated_syntax_roundtrip_and_export_guard():
    expression = PairExpression((PairTerm(), PairTerm()),
                                ("(", "pair", ")", "tensor", "pair"))
    assert PairExpression.from_state(expression.state()) == expression
    with pytest.raises(ValueError, match="evaluated"):
        expression.to_native_terms()
    # Partial bracket input is a valid edit document.
    assert PairExpression.from_state(PairExpression(syntax=("(", "pair")).state()).syntax == ("(", "pair")


@pytest.mark.parametrize("syntax", [["pair", "pair"], ["unknown"], "pair", [1]])
def test_invalid_expression_syntax(syntax):
    with pytest.raises(ValueError):
        PairExpression.from_state(PairExpression().state() | {"syntax": syntax})


def test_explicit_singleton_roundtrip():
    term = PairTerm(singleton=True)
    assert PairTerm.from_state(term.state()) == term
    assert term.native().partition == ((), ())
    assert term.drawing()['symbol'] == '•'
    with pytest.raises(ValueError):
        PairTerm(unbarred=(1,), n0=1, singleton=True)
