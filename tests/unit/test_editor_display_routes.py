"""Packed tensor columns own independent, stable presentation corridors."""

from copy import deepcopy
from fractions import Fraction
import json
from unittest.mock import patch

import pytest

from birdtracks import Antisymmetriser, Permutation, PermutationNode, Projector, Symmetriser
from birdtracks.projectors.editor import EditorSession
from birdtracks.projectors.editor_presentation import column_routes, display_route_domain
from birdtracks.projectors.layout import _node_layers, widget_graph
from tests.unit.test_editor_structural import session


def tensor_corridors():
    # A small synthetic tensor branch, not a saved whiteboard fixture. The
    # lower permutation swaps boundary labels 6/8; the display packs disjoint
    # operators from DIFFERENT algebra layers into the same column.
    return Projector([Symmetriser((1, 2)), Antisymmetriser((2, 3, 4)), Symmetriser((1, 2)),
                      Symmetriser((5, 6)),
                      PermutationNode(Permutation.from_cycle(6, 8), support=(6, 7, 8)),
                      Symmetriser((5, 6))], coefficient=Fraction(-1, 6))


def strand_id(state, label):
    return next(identity for controls in display_route_domain(state).values()
                for identity, global_label in controls.items() if global_label == label)


def test_legacy_manual_rows_are_reserved_before_automatic_rows():
    s = session(tensor_corridors())
    drawing = s.state.presentation
    drawing['free_levels']['0']['7'] = 6
    s.presentation_checkpoint(drawing, base_revision=0)
    rows = column_routes(s.state, widget_graph(s.state.projector)['geometry'])
    assert rows['0']['7'] == 6
    assert rows['0']['6'] != 6
    for levels in rows.values():
        assert len(levels.values()) == len(set(levels.values()))


def test_display_columns_do_not_alias_exact_layers_or_output_labels():
    s = session(tensor_corridors())
    before = s.state
    geometry = widget_graph(before.projector)['geometry']
    layers = _node_layers(before.projector)
    assert layers[2] == layers[3]  # these nodes are in DIFFERENT display columns
    anchor = before.node_ids[0]
    six, seven = strand_id(before, 6), strand_id(before, 7)
    old_rows = column_routes(before, geometry)
    with patch.object(Projector, 'collapse', side_effect=AssertionError('interactive collapse')):
        s.reroute({}, display_changes={anchor: {six: 7, seven: 6}}, base_revision=0, geometry=geometry)
    after = s.state
    rows = column_routes(after, geometry)
    assert rows['0']['6'] == 7
    assert rows['0']['7'] == 6
    assert rows['1'] == old_rows['1']
    assert rows['2'] == old_rows['2']
    assert after.projector is before.projector
    assert after.presentation['positions'] == before.presentation['positions']
    assert after.presentation['free_levels'] == before.presentation['free_levels']
    assert len(s._undo) == 1
    loaded = EditorSession.decode(json.loads(json.dumps(s.payload())))
    assert loaded.state == after
    loaded.undo(base_revision=1)
    assert loaded.state == before
    loaded.redo(base_revision=2)
    assert loaded.state == after
    assert loaded.state.projector.collapse() == before.projector.collapse()


@pytest.mark.parametrize('invalid', ['column', 'output-strand', 'active-strand', 'negative', 'fractional', 'boolean'])
def test_invalid_display_route_is_atomic(invalid):
    s = session(tensor_corridors())
    before = deepcopy(s.payload())
    anchor, identity, level = s.state.node_ids[0], strand_id(s.state, 6), 7
    if invalid == 'column':
        anchor = s.state.node_ids[4]  # hidden permutation is NOT a column
    elif invalid == 'output-strand':
        identity = s.state.strand_ids[-1]
    elif invalid == 'active-strand':
        # Input strand 1 enters an operator in column 0, so it has no free row.
        from birdtracks.projectors.editor_rewrites import edges
        identity = next(i for i, (kind, label, _) in zip(s.state.strand_ids, edges(s.state.projector), strict=True)
                        if kind == 'input' and label == 1)
    else:
        level = {'negative': -1, 'fractional': 1.5, 'boolean': True}[invalid]
    with pytest.raises(ValueError):
        s.reroute({}, display_changes={anchor: {identity: level}}, base_revision=0)
    assert s.payload() == before


def test_python_repairs_collisions_without_moving_operators():
    s = session(tensor_corridors())
    before = s.state
    anchor = before.node_ids[0]
    six, seven = strand_id(before, 6), strand_id(before, 7)
    geometry = widget_graph(before.projector)['geometry']
    s.reroute({}, display_changes={anchor: {six: 0, seven: 0}}, base_revision=0, geometry=geometry)
    rows = column_routes(s.state, geometry)['0']
    assert len(rows.values()) == len(set(rows.values()))
    assert rows['6'] not in (0, 1, 4, 5)
    assert rows['7'] not in (0, 1, 4, 5)
    assert s.state.presentation['positions'] == before.presentation['positions']
    assert s.state.presentation['display_routes'][anchor] == {six: rows['6'], seven: rows['7']}


def test_rewrite_preserves_unaffected_display_routes_and_stable_ids():
    s = session(tensor_corridors())
    geometry = widget_graph(s.state.projector)['geometry']
    anchor = s.state.node_ids[0]
    six, seven = strand_id(s.state, 6), strand_id(s.state, 7)
    s.reroute({}, display_changes={anchor: {six: 7, seven: 6}}, base_revision=0, geometry=geometry)
    before = s.state
    # Replacing the upper middle A leaves the tensor's first column untouched.
    replacement = Projector([Antisymmetriser((2, 3, 4))])
    s.replace_node(before.node_ids[1], replacement, base_revision=1, geometry=geometry)
    after = s.state
    assert after.presentation['display_routes'][anchor] == before.presentation['display_routes'][anchor]
    assert after.node_ids[0] == before.node_ids[0]
    assert strand_id(after, 6) == six
    assert strand_id(after, 7) == seven
    assert after.presentation['positions']['0'] == before.presentation['positions']['0']
    loaded = EditorSession.decode(json.loads(json.dumps(s.payload())))
    assert loaded.state == after
    loaded.undo(base_revision=2)
    assert loaded.state == before
    assert after.projector.collapse() == before.projector.collapse()


def test_rewrite_remaps_removed_column_anchor_by_surviving_members():
    s = session(tensor_corridors())
    geometry = widget_graph(s.state.projector)['geometry']
    anchor = s.state.node_ids[0]
    six, seven = strand_id(s.state, 6), strand_id(s.state, 7)
    s.reroute({}, display_changes={anchor: {six: 7, seven: 6}}, base_revision=0, geometry=geometry)
    before = s.state
    s.replace_node(anchor, Projector([Symmetriser((1, 2))]), base_revision=1, geometry=geometry)
    after = s.state
    assert anchor not in after.node_ids
    new_anchor = next(column for column, strands in display_route_domain(after).items()
                      if six in strands and seven in strands and column != before.node_ids[2])
    assert after.presentation['display_routes'] == {new_anchor: {six: 7, seven: 6}}
    assert before.node_ids[3] in after.node_ids
    assert after.projector.collapse() == before.projector.collapse()
    assert EditorSession.decode(s.payload()).state == after
