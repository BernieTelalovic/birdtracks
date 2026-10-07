"""The same exact command protocol through every projector editing surface."""

from copy import deepcopy
from fractions import Fraction
import json
from unittest.mock import patch

import pytest

from birdtracks import Antisymmetriser, Projector, ProjectorSum, Symmetriser
from birdtracks.projectors.configuration import ProjectorConfiguration
from birdtracks.projectors.widget import projector_widget, projector_sum_widget
from birdtracks.projectors.whiteboard.widget import whiteboard, _result_source
from birdtracks.projectors.whiteboard.projector_codec import projector_codec
from birdtracks.projectors.whiteboard.calculation import evaluate_projector_expression
from birdtracks.projectors.whiteboard import EvaluationEnvironment, projector_backend


def send(child, action, **arguments):
    state = child.editor_state
    child.editor_request = {"request_id": f"conformance-{len(child._editor_seen_requests)}",
                            "term_id": state["term_id"], "base_revision": state["revision"],
                            "action": action, **arguments}
    assert not child.editor_feedback.get("error"), child.editor_feedback


def surface(kind, coefficient, path):
    p = Projector([Antisymmetriser((1, 2, 3)), Symmetriser((3, 4))], coefficient=coefficient)
    if kind == "widget":
        child = projector_widget(p, debug=True)
        def reopen():
            config = ProjectorConfiguration.from_state(child.projector, json.loads(json.dumps(child.configuration.state())))
            return projector_widget(child.projector, configuration=config, debug=True)
        return child, lambda: child.projector, reopen, p
    if kind == "canvas":
        from birdtracks import ProjectorCanvasSession
        canvas = projector_sum_widget(ProjectorSum((p,)), session=path, detangler=False, debug=True)
        return (canvas._term_editors[0], lambda: canvas.current_projector_sum,
                lambda: ProjectorCanvasSession.load(path).open(detangler=False, debug=True)._term_editors[0], p)
    if kind == "parsed":
        board = whiteboard(path, debug=True)
        seed = projector_widget(p, shared_editor=False)
        board.blocks = [{"id": "definition", "source": r"P\def \birdtracks",
                         "projector_snapshots": {"0": seed.configuration.state()}},
                        {"id": "line", "source": "+P"}]
        child = board.backend_projectors[0]
        child._conformance_document = board
        return child, lambda: child.projector, lambda: whiteboard(path, debug=True).backend_projectors[0], p
    board = whiteboard(path, debug=True)
    if kind == "symbolic":
        from birdtracks.symbolic import SymbolicCoefficient
        from birdtracks.projectors.whiteboard.calculation import SymbolicProjectorSum
        x = SymbolicCoefficient.symbol("x")
        source, terms = _result_source(SymbolicProjectorSum(((p, x), (Projector([]), x * 2))))
        board.blocks = [{"id": "line", "source": source, "read_only": True,
                         "calculation_group": "group", "calculation_step": 1, "calculation_terms": terms}]
        child = board.backend_projectors[0]
        child._conformance_document = board
        return child, lambda: child.projector, lambda: whiteboard(path, debug=True).backend_projectors[0], p
    if kind == "generated":
        source, terms = _result_source(ProjectorSum((p,)))
        board.blocks = [{"id": "line", "source": source, "read_only": True,
                         "calculation_group": "group", "calculation_step": 1,
                         "calculation_value": projector_codec.encode(ProjectorSum((p,))), "calculation_terms": terms}]
        board.backend_projectors[0]._conformance_document = board
        def value():
            return ProjectorSum(tuple(projector_codec.decode(t["value"]) for t in board.blocks[0]["calculation_terms"]))
        return board.backend_projectors[0], value, lambda: whiteboard(path, debug=True).backend_projectors[0], p
    body = p / coefficient
    seed = projector_widget(body, shared_editor=False)
    magnitude = abs(coefficient)
    factor = str(magnitude.numerator) if magnitude.denominator == 1 else rf"\frac{{{magnitude.numerator}}}{{{magnitude.denominator}}}"
    source = r"P\def " + ("- " if coefficient < 0 else "") + factor + r"\birdtracks"
    board.blocks = [{"id": "line", "source": source, "read_only": True,
                     "projector_snapshots": {"0": seed.configuration.state()}}]
    board.embedded_projectors[0]._conformance_document = board
    def value():
        return evaluate_projector_expression(board.blocks, {"line:projector:0": board.embedded_projectors[0]},
                                             EvaluationEnvironment(projector_backend))
    return board.embedded_projectors[0], value, lambda: whiteboard(path, debug=True).embedded_projectors[0], p


