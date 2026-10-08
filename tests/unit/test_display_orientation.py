"""Small topology and oriented-coefficient cases, independent of saved examples."""

from fractions import Fraction
from unittest.mock import patch

import pytest

from birdtracks import Antisymmetriser, Connection, NodePort, Projector, ProjectorSum, Symmetriser
from birdtracks.projectors.display_graph import compile_display_graph
from birdtracks.projectors.layout import default_positions, widget_graph
from birdtracks.projectors.widget import _projector_from_state
from birdtracks.projectors.simplification import recursive_expand_node
from birdtracks.projectors.whiteboard.projector_codec import projector_codec
from birdtracks.projectors.whiteboard.widget import _result_source, whiteboard


def reconstruct(graph):
    return _projector_from_state(graph, {
        str(n['index']): {'input': n['input_labels'], 'output': n['output_labels']}
        for n in graph['nodes']
    }, {'input': graph['boundary_labels'], 'output': graph['boundary_labels']})


@pytest.mark.parametrize('coefficient', [Fraction(1), Fraction(-2, 3), Fraction(5, 7)])
@pytest.mark.parametrize('sides', [
    {'input': (2, 1, 3), 'output': (1, 2, 3)},
    {'input': (1, 2, 3), 'output': (2, 1, 3)},
    {'input': (2, 1, 3), 'output': (2, 1, 3)},
])
def test_explicit_orientation_is_not_compensated_again(coefficient, sides):
    p = Projector([Antisymmetriser((1, 2, 3))], coefficient=coefficient, port_orders={0: sides})
    g = widget_graph(p)
    assert g['coefficient'] == {'numerator': str(coefficient.numerator), 'denominator': str(coefficient.denominator)}
    assert reconstruct(g).collapse() == p.collapse()
    source, _ = _result_source(ProjectorSum((p,)))
    assert source.startswith('= - ' if coefficient < 0 else '= ')
    assert ('= - ' in source) == (coefficient < 0)


def test_connected_ports_with_disjoint_local_labels_have_separate_columns():
    p = Projector([Symmetriser((1, 2)), Antisymmetriser((3, 4))],
        connections=[Connection(NodePort(1, 3), NodePort(0, 2))],
        input_boundary={1: NodePort(0, 1), 2: NodePort(1, 3), 3: NodePort(1, 4)},
        output_boundary={1: NodePort(0, 1), 2: NodePort(0, 2), 3: NodePort(1, 4)})
    assert compile_display_graph(p).operator_columns == ((0,), (1,))
    assert p.detangle().collapse() == p.collapse()


def test_disconnected_ports_with_identical_local_labels_share_a_column():
    p = Projector([Symmetriser((1, 2)), Antisymmetriser((1, 2))], connections=[],
        input_boundary={1: NodePort(0, 1), 2: NodePort(0, 2), 3: NodePort(1, 1), 4: NodePort(1, 2)},
        output_boundary={1: NodePort(0, 1), 2: NodePort(0, 2), 3: NodePort(1, 1), 4: NodePort(1, 2)})
    assert compile_display_graph(p).operator_columns == ((0, 1),)
    pos = default_positions(p)
    assert pos['0']['x'] == pos['1']['x']
    assert p.detangle().collapse() == p.collapse()


def test_new_line_uses_the_same_oriented_value_for_text_and_diagram():
    p = Projector([Antisymmetriser((1, 2)), Symmetriser((10,)), Symmetriser((20,))],
        connections=[Connection(NodePort(1, 10), NodePort(0, 2)),
                     Connection(NodePort(2, 20), NodePort(0, 1))], coefficient=Fraction(2, 3))
    source, terms = _result_source(ProjectorSum((p,)))
    rendered = projector_codec.decode(terms[0]['value'])
    assert source == r'= - \frac{2}{3}R'
    assert rendered.coefficient == Fraction(-2, 3)
    assert rendered.port_orders_are_explicit
    assert widget_graph(rendered)['coefficient']['numerator'] == '-2'
    assert rendered.collapse() == p.collapse()
    assert _result_source(ProjectorSum((rendered,)))[0] == source


@pytest.mark.parametrize('edge', ['top', 'bottom'])
def test_contextual_recursion_preserves_expression_through_detangle(edge):
    p = Projector([Symmetriser((1, 2)), Antisymmetriser((7, 8, 9))],
        connections=[Connection(NodePort(1, 7), NodePort(0, 2))],
        input_boundary={1: NodePort(0, 1), 2: NodePort(1, 7), 3: NodePort(1, 8), 4: NodePort(1, 9)},
        output_boundary={1: NodePort(0, 1), 2: NodePort(0, 2), 3: NodePort(1, 8), 4: NodePort(1, 9)})
    expanded = recursive_expand_node(p, 1, side='input', edge=edge)
    assert expanded.collapse() == p.collapse()
    for term, _ in expanded:
        assert reconstruct(widget_graph(term)).collapse() == term.collapse()


