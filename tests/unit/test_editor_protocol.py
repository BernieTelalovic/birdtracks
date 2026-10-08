"""Ownership and persistence conformance for the mandatory editor protocol."""

from copy import deepcopy
from fractions import Fraction
import inspect
from uuid import uuid4

import pytest

from birdtracks import Antisymmetriser, Projector, ProjectorCanvasSession, ProjectorSum, Symmetriser, whiteboard
from birdtracks.projectors.editor import EditorSession
from birdtracks.projectors.pair_editor import PairEditorSession
from birdtracks.projectors.widget import projector_creator, projector_sum_widget, projector_widget
from birdtracks.young_diagrams import PairExpression, PairTerm
from tests.editor_protocol_helpers import create_editor, expand_editor, send_editor


def pair_request(editor, operation='edit', **arguments):
    state = editor.pair_editor_state
    editor.pair_editor_request = {
        'request_id': uuid4().hex, 'session_id': state['session_id'],
        'base_revision': state['revision'], 'operation': operation, **arguments,
    }
    assert not editor.pair_editor_feedback.get('error'), editor.pair_editor_feedback


def test_every_projector_editor_including_blank_has_the_same_owner():
    assert 'shared_editor' not in inspect.signature(projector_widget).parameters
    assert 'shared_editor' not in inspect.signature(projector_sum_widget).parameters
    editor = projector_creator(detangler=False)._term_editors[0]
    assert editor.editor_state['version'] == 1
    assert editor._editor_session.state.projector == editor.projector
    assert editor.editor_state['graph']['creator'] is True
    create_editor(editor, projector_widget(Projector([Antisymmetriser((1,2))])).configuration.state())
    assert editor.editor_state['node_ids']
    assert editor._editor_session._undo
    accepted = editor._editor_session.state.projector
    send_editor(editor, 'undo')
    assert not editor.projector.nodes
    send_editor(editor, 'redo')
    assert editor.projector == accepted


def test_incoming_render_traits_cannot_inject_a_value_or_rewrite():
    canvas = projector_sum_widget(ProjectorSum((Projector([Antisymmetriser((1,2))]),)), detangler=False)
    editor = canvas._term_editors[0]
    send_editor(editor, 'reorder', changes={editor.editor_state['node_ids'][0]: {'input':[2,1]}})
    accepted = deepcopy(editor._editor_session.payload())
    rows = len(canvas._line_states)
    editor.set_state({
        'graph': {}, 'port_orders': {}, 'positions': {}, 'line_colors': {},
        'effective_coefficient': {'numerator':'999','denominator':'1'},
        'editor_state': {}, 'editor_rewrite': {'parent_term_id':editor.editor_state['term_id'], 'states':[]},
        'saved_revision':999, 'save_snapshot':{'revision':999},
    })
    assert editor._editor_session.payload() == accepted
    assert len(canvas._line_states) == rows
    assert editor.saved_revision != 999
    assert EditorSession.decode(editor.editor_state['editor_payload']).payload() == accepted
    assert editor.configuration.state()['port_orders']['0']['input'] == [2,1]


def test_stale_creation_command_leaves_blank_owner_and_history_unchanged():
    editor = projector_creator(detangler=False)._term_editors[0]
    before = deepcopy(editor._editor_session.payload())
    request = {'request_id':'stale', 'term_id':editor.editor_state['term_id'],
               'base_revision':-1, 'action':'creation', 'snapshot':{}}
    editor.set_state({'editor_request':request})
    assert 'stale' in editor.editor_feedback['error']
    assert editor._editor_session.payload() == before


def test_shared_expansion_never_runs_an_implicit_global_layout_policy(tmp_path, monkeypatch):
    from birdtracks.projectors.detangle_training import LearnedDetangler

    # Exercise the policy boundary without requiring the optional Torch package.
    policy = LearnedDetangler(None, tmp_path/'unused.pt', {})

    def forbidden(*args, **kwargs):
        raise AssertionError('a shared rewrite must retain owned local placement')

    monkeypatch.setattr(LearnedDetangler, 'optimize', forbidden)
    value = Projector([Symmetriser((1,2)), Antisymmetriser((2,3))])
    canvas = projector_sum_widget(ProjectorSum((value,)), detangler=policy)
    editor = canvas._term_editors[0]
    expand_editor(editor, {'node':0})
    assert not editor.editor_feedback.get('error'), editor.editor_feedback
    assert len(canvas._line_states) == 2
    assert canvas._history[-1].collapse() == value.collapse()


@pytest.mark.parametrize('bad', [{'terms':[]}, {'version':True}, {'revision':True},
                               {'undo':[{}]}, {'styles':{'x':float('nan')}}])
def test_pair_payload_validation_is_exact(bad):
    session = PairEditorSession(PairExpression().state())
    payload = session.payload()
    if 'terms' in bad:
        payload['value'] = bad
    else:
        payload.update(bad)
    with pytest.raises(ValueError):
        PairEditorSession.decode(payload)


def test_pair_candidate_validation_does_not_change_history():
    session = PairEditorSession(PairExpression().state())
    session.commit(PairExpression((PairTerm(unbarred=(1,), n0=1),)).state())
    before = session.payload()
    with pytest.raises(ValueError):
        session.commit({'invalid':True}, {'cell':{'fill':'#ff0000'}})
    assert session.payload() == before