@pytest.mark.parametrize("kind", ["widget", "canvas", "generated", "inline", "parsed", "symbolic"])
@pytest.mark.parametrize("coefficient", [Fraction(1), Fraction(-2, 3), Fraction(5, 7)])
def test_reorder_undo_redo_and_persistence_conform(kind, coefficient, tmp_path):
    pytest.importorskip("anywidget")
    path = tmp_path / ("sequence.canvas.json" if kind == "canvas" else "sequence.whiteboard")
    child, value, reopen, original = surface(kind, coefficient, path)
    before = deepcopy(child.editor_state)
    node_id = before["node_ids"][0]
    drawing = {key: deepcopy(before[key]) for key in ("positions", "free_levels", "boundary_orders", "line_colors")}
    drawing["positions"]["0"]["y"] += 1
    send(child, "presentation", presentation=drawing)
    sequence = [{"input": [2, 1, 3]}, {"output": [2, 1, 3]},
                {"input": [3, 2, 1]}, {"input": [1, 2, 3]}, {"output": [1, 2, 3]}]
    for sides in sequence:
        old = deepcopy(child.editor_state)
        undo_count = len(child._editor_session._undo)
        with patch.object(Projector, "collapse", side_effect=AssertionError("interactive collapse")):
            send(child, "reorder", changes={node_id: sides})
        accepted = deepcopy(child.editor_state)
        assert len(child._editor_session._undo) == undo_count + 1
        assert value().collapse() == original.collapse()
        assert accepted["positions"] == drawing["positions"]
        send(child, "undo")
        assert child.editor_state["port_orders"] == old["port_orders"]
        assert value().collapse() == original.collapse()
        send(child, "redo")
        assert child.editor_state["port_orders"] == accepted["port_orders"]
        assert child.editor_state["display"] == accepted["display"]
        assert value().collapse() == original.collapse()
    state = deepcopy(child.editor_state)
    child.save_snapshot = {"revision": 0}  # The obsolete write cannot override a committed edit.
    assert child.editor_state == state
    send(child, "save")
    loaded = reopen()
    for key in ("node_ids", "strand_ids", "port_orders", "positions", "free_levels", "display", "can_undo", "can_redo"):
        assert loaded.editor_state[key] == child.editor_state[key]
    send(loaded, "undo")
    assert loaded.editor_state["port_orders"]["0"]["output"] == [2, 1, 3]


@pytest.mark.parametrize("kind", ["inline", "generated"])
def test_legacy_whiteboard_container_roundtrip_retains_exact_editor_payload(kind, tmp_path):
    from birdtracks.projectors.whiteboard import write_sidecar
    pytest.importorskip("anywidget")
    path = tmp_path / "legacy.whiteboard"
    child, value, _reopen, original = surface(kind, Fraction(-2, 3), path)
    send(child, "reorder", changes={child.editor_state["node_ids"][0]: {"input": [2, 1, 3]}})
    board = child._conformance_document
    write_sidecar(path, EvaluationEnvironment(projector_backend), codec=projector_codec,
                  document={"blocks": board.blocks, "title": "legacy"})
    assert json.loads(path.read_text())["version"] == 1
    loaded_board = whiteboard(path, debug=True)
    loaded = (loaded_board.embedded_projectors if kind == "inline" else loaded_board.backend_projectors)[0]
    assert loaded.editor_state["node_ids"] == child.editor_state["node_ids"]
    assert loaded.editor_state["port_orders"] == child.editor_state["port_orders"]
    assert loaded.editor_state["display"] == child.editor_state["display"]
    assert value().collapse() == original.collapse()


@pytest.mark.parametrize("kind", ["widget", "canvas", "generated", "inline", "parsed", "symbolic"])
def test_invalid_or_stale_commands_leave_every_surface_unchanged(kind, tmp_path):
    pytest.importorskip("anywidget")
    child, value, _reopen, original = surface(kind, Fraction(-2, 3), tmp_path / "atomic.whiteboard")
    accepted = deepcopy(child.editor_state)
    for revision, order in [(0, [1, 1, 3]), (99, [2, 1, 3])]:
        child.editor_request = {"request_id": f"invalid-{revision}", "term_id": accepted["term_id"],
                                "base_revision": revision, "action": "reorder",
                                "changes": {accepted["node_ids"][0]: {"input": order}}}
        assert child.editor_feedback.get("error")
        assert child.editor_state == accepted
        assert value().collapse() == original.collapse()


def test_detached_inline_editor_cannot_overwrite_a_reused_occurrence(tmp_path):
    pytest.importorskip("anywidget")
    old, _value, _reopen, _original = surface("inline", Fraction(-2, 3), tmp_path / "detached.whiteboard")
    board = old._conformance_document
    original_block = deepcopy(board.blocks[0])
    board.blocks = [{"id": "line", "source": ""}]
    board.blocks = [original_block]
    replacement = board.embedded_projectors[0]
    assert replacement is not old
    state, blocks = deepcopy(replacement.editor_state), deepcopy(board.blocks)
    send(old, "reorder", changes={old.editor_state["node_ids"][0]: {"input": [2, 1, 3]}})
    send(old, "save")
    assert replacement.editor_state == state
    assert board.blocks == blocks


def test_symbolic_projection_preserves_factors_and_scalar_occurrences(tmp_path):
    from birdtracks.symbolic import SymbolicCoefficient
    pytest.importorskip("anywidget")
    child, _value, reopen, _original = surface("symbolic", Fraction(-2, 3), tmp_path / "symbolic.whiteboard")
    board = child._conformance_document
    before = deepcopy(board.blocks[0]["calculation_terms"][0])
    send(child, "reorder", changes={child.editor_state["node_ids"][0]: {"input": [2, 1, 3]}})
    term = board.blocks[0]["calculation_terms"][0]
    assert projector_codec.decode(term["outer_factor"]) == SymbolicCoefficient.symbol("x")
    assert term["scalar_terms"] == before["scalar_terms"]
    assert term["factor_preview"]["even"] == before["factor_preview"]["odd"]
    loaded = reopen()
    assert loaded.editor_state["node_ids"] == child.editor_state["node_ids"]
