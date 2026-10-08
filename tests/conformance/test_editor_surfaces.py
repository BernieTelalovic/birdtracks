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
        canvas._term_editors[0]._conformance_canvas = canvas
        return (canvas._term_editors[0], lambda: canvas.current_projector_sum,
                lambda: ProjectorCanvasSession.load(path).open(detangler=False, debug=True)._term_editors[0], p)
    if kind == "parsed":
        board = whiteboard(path, debug=True)
        seed = projector_widget(p)
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
    seed = projector_widget(body)
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
    send(child, "replace", node_id=child.editor_state["node_ids"][0],
         replacement=projector_codec.encode(Projector([Antisymmetriser((1,2,3)),Antisymmetriser((1,2,3))])))
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
    send(loaded,"undo")
    assert len(loaded.editor_state["node_ids"]) == 2
    send(loaded,"redo")
    assert loaded.editor_state["node_ids"] == child.editor_state["node_ids"]


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


@pytest.mark.parametrize("kind", ["widget", "canvas", "generated", "inline", "parsed", "symbolic"])
def test_display_corridor_transaction_and_history_roundtrip(kind, tmp_path):
    child, value, reopen, original = surface(kind, Fraction(-2, 3), tmp_path / "corridor.whiteboard")
    before = deepcopy(child.editor_state)
    anchor = before['graph']['display']['column_ids'][0]
    strand = next(item['editor_id'] for item in before['graph']['external_inputs'] if item['boundary_label'] == 4)
    drawing = child._editor_session.state.presentation
    # Swap the free line above A, with the operator shifted down one row in
    # the SAME transaction, as the existing frontend packing gesture does.
    drawing['positions']['0']['y'] += before['graph']['geometry']['level_spacing']
    with patch.object(Projector, 'collapse', side_effect=AssertionError('interactive collapse')):
        send(child, 'reroute', display_changes={anchor: {strand: 0}}, presentation=drawing)
    accepted = deepcopy(child.editor_state)
    assert len(child._editor_session._undo) == 1
    assert accepted['graph']['display_free_levels']['0']['4'] == 0
    assert accepted['positions']['1'] == before['positions']['1']
    assert accepted['node_ids'] == before['node_ids']
    assert accepted['strand_ids'] == before['strand_ids']
    assert value().collapse() == original.collapse()
    send(child, 'save')
    loaded = reopen()
    assert loaded.editor_state['display_routes'] == accepted['display_routes']
    assert loaded.editor_state['graph']['display_free_levels'] == accepted['graph']['display_free_levels']
    assert loaded.editor_state['positions'] == accepted['positions']
    send(loaded, 'undo')
    assert loaded.editor_state['positions'] == before['positions']
    assert loaded.editor_state['graph']['display_free_levels'] == before['graph']['display_free_levels']
    send(loaded, 'redo')
    assert loaded.editor_state['display_routes'] == accepted['display_routes']
    assert loaded.editor_state['positions'] == accepted['positions']


@pytest.mark.parametrize("kind", ["widget", "canvas", "generated", "inline", "parsed", "symbolic"])
def test_structural_presentation_and_replacement_roundtrip(kind, tmp_path):
    child, value, reopen, original = surface(kind, Fraction(-2, 3), tmp_path / "structural.whiteboard")
    before = deepcopy(child.editor_state)
    first, survivor = before["node_ids"]
    send(child, "move", changes={first:{"x":71,"y":42}})
    send(child, "reroute", changes={before["strand_ids"][0]:{"0":4}})
    drawing = deepcopy(child.editor_state)
    replacement = Projector([Antisymmetriser((1,2,3)),Antisymmetriser((1,2,3))])
    with patch.object(Projector, "collapse", side_effect=AssertionError("interactive collapse")):
        send(child, "replace", node_id=first, replacement=projector_codec.encode(replacement))
    assert child.editor_state["node_ids"][-1] == survivor
    assert child.editor_state["positions"]["2"] == before["positions"]["1"]
    assert value().collapse() == original.collapse()
    accepted = deepcopy(child.editor_state)
    send(child, "save")
    loaded = reopen()
    assert loaded.editor_state["node_ids"] == accepted["node_ids"]
    assert loaded.editor_state["strand_ids"] == accepted["strand_ids"]
    assert loaded.editor_state["strand_routes"] == accepted["strand_routes"]
    assert loaded.editor_state["positions"] == accepted["positions"]
    assert loaded.editor_state["automatic_positions"] == accepted["automatic_positions"]
    send(loaded, "undo")
    assert loaded.editor_state["node_ids"] == drawing["node_ids"]
    assert loaded.editor_state["positions"] == drawing["positions"]
    send(loaded, "redo")
    assert loaded.editor_state["node_ids"] == accepted["node_ids"]


