"""Focused structural editor invariants, with exact small-case oracles."""

from copy import deepcopy
from fractions import Fraction
import json
from unittest.mock import patch

import pytest

from birdtracks import Antisymmetriser, Symmetriser, Projector, ProjectorSum
from birdtracks.projectors.editor import EditorSession, EditorState
from birdtracks.projectors.editor_rewrites import edges, recursive_branches, replace_node
from birdtracks.projectors.layout import widget_graph, default_positions


def session(p):
    graph = widget_graph(p)
    return EditorSession(EditorState.create(p, {
        "positions": default_positions(p), "free_levels": graph["free_levels"],
        "boundary_orders": {"input": sorted(p.support), "output": sorted(p.support)},
        "line_colors": {},
    }))


def test_move_route_undo_and_json_history_keep_identical_algebra_object():
    s = session(Projector([Antisymmetriser((1, 2, 3)), Symmetriser((3, 4))], coefficient=Fraction(-2, 3)))
    initial = s.state
    s.move({initial.node_ids[0]: {"x": 61, "y": 47}}, base_revision=0)
    moved = s.state
    s.reroute({initial.strand_ids[0]: {"0": 3}}, base_revision=1)
    assert s.state.projector is initial.projector
    assert s.state.node_ids == initial.node_ids
    assert len(s._undo) == 2
    loaded = EditorSession.decode(json.loads(json.dumps(s.payload())))
    loaded.undo(base_revision=2)
    assert loaded.state == moved
    loaded.undo(base_revision=3)
    assert loaded.state == initial
    loaded.redo(base_revision=4)
    assert loaded.state == moved


@pytest.mark.parametrize("kind", [Antisymmetriser, Symmetriser])
@pytest.mark.parametrize("size", [2, 3, 4])
@pytest.mark.parametrize("side", ["input", "output"])
@pytest.mark.parametrize("edge", ["top", "bottom"])
def test_recursive_branches_preserve_exact_value_and_survivors(kind, size, side, edge):
    p = Projector([Symmetriser((size, size+1)), kind(tuple(range(1, size+1))),
                   Antisymmetriser((size+2, size+3))], coefficient=Fraction(-2, 3))
    s = session(p)
    node_id = s.state.node_ids[1]
    s.reorder({node_id:{"input": list(reversed(range(1, size+1)))}}, base_revision=0)
    before = s.state
    with patch.object(Projector, "collapse", side_effect=AssertionError("interactive collapse")), \
         patch.object(kind, "collapse", side_effect=AssertionError("factorial node expansion")):
        branches = s.expand(node_id, base_revision=before.revision, side=side, edge=edge)
    assert len(branches) == 2
    assert ProjectorSum(b.projector * b.outer_factor for b in branches).collapse() == before.projector.collapse()
    for b in branches:
        assert b.term_id != before.term_id
        assert b.node_ids[0] == before.node_ids[0]
        assert b.node_ids[-1] == before.node_ids[-1]
        assert b.presentation["positions"]["0"] == before.presentation["positions"]["0"]
        assert b.presentation["positions"][str(len(b.node_ids)-1)] == before.presentation["positions"]["2"]
        assert set(before.strand_ids) <= set(b.strand_ids)
        assert b.presentation["free_levels"] == before.presentation["free_levels"]
    assert s.state is before


def test_replacement_retains_survivors_and_structural_undo_roundtrip():
    p = Projector([Symmetriser((2, 3)), Antisymmetriser((1, 2)), Antisymmetriser((4, 5))], coefficient=Fraction(-5, 7))
    s = session(p)
    before = s.state
    replacement = Projector([Antisymmetriser((1, 2)), Antisymmetriser((1, 2))])
    with patch.object(Projector, "collapse", side_effect=AssertionError("interactive collapse")):
        s.replace_node(before.node_ids[1], replacement, base_revision=0)
    after = s.state
    assert after.projector.collapse() == p.collapse()
    assert after.node_ids[0] == before.node_ids[0]
    assert after.node_ids[-1] == before.node_ids[-1]
    assert set(before.strand_ids) <= set(after.strand_ids)
    loaded = EditorSession.decode(json.loads(json.dumps(s.payload())))
    loaded.undo(base_revision=1)
    assert loaded.state == before
    loaded.redo(base_revision=2)
    assert loaded.state == after
    payload = deepcopy(s.payload())
    with pytest.raises(ValueError):
        s.replace_node(after.node_ids[0], Projector([Symmetriser((8, 9))]), base_revision=1)
    assert s.payload() == payload


def test_invalid_reconnection_is_atomic_and_valid_swap_is_semantic():
    s = session(Projector([Antisymmetriser((1, 2))]))
    before = s.state
    input_ids = [identity for identity, e in zip(before.strand_ids, edges(before.projector)) if e[0] == "input"]
    def edit(label):
        return {"source":{"boundary":label}, "target":{"node_id":before.node_ids[0], "label":3-label}}
    payload = deepcopy(s.payload())
    with pytest.raises(ValueError):
        s.reconnect({input_ids[0]:edit(1)}, base_revision=0)
    assert s.payload() == payload
    s.reconnect({input_ids[0]:edit(1), input_ids[1]:edit(2)}, base_revision=0)
    assert s.state.projector.collapse() == (-before.projector).collapse()
    assert set(s.state.strand_ids) == set(before.strand_ids)
    s.undo(base_revision=1)
    assert s.state == before


