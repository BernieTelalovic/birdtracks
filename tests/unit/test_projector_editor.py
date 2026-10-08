"""Exact conformance checks for compensated editor redraw transactions."""

from copy import deepcopy
from fractions import Fraction
from unittest.mock import patch

import pytest

from birdtracks import Antisymmetriser, Projector, ProjectorSum, Symmetriser
from birdtracks.projectors.editor import EditorSession, EditorState
from birdtracks.projectors.widget import projector_sum_widget
from birdtracks.symbolic import SymbolicCoefficient


def session(coefficient=Fraction(1), factor=Fraction(1), product=False):
    nodes = [Antisymmetriser((1, 2, 3))]
    if product:
        nodes.append(Symmetriser((3, 4)))
    value = Projector(nodes, coefficient=coefficient)
    return EditorSession(EditorState.create(value, {
        "positions": {str(i): {"x": 10.0 + i, "y": 5.0} for i in range(len(nodes))},
        "free_levels": {"0": {"1": 4}},
        "boundary_orders": {"input": sorted(value.support), "output": sorted(value.support)},
        "line_colors": {"strand": "#123456"},
    }, outer_factor=factor))


def reorder(editor, sides):
    return editor.reorder({editor.state.node_ids[0]: sides}, base_revision=editor.state.revision)


@pytest.mark.parametrize("sides,sign", [
    ({"input": [2, 1, 3]}, -1),
    ({"output": [2, 1, 3]}, -1),
    ({"input": [2, 3, 1]}, 1),
    ({"output": [2, 3, 1]}, 1),
    ({"input": [2, 1, 3], "output": [2, 1, 3]}, 1),
    ({"input": [2, 3, 1], "output": [3, 1, 2]}, 1),
])
@pytest.mark.parametrize("coefficient,factor", [
    (Fraction(1), Fraction(1)), (Fraction(-2, 3), Fraction(1)),
    (Fraction(5, 7), Fraction(-3, 2)),
])
@pytest.mark.parametrize("product", [False, True])
def test_relative_reorder_preserves_expression_and_prefactor(sides, sign, coefficient, factor, product):
    editor = session(coefficient, factor, product)
    before = editor.state
    expected = factor * before.projector.collapse()
    with patch.object(Projector, "collapse", side_effect=AssertionError("interactive collapse")):
        after = reorder(editor, sides)
    assert after.projector == before.projector
    assert factor * after.projector.collapse() == expected
    assert after.displayed_coefficient == factor * coefficient * sign
    assert after.projector.connections == before.projector.connections
    assert after.projector.input_boundary == before.projector.input_boundary
    assert after.node_ids == before.node_ids and after.strand_ids == before.strand_ids
    assert after.presentation == before.presentation
    assert len(editor._undo) == 1
    assert after != before  # mathematical equality must not hide the redraw


def test_repeated_swap_undo_redo_and_roundtrip_restore_arrangement():
    editor = session(Fraction(-7, 11))
    initial = editor.state
    reorder(editor, {"input": [2, 1, 3]})
    intermediate = editor.state
    reorder(editor, {"input": [1, 2, 3]})
    assert editor.state == initial
    loaded = EditorSession.decode(editor.payload())
    assert loaded.state == initial
    loaded.undo(base_revision=loaded.state.revision)
    assert loaded.state == intermediate
    revision = loaded.state.revision
    loaded.redo(base_revision=revision)
    assert loaded.state == initial and loaded.state.revision > revision
    loaded.undo(base_revision=loaded.state.revision)
    loaded.undo(base_revision=loaded.state.revision)
    assert loaded.state == initial


def test_equivalent_sequences_and_multiple_a_nodes():
    editor = session()
    initial = editor.state.projector
    reorder(editor, {"input": [2, 1, 3]})
    reorder(editor, {"output": [2, 1, 3]})
    assert editor.state.projector.coefficient == initial.coefficient
    other = session()
    reorder(other, {"input": [2, 1, 3], "output": [2, 1, 3]})
    assert editor.state.projector.port_orders == other.state.projector.port_orders
    assert editor.state.projector.collapse() == other.state.projector.collapse()
    value = Projector([Antisymmetriser((1, 2)), Antisymmetriser((2, 3))])
    both = EditorSession(EditorState.create(value, {}))
    both.reorder({both.state.node_ids[0]: {"input": [2, 1]},
                  both.state.node_ids[1]: {"output": [3, 2]}}, base_revision=0)
    assert both.state.projector.coefficient == value.coefficient
    assert both.state.projector.collapse() == value.collapse()