@pytest.mark.parametrize("kind", ["widget", "canvas", "generated", "inline", "parsed", "symbolic"])
def test_tidy_is_one_undoable_reset_of_automatic_placement(kind, tmp_path):
    child, value, reopen, original = surface(kind, Fraction(-2, 3), tmp_path / "tidy.whiteboard")
    identity = child.editor_state["node_ids"][0]
    send(child, "move", changes={identity: {"x": 30, "y": 20}})
    pinned = deepcopy(child.editor_state)
    assert "0" not in pinned["automatic_positions"]
    history = len(child._editor_session._undo)
    send(child, "tidy")
    automatic = deepcopy(child.editor_state)
    assert len(child._editor_session._undo) == history + 1
    assert automatic["automatic_positions"] == automatic["positions"]
    assert value().collapse() == original.collapse()
    send(child, "save")
    loaded = reopen()
    assert loaded.editor_state["automatic_positions"] == automatic["automatic_positions"]
    send(loaded, "undo")
    assert loaded.editor_state["positions"] == pinned["positions"]
    assert loaded.editor_state["automatic_positions"] == pinned["automatic_positions"]
    send(loaded, "redo")
    assert loaded.editor_state["automatic_positions"] == automatic["automatic_positions"]


@pytest.mark.parametrize("kind", ["widget", "canvas", "generated", "inline", "parsed", "symbolic"])
def test_recursive_command_avoids_solver_and_preserves_survivors(kind, tmp_path):
    child, value, reopen, original = surface(kind, Fraction(-2, 3), tmp_path / "branches.whiteboard")
    first, survivor = child.editor_state["node_ids"]
    # Automatic columns may compact around the rewrite. Manual placement is
    # the authoritative invariant across every interface and persisted format.
    manual = {**child.editor_state["positions"]["1"]}
    manual["y"] += 0.25
    send(child, "move", changes={survivor: manual})
    position = deepcopy(child.editor_state["positions"]["1"])
    with patch.object(Projector, "collapse", side_effect=AssertionError("interactive collapse")), \
         patch.object(Antisymmetriser, "collapse", side_effect=AssertionError("factorial expansion")):
        send(child, "expand", node_id=first, edge="top")
    branches = child._expanded_editor_states
    assert len(branches) == 2
    expected = original if kind != "inline" else original / Fraction(-2, 3)
    assert ProjectorSum(s.projector*s.outer_factor for s in branches).collapse() == expected.collapse()
    for s in branches:
        assert s.node_ids[-1] == survivor
        assert s.presentation["positions"][str(len(s.node_ids)-1)] == position
    if kind == "canvas":
        loaded = reopen()
        assert loaded.editor_state["node_ids"][-1] == survivor
    if kind in {"generated", "inline", "parsed", "symbolic"}:
        board = child._conformance_document
        assert len(board.blocks) >= 2
        generated = board.blocks[-1]
        assert len(generated["calculation_terms"]) == 2
        loaded_board = whiteboard(tmp_path / "branches.whiteboard", debug=True)
        assert len(loaded_board.backend_projectors) >= (2 if kind == "inline" else 3)
        assert loaded_board.backend_projectors[-1].editor_state["node_ids"][-1] == survivor
        if kind == "inline":
            result = ProjectorSum(projector_codec.decode(t["value"]) for t in generated["calculation_terms"])
            assert result.collapse() == original.collapse()