def test_recursive_large_node_does_not_enumerate_permutations():
    s = session(Projector([Antisymmetriser(tuple(range(1, 13)))]))
    with patch.object(Antisymmetriser, "collapse", side_effect=AssertionError("factorial")):
        result = s.expand(s.state.node_ids[0], base_revision=0)
    assert len(result) == 2
    assert max(len(b.node_ids) for b in result) <= 5


def test_recursive_local_placement_leaves_room_for_visible_boxes_and_crossings():
    p = Projector([Antisymmetriser((1,2,3))])
    s = session(p)
    geometry = widget_graph(p)["geometry"]
    branches = s.expand(s.state.node_ids[0],base_revision=0,edge="top",geometry=geometry)
    visible = [position for i,position in branches[1].presentation["positions"].items()
               if isinstance(branches[1].projector.nodes[int(i)],Antisymmetriser)]
    assert len(visible) == 2
    assert abs(visible[0]["x"]-visible[1]["x"]) >= geometry["node_width"] + geometry["step"]


def test_recursive_local_placement_reuses_compatible_survivor_columns():
    from birdtracks.projectors.display_graph import compile_display_graph
    p = Projector([Symmetriser((1,2)),Antisymmetriser((2,3,4)),Symmetriser((1,2))])
    s = session(p)
    before = s.state
    branch = s.expand(before.node_ids[1],base_revision=0,edge="top",geometry=widget_graph(p)["geometry"])[1]
    positions = branch.presentation["positions"]
    for column in compile_display_graph(branch.projector).operator_columns:
        assert len({positions[str(i)]["x"] for i in column}) == 1
    for identity in (before.node_ids[0],before.node_ids[-1]):
        assert positions[str(branch.node_ids.index(identity))] == before.presentation["positions"][str(before.node_ids.index(identity))]
    assert ProjectorSum(b.projector for b in s.expand(before.node_ids[1],base_revision=0,edge="top")).collapse() == p.collapse()


def test_local_placement_fits_box_widths_between_fixed_dependent_neighbours():
    p = Projector([Symmetriser((1,2)),Antisymmetriser((1,2,3)),Symmetriser((1,2))])
    s = session(p)
    geometry = widget_graph(p)["geometry"]
    branch = s.expand(s.state.node_ids[1],base_revision=0,edge="top",geometry=geometry)[1]
    boxes = [position for i,position in branch.presentation["positions"].items()
             if isinstance(branch.projector.nodes[int(i)],(Antisymmetriser,Symmetriser))]
    xs = sorted(p["x"] for p in boxes)
    assert all(b-a > geometry["node_width"] for a,b in zip(xs,xs[1:]))
    for i in (0,len(p.nodes)-1):
        assert branch.presentation["positions"][str(branch.node_ids.index(s.state.node_ids[i]))] == s.state.presentation["positions"][str(i)]


def test_selected_subgraph_identity_and_cut_validation_are_atomic():
    p = Projector([Symmetriser((2,3)),Antisymmetriser((1,2)),Antisymmetriser((1,2)),Symmetriser((4,5))],coefficient=Fraction(-2,3))
    s = session(p)
    old = s.state
    left,right = old.node_ids[1:3]
    inputs = {label:(right,label) for label in (1,2)}
    outputs = {label:(left,label) for label in (1,2)}
    replacement = Projector([Antisymmetriser((1,2))])
    with patch.object(Projector,'collapse',side_effect=AssertionError('interactive collapse')):
        s.replace_subgraph([left,right],replacement,input_ports=inputs,output_ports=outputs,base_revision=0)
    assert s.state.projector.collapse() == p.collapse()
    assert s.state.node_ids[0] == old.node_ids[0]
    assert s.state.node_ids[-1] == old.node_ids[-1]
    snapshot = deepcopy(s.payload())
    with pytest.raises(ValueError):
        s.replace_subgraph([s.state.node_ids[1]],replacement,input_ports={1:(s.state.node_ids[1],1)},output_ports=outputs,base_revision=1)
    assert s.payload() == snapshot


@pytest.mark.parametrize('ratio',[Fraction(2,3),Fraction(-2,3),Fraction(3,2)])
def test_inline_translation_retains_rational_replacement_scalars(ratio):
    from birdtracks.projectors.whiteboard.result_projection import project_inline_occurrence
    from birdtracks.projectors.whiteboard.calculation import evaluate_projector_expression
    from birdtracks.projectors.whiteboard import EvaluationEnvironment,projector_backend

    p = Projector([Antisymmetriser((1,2))])
    source = r'P\def -\frac{2}{3}\birdtracks'
    updated, body = project_inline_occurrence(source,source.index(r'\birdtracks'),p*ratio,Fraction(1),p)
    class Occurrence:
        _configured_projector = body
    value = evaluate_projector_expression([{'id':'line','source':updated}],{'line:projector:0':Occurrence()},EvaluationEnvironment(projector_backend))
    assert value.collapse() == (p*ratio*Fraction(-2,3)).collapse()