@pytest.mark.parametrize("sides", [{"input": [1, 1, 3]}, {"wrong": [1, 2, 3]}, {"input": [True, 2, 3]}])
def test_invalid_commands_are_atomic(sides):
    editor = session()
    original = deepcopy(editor.payload())
    with pytest.raises(ValueError):
        reorder(editor, sides)
    assert editor.payload() == original
    with pytest.raises(ValueError, match="stale"):
        editor.undo(base_revision=42)
    assert editor.payload() == original
    with pytest.raises(ValueError, match="finite"):
        editor.reorder({editor.state.node_ids[0]: {"input": [2, 1, 3]}}, base_revision=0,
                       presentation={"positions": {"0": {"x": 0, "y": float("nan")}}})
    assert editor.payload() == original


def test_noop_and_new_branch_history():
    editor = session()
    reorder(editor, {"input": [1, 2, 3]})
    assert not editor._undo and editor.state.revision == 0
    reorder(editor, {"input": [2, 1, 3]})
    editor.undo(base_revision=1)
    reorder(editor, {"output": [2, 1, 3]})
    assert not editor._redo


def test_symbolic_factor_is_retained_without_entering_rational_algebra():
    x = SymbolicCoefficient.symbol("x")
    editor = session(Fraction(-2, 3), x)
    reorder(editor, {"input": [2, 1, 3]})
    assert editor.state.displayed_coefficient == Fraction(2, 3) * x
    restored = EditorSession.decode(editor.payload())
    assert restored.state == editor.state


def send(widget, action, **arguments):
    state = widget.editor_state
    widget.editor_request = {
        "request_id": f"test-{state['revision']}-{action}-{len(widget._editor_seen_requests)}",
        "term_id": state["term_id"], "base_revision": state["revision"],
        "action": action, **arguments,
    }
    assert not widget.editor_feedback.get("error"), widget.editor_feedback


@pytest.mark.parametrize('directions',[('left','right'),('right','left')])
def test_creation_direction_updates_committed_render_and_undo_without_topology_change(directions):
    from birdtracks.projectors.widget import projector_widget
    from birdtracks.projectors.editor import EditorSession

    widget=projector_widget(Projector([Antisymmetriser((1,2))]),mode='create')
    original=deepcopy(widget.editor_state)
    snapshot=widget.configuration.state()
    snapshot['graph']['in_direction'],snapshot['graph']['out_direction']=directions
    send(widget,'creation',snapshot=snapshot,node_ids=original['node_ids'],strand_ids=original['strand_ids'])
    assert (widget.projector.in_direction,widget.projector.out_direction)==directions
    assert (widget.graph['in_direction'],widget.graph['out_direction'])==directions
    assert widget.editor_state['graph']==widget.graph
    assert widget.editor_state['node_ids']==original['node_ids']
    assert widget.editor_state['strand_ids']==original['strand_ids']
    assert widget.editor_state['positions']==original['positions']
    assert EditorSession.decode(widget.configuration.state()['editor_state']).state.projector==widget.projector
    send(widget,'undo')
    assert widget.graph['in_direction']==widget.graph['out_direction']=='neutral'
    send(widget,'redo')
    assert (widget.graph['in_direction'],widget.graph['out_direction'])==directions


def test_canvas_sum_save_reload_and_stale_snapshot(tmp_path):
    pytest.importorskip("anywidget")
    a = Projector([Antisymmetriser((1, 2)), Symmetriser((2, 3))])
    b = Projector([Symmetriser((1, 2))])
    value = ProjectorSum(((a, Fraction(-2, 3)), (b, Fraction(5, 7))))
    path = tmp_path / "port-slice.canvas.json"
    canvas = projector_sum_widget(value, shared_editor=True, session=path, detangler=False, debug=True)
    child = next(e for e in canvas._term_editors if any(isinstance(n, Antisymmetriser) for n in e.projector.nodes))
    untouched = next(e for e in canvas._term_editors if e is not child)
    untouched_state = deepcopy(untouched.editor_state)
    before = child.editor_state
    presentation = {key: deepcopy(before[key]) for key in ("positions", "free_levels", "boundary_orders", "line_colors")}
    presentation["positions"]["0"]["y"] += 2.0
    send(child, "presentation", presentation=presentation)
    with patch.object(Projector, "collapse", side_effect=AssertionError("interactive collapse")):
        send(child, "reorder", changes={child.editor_state["node_ids"][0]: {"input": [2, 1]}})
    assert canvas.current_projector_sum.collapse() == value.collapse()
    assert untouched.editor_state == untouched_state
    assert child.editor_state["display"]["sign"] == ""
    accepted = deepcopy(child.editor_state)
    child.save_snapshot = {"revision": 100, "graph": {}, "port_orders": {}}
    assert child.editor_state == accepted
    send(child, "save")
    from birdtracks.projectors.canvas_session import ProjectorCanvasSession
    stored = ProjectorCanvasSession.load(path)
    assert stored.expression().collapse() == value.collapse()
    reopened = stored.open(detangler=False, debug=True)
    restored = next(e for e in reopened._term_editors if e.editor_state["term_id"] == accepted["term_id"])
    assert restored.editor_state == accepted
    send(restored, "undo")
    assert restored.editor_state["positions"] == presentation["positions"]
    send(restored, "redo")
    assert reopened.current_projector_sum.collapse() == value.collapse()