@pytest.mark.parametrize("kind", ["canvas", "generated", "inline", "parsed", "symbolic"])
def test_rewrite_line_undo_redo_survives_reload(kind, tmp_path):
    path = tmp_path / ("history.canvas.json" if kind == "canvas" else "history.whiteboard")
    child, _value, _reopen, original = surface(kind, Fraction(-2,3), path)
    if kind == "canvas":
        # Retain the canvas host (surface's value accessor deliberately hides it).
        from birdtracks import ProjectorCanvasSession
        host = ProjectorCanvasSession.load(path).open(detangler=False,debug=True)
        child = host._term_editors[0]
    else:
        host = child._conformance_document
    send(child,"expand",node_id=child.editor_state["node_ids"][0])
    descendants = host._term_editors if kind == "canvas" else tuple(e for k,e in zip(host.backend_projector_ids,host.backend_projectors) if k.startswith(host.blocks[-1]["id"]+":"))
    ids = [e.editor_state["node_ids"] for e in descendants]
    presentation = [(e.editor_state["positions"],e.editor_state["strand_routes"]) for e in descendants]
    send(descendants[0],"undo")
    if kind == "canvas":
        assert len(host._line_states) == 1
        loaded = ProjectorCanvasSession.load(path).open(detangler=False,debug=True)
        send(loaded._term_editors[0],"redo")
        assert len(loaded._line_states) == 2
        assert [e.editor_state["node_ids"] for e in loaded._term_editors] == ids
        assert [(e.editor_state["positions"],e.editor_state["strand_routes"]) for e in loaded._term_editors] == presentation
        assert loaded.current_projector_sum.collapse() == original.collapse()
    else:
        assert "editor_rewrite_redo" in host.blocks[-1]
        loaded = whiteboard(path,debug=True)
        parents = loaded.embedded_projectors if kind == "inline" else loaded.backend_projectors
        parent = parents[0] if kind == "inline" else next(e for k,e in zip(loaded.backend_projector_ids,parents) if k.startswith(host.blocks[-1]["id"]+":"))
        assert parent.editor_state["can_redo"]
        send(parent,"redo")
        restored = [e for k,e in zip(loaded.backend_projector_ids,loaded.backend_projectors) if k.startswith(loaded.blocks[-1]["id"]+":")]
        assert [e.editor_state["node_ids"] for e in restored] == ids
        assert [(e.editor_state["positions"],e.editor_state["strand_routes"]) for e in restored] == presentation


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


@pytest.mark.parametrize("kind", ["widget", "canvas", "generated", "inline", "parsed", "symbolic"])
def test_invalid_reconnection_leaves_every_surface_committed_state_unchanged(kind, tmp_path):
    child, _value, _reopen, _original = surface(kind, Fraction(-2, 3), tmp_path / "invalid.whiteboard")
    child.mode = "create"
    before = deepcopy(child.editor_state)
    history = deepcopy(child._editor_session.payload())
    wire = before["graph"]["external_inputs"][0]
    child.editor_request = {"request_id":"invalid-port", "term_id":before["term_id"],
                            "base_revision":before["revision"], "action":"reconnect",
                            "changes":{wire["editor_id"]:{"source":{"boundary":wire["boundary_label"]},
                                "target":{"node_id":before["node_ids"][wire["port"]["node"]], "label":999}}}}
    assert child.editor_feedback.get("error")
    assert child.editor_state == before
    assert child._editor_session.payload() == history