@pytest.mark.parametrize('kind', ['canvas', 'whiteboard'])
def test_pair_value_styles_and_undo_redo_survive_reload(kind, tmp_path):
    value = PairExpression((PairTerm(unbarred=(1,), n0=1, coefficient=Fraction(-2,3)),)).state()
    styles = {'0:unbarred:0:0':{'fill':'#9141ac'}}
    if kind == 'canvas':
        path = tmp_path/'pair.canvas.json'
        host = projector_creator(session=path, detangler=False)
        host._toolbar.create_kind = 'young'
        editor = host._toolbar
        pair_request(editor, value=value, styles=styles)
        host._save_step_button.click()
        loaded = ProjectorCanvasSession.load(path).open(detangler=False)._toolbar
    else:
        path = tmp_path/'pair.whiteboard'
        host = whiteboard(path, debug=True)
        host.blocks = [{'id':'line', 'source':r'B\def \pair'}]
        editor = host.embedded_pairs[0]
        host.document_request = {'request_id':'pair-edit','base_revision':host.document_state['revision'],
                                 'action':'pair','occurrence_id':'line:pair:0','session_id':editor._pair_session.identity,
                                 'value':value,'styles':styles}
        assert not host.document_feedback.get('error')
        host.save_request += 1
        loaded = whiteboard(path, debug=True).embedded_pairs[0]
    assert loaded._pair_session.identity == editor._pair_session.identity
    assert loaded._pair_session.value == editor._pair_session.value
    assert loaded._pair_session.styles == styles
    pair_request(loaded, 'undo')
    assert loaded._pair_session.value == PairExpression()
    pair_request(loaded, 'redo')
    assert loaded._pair_session.value.state() == value
    assert loaded._pair_session.styles == styles
    before = loaded._pair_session.payload()
    loaded.set_state({'pair_expression':PairExpression().state(), 'pair_editor_state':{}, 'pair_cell_styles':{}})
    assert loaded._pair_session.payload() == before


def test_pair_rejects_stale_revision_and_duplicate_request_is_idempotent():
    host = projector_creator(detangler=False)
    editor = host._toolbar
    pair_request(editor, value=PairExpression((PairTerm(unbarred=(1,), n0=1),)).state())
    before = editor._pair_session.payload()
    duplicate = deepcopy(editor.pair_editor_request)
    editor.set_state({'pair_editor_request':duplicate})
    assert editor._pair_session.payload() == before
    editor.pair_editor_request = {**duplicate,'request_id':'stale','base_revision':0}
    assert 'stale' in editor.pair_editor_feedback['error']
    assert editor._pair_session.payload() == before


def test_old_pair_identity_cannot_edit_a_recreated_occurrence(tmp_path):
    board = whiteboard(tmp_path/'replaced', debug=True)
    board.blocks = [{'id':'line','source':r'\pair'}]
    old_identity = board.embedded_pairs[0]._pair_session.identity
    board.blocks = [{'id':'line','source':'x'}]
    board.blocks = [{'id':'line','source':r'\pair'}]
    current = board.embedded_pairs[0]
    assert current._pair_session.identity != old_identity
    before = current._pair_session.payload()
    board.document_request = {'request_id':'late-pair','action':'pair','base_revision':board.document_state['revision'],
                              'occurrence_id':'line:pair:0','session_id':old_identity,
                              'value':PairExpression((PairTerm(unbarred=(1,), n0=1),)).state()}
    assert 'replaced' in board.document_feedback['error']
    assert current._pair_session.payload() == before


def test_document_comm_drops_legacy_snapshots_and_stale_calculations(tmp_path):
    board = whiteboard(tmp_path/'owned', debug=True)
    board.blocks = [{'id':'line','source':'x'}]
    before = deepcopy(board.document_state)
    board.set_state({'blocks':[{'id':'line','source':'old'}], 'document_state':{},
                     'simplify_request':{'line_id':'line','action':'evaluate','base_revision':-1,
                                         'snapshots':{'forged':{}}}})
    assert board.document_state == before
    assert board.calculation_feedback['action'] == 'rejected'
    board.document_request = {'request_id':'forge','action':'blocks','base_revision':before['revision'],
                              'order':['line'],'changes':[{'id':'line','fields':{'calculation_value':{}},'remove':[]}]}
    assert 'Python-owned' in board.document_feedback['error']
    assert board.document_state == before


def test_canvas_reload_ignores_stale_render_copy(tmp_path):
    from birdtracks.projectors.canvas_session import write_canvas_session

    path = tmp_path/'owned.canvas.json'
    canvas = projector_sum_widget(ProjectorSum((Projector([Antisymmetriser((1,2))], coefficient=Fraction(-2,3)),)),
                                  session=path, detangler=False)
    editor = canvas._term_editors[0]
    send_editor(editor, 'reorder', changes={editor.editor_state['node_ids'][0]:{'input':[2,1]}})
    saved = ProjectorCanvasSession.load(path).state()
    projection = saved['lines'][0]['terms'][0]['state']
    projection['graph'] = {'coefficient':{'numerator':'999','denominator':'1'}}
    projection['effective_coefficient'] = {'numerator':'999','denominator':'1'}
    write_canvas_session(path, saved)
    reopened = ProjectorCanvasSession.load(path).open(detangler=False)
    assert reopened.current_projector_sum == canvas.current_projector_sum
    assert reopened._term_editors[0].editor_state['node_ids'] == editor.editor_state['node_ids']