def test_automatic_odd_layout_is_materialized_from_authoritative_algebra():
    from birdtracks import Connection, NodePort
    p = Projector([Antisymmetriser((1, 2)), Symmetriser((10,)), Symmetriser((20,))],
                  connections=[Connection(NodePort(1, 10), NodePort(0, 2)),
                               Connection(NodePort(2, 20), NodePort(0, 1))])
    canvas = projector_sum_widget(ProjectorSum((p,)), shared_editor=True, detangler=False)
    assert canvas.current_projector_sum.collapse() == p.collapse()
    child = canvas._term_editors[0]
    assert child.projector == child._source_projector
    assert "port_swap_sign" not in child.graph


def test_presentation_bridge_prevents_reorder_from_restoring_old_placement():
    editor = session()
    drawing = editor.state.presentation
    drawing["positions"]["0"]["y"] = 99.0
    reorder_state = editor.reorder({editor.state.node_ids[0]: {"output": [2, 1, 3]}},
                                  base_revision=0, presentation=drawing)
    assert reorder_state.presentation == drawing
    editor.undo(base_revision=1)
    assert editor.state.presentation == drawing


def test_configuration_replay_preserves_outer_negative_sign():
    p = Projector([Antisymmetriser((1, 2))], coefficient=Fraction(-2, 3))
    canvas = projector_sum_widget(ProjectorSum((p,)), shared_editor=True, detangler=False)
    child = canvas._term_editors[0]
    send(child, "reorder", changes={child.editor_state["node_ids"][0]: {"input": [2, 1]}})
    reopened = child.configuration.evaluate(detangler=False)
    assert reopened.current_projector_sum == canvas.current_projector_sum
    assert reopened._term_editors[0].editor_state == child.editor_state


def test_zero_one_port_symmetriser_and_selection():
    p = Projector([Symmetriser((1, 2)), Antisymmetriser((3,))], coefficient=0)
    editor = EditorSession(EditorState.create(p, {}))
    initial = editor.state
    editor.reorder({initial.node_ids[0]: {"input": [2, 1]}}, base_revision=0,
                   selection=[initial.node_ids[0]])
    assert editor.state.projector.coefficient == 0
    assert editor.state.selection == (initial.node_ids[0],)
    editor.undo(base_revision=1)
    assert editor.state == initial
    editor.reorder({initial.node_ids[1]: {"input": [3]}}, base_revision=2)
    assert editor.state.revision == 2


def test_invalid_save_and_duplicate_transport_requests_are_atomic():
    p = Projector([Antisymmetriser((1, 2))])
    canvas = projector_sum_widget(ProjectorSum((p,)), shared_editor=True, detangler=False)
    child = canvas._term_editors[0]
    original = deepcopy(child.editor_state)
    presentation = {key: deepcopy(original[key]) for key in ("positions", "free_levels", "boundary_orders", "line_colors")}
    presentation["positions"]["0"]["y"] += 1
    child.editor_request = {"request_id": "bad-save", "action": "save", "term_id": original["term_id"],
                            "base_revision": 0, "save_revision": -1, "presentation": presentation}
    assert child.editor_state == original
    assert "save revision" in child.editor_feedback["error"]
    send(child, "reorder", changes={original["node_ids"][0]: {"input": [2, 1]}})
    accepted = deepcopy(child.editor_state)
    previous = deepcopy(child.editor_request)
    previous["ignored_transport_field"] = True
    child.editor_request = previous
    assert child.editor_state == accepted
    assert len(child._editor_session._undo) == 1