def test_reconnection_publishes_wire_ids_by_boundary_label_and_transfers_paint():
    child = projector_widget(Projector([Antisymmetriser((1, 2))]), mode="create", debug=True)
    before = deepcopy(child.editor_state)
    inputs = {e["boundary_label"]:e for e in before["graph"]["external_inputs"]}
    drawing = deepcopy(child._editor_session.state.presentation)
    drawing["line_colors"] = {"right-anchor:0->input:0:1":"#ff0000"}
    send(child,"presentation",presentation=drawing)
    changes = {inputs[label]["editor_id"]:{"source":{"boundary":label},
                "target":{"node_id":before["node_ids"][0],"label":3-label}} for label in (1,2)}
    send(child,"reconnect",changes=changes)
    reordered = child.editor_state["graph"]["external_inputs"]
    assert [e["boundary_label"] for e in reordered] == [2,1]
    for edge in reordered:
        assert edge["editor_id"] == inputs[edge["boundary_label"]]["editor_id"]
    assert child.editor_state["line_colors"]["right-anchor:0->input:0:2"] == "#ff0000"
    send(child,"undo")
    assert child.editor_state["graph"]["external_inputs"] == before["graph"]["external_inputs"]


def test_branching_rewrite_preserves_untouched_sum_occurrence_metadata(tmp_path):
    a = Projector([Antisymmetriser((1,2,3))], coefficient=Fraction(-2,3))
    b = Projector([Symmetriser((1,2))], coefficient=Fraction(5,7))
    canvas = projector_sum_widget(ProjectorSum((a,b)),session=tmp_path / "sum.canvas.json",detangler=False,debug=True)
    first, untouched = canvas._term_editors
    send(untouched,"move",changes={untouched.editor_state["node_ids"][0]:{"x":211,"y":103}})
    before = untouched._editor_session.state
    send(first,"expand",node_id=first.editor_state["node_ids"][0])
    survivors = [e._editor_session.state for e in canvas._term_editors if e._editor_session.state.node_ids == before.node_ids]
    assert len(survivors) == 1
    after = survivors[0]
    assert after.strand_ids == before.strand_ids
    assert after.presentation == before.presentation
    assert after.projector == before.projector
    assert canvas.current_projector_sum.collapse() == ProjectorSum((a,b)).collapse()