def test_generated_line_reorder_updates_exact_occurrence_and_source_atomically():
    p = Projector([Antisymmetriser((1, 2, 3))], coefficient=Fraction(-2, 3))
    value = ProjectorSum((p,))
    source, terms = _result_source(value)
    board = whiteboard()
    board.blocks = [{'id': 'result', 'source': source, 'read_only': True,
        'calculation_group': 'group', 'calculation_step': 1,
        'calculation_terms': terms, 'calculation_value': projector_codec.encode(value)}]
    child = board.backend_projectors[0]
    assert hasattr(child, 'editor_state')
    initial = child.editor_state
    with patch.object(Projector, 'collapse', side_effect=AssertionError('interactive collapse')):
        child.editor_request = {'request_id': 'swap', 'term_id': initial['term_id'],
            'base_revision': initial['revision'], 'action': 'reorder',
            'changes': {initial['node_ids'][0]: {'input': [2, 1, 3]}}}
    block = board.blocks[0]
    assert block['source'] == r'= \frac{2}{3}R'
    updated = projector_codec.decode(block['calculation_terms'][0]['value'])
    assert updated.coefficient == Fraction(2, 3)
    assert updated.port_orders[0]['input'] == (2, 1, 3)
    assert updated.collapse() == value.collapse()
    assert board.backend_projectors[0] is child
    child.editor_request = {'request_id': 'undo', 'term_id': initial['term_id'],
        'base_revision': child.editor_state['revision'], 'action': 'undo'}
    assert board.blocks[0]['source'] == source
    assert board.backend_projectors[0] is child


@pytest.mark.parametrize('coefficient', [Fraction(1), Fraction(-2, 3), Fraction(5, 7)])
def test_result_product_reorder_keeps_other_sum_occurrences(coefficient):
    p = Projector([Antisymmetriser((1, 2, 3)), Symmetriser((3, 4))], coefficient=coefficient)
    q = Projector([Symmetriser((1, 2))], coefficient=Fraction(3, 5))
    aggregate = ProjectorSum((p, q))
    source, terms = _result_source(aggregate)
    board = whiteboard()
    board.blocks = [{'id': 'result', 'source': source, 'read_only': True,
        'calculation_group': 'group', 'calculation_step': 1,
        'calculation_terms': terms, 'calculation_value': projector_codec.encode(aggregate)}]
    index = next(i for i, child in enumerate(board.backend_projectors)
                 if any(isinstance(n, Antisymmetriser) for n in child.projector.nodes))
    child = board.backend_projectors[index]
    other = 1 - index
    other_value = terms[other]['value']
    state = child.editor_state
    with patch.object(Projector, 'collapse', side_effect=AssertionError('interactive collapse')):
        child.editor_request = {'request_id': 'product-swap', 'term_id': state['term_id'],
            'base_revision': state['revision'], 'action': 'reorder',
            'changes': {state['node_ids'][0]: {'output': [2, 1, 3]}}}
    updated = board.blocks[0]
    assert updated['calculation_terms'][other]['value'] == other_value
    assert child.projector.coefficient == -coefficient
    visible = ProjectorSum(projector_codec.decode(t['value']) for t in updated['calculation_terms'])
    assert visible.collapse() == aggregate.collapse()


def test_result_reopen_retains_ids_manual_placement_and_undo(tmp_path):
    p = Projector([Antisymmetriser((1, 2, 3))], coefficient=Fraction(-2, 3))
    aggregate = ProjectorSum((p,))
    source, terms = _result_source(aggregate)
    path = tmp_path / 'result'
    board = whiteboard(path)
    board.blocks = [{'id': 'result', 'source': source, 'read_only': True,
        'calculation_group': 'group', 'calculation_step': 1,
        'calculation_terms': terms, 'calculation_value': projector_codec.encode(aggregate)}]
    child = board.backend_projectors[0]
    state = child.editor_state
    presentation = child._editor_session.state.presentation
    presentation['positions']['0']['y'] += 2
    child.editor_request = {'request_id': 'saved-swap', 'term_id': state['term_id'],
        'base_revision': state['revision'], 'action': 'reorder', 'presentation': presentation,
        'changes': {state['node_ids'][0]: {'input': [2, 1, 3]}}}
    reopened = whiteboard(path)
    restored = reopened.backend_projectors[0]
    assert restored.editor_state['term_id'] == state['term_id']
    assert restored.editor_state['node_ids'] == state['node_ids']
    assert restored.positions == presentation['positions']
    assert restored.editor_state['can_undo']
    assert restored.projector.collapse() == p.collapse()
    restored.editor_request = {'request_id': 'restored-undo', 'term_id': state['term_id'],
        'base_revision': restored.editor_state['revision'], 'action': 'undo'}
    assert reopened.blocks[0]['source'] == source
    assert restored.positions == presentation['positions']