@pytest.mark.parametrize("kind", ["canvas", "generated", "symbolic"])
@pytest.mark.parametrize("full", [False, True])
def test_expansion_cleans_whole_line_with_exact_factors_and_persisted_history(kind, full, tmp_path):
    from birdtracks import Permutation, PermutationNode
    from birdtracks import ProjectorCanvasSession
    from birdtracks.symbolic import SymbolicCoefficient
    from birdtracks.projectors.whiteboard.result_projection import projector_terms_source, symbolic_projector_terms_source

    plain = Projector([Symmetriser((1,2)), Antisymmetriser((2,3,4)), Symmetriser((1,2))], coefficient=Fraction(1,3))
    target = Projector([Symmetriser((1,2)), Antisymmetriser((2,3,4)), Symmetriser((1,2)),
                        PermutationNode(Permutation.from_cycle(2,3),support=(2,3,4)),
                        Antisymmetriser((3,4)), Symmetriser((1,2))], coefficient=Fraction(-2,3))
    original = ProjectorSum((plain, target))
    path = tmp_path / ("cleanup.canvas.json" if kind == "canvas" else "cleanup.whiteboard")
    x, y = SymbolicCoefficient.symbol("x"), SymbolicCoefficient.symbol("y")
    if kind == "canvas":
        host = projector_sum_widget(original,session=path,detangler=False,debug=True)
        parents = host._term_editors
    else:
        host = whiteboard(path, debug=True)
        if kind == "symbolic":
            source, terms = symbolic_projector_terms_source(((plain,x),(target,x),(Projector(()),y)))
            fields = {}
        else:
            source, terms = projector_terms_source((plain,target))
            fields = {"calculation_value":projector_codec.encode(original)}
        host.blocks = [{"id":"cleanup", "source":source, "read_only":True,
                        "calculation_group":"cleanup", "calculation_step":1,
                        "calculation_terms":terms, **fields}]
        parents = host.backend_projectors
    child = next(e for e in parents if len(e.projector.nodes) == 6)
    # The kept S is manually pinned before cleanup, including when its branch
    # becomes the first representative of the combined term.
    send(child,"move",changes={child.editor_state["node_ids"][0]:{"x":11,"y":19}})
    before = deepcopy(child.editor_state)
    if full:
        send(child, "calculate_full", node_id=before["node_ids"][2])
    else:
        with patch.object(Projector,"collapse",side_effect=AssertionError("interactive collapse")):
            send(child,"expand",node_id=before["node_ids"][2],edge="top")
    descendants = host._term_editors if kind == "canvas" else [e for key,e in zip(host.backend_projector_ids,host.backend_projectors)
                                                             if key.startswith(host.blocks[-1]["id"]+":")]
    assert len(descendants) == 1
    merged = descendants[0]
    assert merged.projector.collapse() == (plain if kind == "symbolic" else plain*2).collapse()
    accepted = deepcopy(merged.editor_state)
    send(merged,"save")
    if kind == "canvas":
        assert host.current_projector_sum.collapse() == original.collapse()
        reopened = ProjectorCanvasSession.load(path).open(detangler=False,debug=True)
        loaded = reopened._term_editors[0]
    else:
        term = host.blocks[-1]["calculation_terms"][0]
        if kind == "symbolic":
            # The drawing keeps plain's rational coefficient; all symbolic
            # factors (including scalar-only terms) remain exact and external.
            p = projector_codec.decode(term["value"])
            factor = projector_codec.decode(term["outer_factor"])
            assert factor*p.coefficient == x*Fraction(2,3)
            assert projector_codec.decode(term["scalar_terms"][0]["outer_factor"]) == y
        reopened = whiteboard(path,debug=True)
        loaded = reopened.backend_projectors[-1]
    assert loaded.editor_state["node_ids"] == accepted["node_ids"]
    assert loaded.editor_state["positions"] == accepted["positions"]
    send(loaded,"undo")
    send(next(e for e in (reopened._term_editors if kind == "canvas" else reopened.backend_projectors)
              if len(e.projector.nodes)==6),"redo")
    restored = reopened._term_editors[0] if kind == "canvas" else reopened.backend_projectors[-1]
    assert restored.editor_state["node_ids"] == accepted["node_ids"]
    assert restored.editor_state["positions"] == accepted["positions"]


def test_cleanup_absorbs_an_untouched_term_carried_into_a_recursive_line(tmp_path):
    from birdtracks import Permutation, PermutationNode
    p = Projector([Antisymmetriser((2,3)),PermutationNode(Permutation.identity(),support=(1,2)),
                   Antisymmetriser((2,3)),Symmetriser((1,2))],coefficient=Fraction(1,2))
    other = Projector([Symmetriser((5,6))])
    canvas = projector_sum_widget(ProjectorSum((p,other)),session=tmp_path/"absorb.canvas.json",detangler=False,debug=True)
    copied = next(e for e in canvas._term_editors if len(e.projector.nodes)==4)
    identity = copied.editor_state["node_ids"][0]
    child = next(e for e in canvas._term_editors if len(e.projector.nodes)==1)
    original = canvas.current_projector_sum
    send(child,"expand",node_id=child.editor_state["node_ids"][0])
    kept = next(e for e in canvas._term_editors if identity in e.editor_state["node_ids"])
    assert sum(isinstance(n,Antisymmetriser) for n in kept.projector.nodes)==1
    assert canvas.current_projector_sum.collapse()==original.collapse()


@pytest.mark.parametrize("full", [False, True])
def test_standalone_expansion_also_publishes_cleaned_python_branches(full):
    from birdtracks import Permutation, PermutationNode
    p = Projector([Symmetriser((1,2)),Antisymmetriser((2,3,4)),Symmetriser((1,2)),
                   PermutationNode(Permutation.from_cycle(2,3),support=(2,3,4)),
                   Antisymmetriser((3,4)),Symmetriser((1,2))],coefficient=Fraction(-2,3))
    child = projector_widget(p,debug=True)
    if full:
        send(child, "calculate_full", node_id=child.editor_state["node_ids"][2])
    else:
        with patch.object(Projector,"collapse",side_effect=AssertionError("interactive collapse")):
            send(child,"expand",node_id=child.editor_state["node_ids"][2])
    assert len(child._expanded_editor_states)==1
    assert child.expanded_projector_sum.collapse()==p.collapse()


def test_large_standalone_recursive_cleanup_does_not_expand_for_equivalence():
    child = projector_widget(Projector([Antisymmetriser(range(1,13))]),debug=True)
    with patch.object(Projector,"collapse",side_effect=AssertionError("interactive collapse")), \
         patch.object(Antisymmetriser,"collapse",side_effect=AssertionError("factorial expansion")):
        send(child,"expand",node_id=child.editor_state["node_ids"][0])
    assert len(child._expanded_editor_states)==2


@pytest.mark.parametrize("kind", ["canvas", "generated", "inline", "parsed", "symbolic"])
def test_new_parent_edit_invalidates_undone_rewrite_line(kind, tmp_path):
    child, _value, _reopen, _original = surface(kind, Fraction(-2,3), tmp_path / "invalidate.whiteboard")
    host = child._conformance_canvas if kind == "canvas" else child._conformance_document
    send(child,"expand",node_id=child.editor_state["node_ids"][0])
    descendant = host._term_editors[0] if kind == "canvas" else host.backend_projectors[-1]
    send(descendant,"undo")
    assert child.editor_state["can_redo"]
    send(child,"move",changes={child.editor_state["node_ids"][0]:{"x":91,"y":83}})
    assert not child.editor_state["can_redo"]
    if kind == "canvas":
        assert not host._redo_lines
    else:
        assert "editor_rewrite_redo" not in host.blocks[-1]


def test_canvas_mode_switch_keeps_committed_occurrence_routes_and_history(tmp_path):
    child, _value, _reopen, _original = surface("canvas", Fraction(-2,3), tmp_path / "mode.canvas.json")
    host = child._conformance_canvas
    send(child,"move",changes={child.editor_state["node_ids"][0]:{"x":97,"y":83}})
    send(child,"reroute",changes={child.editor_state["strand_ids"][0]:{"0":4}})
    before = deepcopy(child._editor_session.payload())
    host._toolbar.mode = "create"
    assert child.mode == "create"
    host._toolbar.mode = "evaluate"
    # Acknowledge the existing Save handshake, just as the frontend does.
    send(child,"save",save_revision=child.save_command)
    assert host._term_editors[0] is child
    assert child.mode == "evaluate"
    assert child.active_line
    assert child._editor_session.payload() == before
    send(child,"undo")
    assert not child.editor_state.get("strand_routes")


@pytest.mark.parametrize("factor", [1,-1])
def test_first_valid_creation_keeps_shared_rewrite_host_after_mode_switch(factor):
    from birdtracks.projectors.widget import projector_creator
    host = projector_creator(detangler=False,debug=True)
    child = host._term_editors[0]
    if factor < 0:
        host._toolbar.add_term_request = {'sign': -1, 'revision': 1}
        send(child, 'save', save_revision=child.save_command)
        send(child, 'delete_term')
        child = host._term_editors[0]
    p = Projector([Antisymmetriser((1,2,3))])
    seed = projector_widget(p)
    snapshot = seed.configuration.state()
    from tests.editor_protocol_helpers import create_editor
    create_editor(child, snapshot)
    accepted = deepcopy(child._editor_session.payload())
    assert child._editor_session.state.outer_factor == factor
    host._toolbar.mode = "evaluate"
    for other in host._term_editors:
        if other is not child:
            send(other, 'save', save_revision=other.save_command)
    send(child,"save",save_revision=child.save_command)
    assert host._term_editors[0] is child
    assert child.mode == "evaluate"
    assert child._editor_session.payload() == accepted
    send(child,"expand",node_id=child.editor_state["node_ids"][0])
    assert len(host._line_states) == 2
    assert host.current_projector_sum.collapse() == (p*factor).collapse()
