"""Source drafts and embedded values share one revisioned document boundary."""

from copy import deepcopy
from fractions import Fraction
from unittest.mock import patch

import pytest

from birdtracks import Antisymmetriser, Projector, whiteboard
from birdtracks.projectors.whiteboard.document import DocumentSession, parse_source
from birdtracks.projectors.widget import projector_widget


@pytest.mark.parametrize('source', ['x', 'x_1', r'\frac{1}{2} x', r'\mathcal{P}_{1}',
                                   r'\left(A+B\right)', r'B\def \pair', r'P\def \birdtracks',
                                   r'\text{notes [ok)}', r'$x$', r'\pair\oplus\pair'])
def test_complete_source_is_not_evaluated(source):
    with patch.object(Projector, 'collapse', side_effect=AssertionError('interactive collapse')):
        assert parse_source(source, 'line').source == source


@pytest.mark.parametrize('source', [r'\frac{1}{', r'\frac{1}', 'x_{', 'x_', 'x^', 'x+',
                                   r'P\def', r'\unknown', '\\', r'\birdtracks{', '$x',
                                   r'\frac{1}{0}', '(x', 'x}', 'x_1_2', 'x^1^2'])
def test_incomplete_or_invalid_source_preserves_last_valid_expression(source):
    s = DocumentSession([{'id': 'line', 'source': 'x'}])
    s.edit_source('line', source, base_revision=0)
    assert s.blocks[0]['source'] == source
    assert s.blocks[0]['source_edit']['error']
    assert s.committed_blocks[0]['source'] == 'x'
    assert DocumentSession(s.blocks).committed_blocks[0]['source'] == 'x'
    before = deepcopy(s.payload())
    with pytest.raises(ValueError, match='stale'):
        s.edit_source('line', 'old', base_revision=0)
    assert s.payload() == before


def send(board, action, **args):
    board.document_request = {'request_id': f'document-{len(str(board.document_request))}-{board.document_state["revision"]}',
                              'base_revision': board.document_state['revision'], 'action': action, **args}
    assert not board.document_feedback.get('error'), board.document_feedback


def test_direction_commits_keep_last_valid_tensor_until_factors_agree():
    from tests.unit.test_projector_editor import send as editor_command
    from birdtracks.projectors.whiteboard.calculation import calculate_projector_blocks

    p=Projector([Antisymmetriser((1,2))])
    board=whiteboard(debug=True)
    board.blocks=[{'id':'line','source':r'A \def \birdtracks \otimes \birdtracks',
                   'projector_snapshots':{'0':projector_widget(p).configuration.state(),
                                          '1':projector_widget(p).configuration.state()}},
                  {'id':'reference','source':'+ A'}]
    before=board.backend_projectors[0].projector
    for index,editor in enumerate(board.embedded_projectors):
        snapshot=editor.configuration.state()
        snapshot['graph']['in_direction']='left'
        snapshot['graph']['out_direction']='right'
        editor_command(editor,'creation',snapshot=snapshot,node_ids=editor.editor_state['node_ids'],
                       strand_ids=editor.editor_state['strand_ids'])
        if index==0:
            assert board.backend_projectors[0].projector==before
            explicit=dict(zip(board.embedded_projector_ids,board.embedded_projectors,strict=True))
            with pytest.raises(NotImplementedError,match='different directions'):
                calculate_projector_blocks(board.blocks,explicit)
    assert board.backend_projectors[0].projector.in_direction=='left'
    assert board.backend_projectors[0].graph['in_direction']=='left'


def test_draft_reload_keeps_live_diagram_identity_value_and_definition(tmp_path):
    p = Projector([Antisymmetriser((1,2))], coefficient=Fraction(-2,3))
    seed = projector_widget(p)
    board = whiteboard(tmp_path/'draft.whiteboard',debug=True)
    board.blocks = [{'id':'line','source':r'P\def \birdtracks','projector_snapshots':{'0':seed.configuration.state()}}]
    editor = board.embedded_projectors[0]
    identity = 'line:projector:0'
    initial = board._document_session.occurrence_value(identity)
    with patch.object(Projector, 'collapse', side_effect=AssertionError('interactive collapse')):
        send(board,'source',block_id='line',source=r'P\def \birdt')
    assert board.embedded_projectors[0] is editor
    assert board._document_session.occurrence_value(identity) is initial
    assert board._document_session.occurrences[identity] is editor
    assert board._document_session.source_value('line').references == (identity,)
    loaded = whiteboard(tmp_path/'draft.whiteboard',debug=True)
    assert loaded.blocks[0]['source'] == r'P\def \birdt'
    assert loaded.blocks[0]['source_edit']['committed_source'] == r'P\def \birdtracks'
    assert loaded.embedded_projectors[0].projector.collapse() == p.collapse()
    send(loaded,'source',block_id='line',source=r'P\def \birdtracks')
    assert not loaded.blocks[0]['source_edit']['error']


def test_draft_keeps_pair_and_validates_pair_commands_atomically(tmp_path):
    board = whiteboard(tmp_path/'pair.whiteboard',debug=True)
    board.blocks = [{'id':'line','source':r'B\def \pair'}]
    editor = board.embedded_pairs[0]
    send(board,'source',block_id='line',source=r'B\def \pa')
    assert board.embedded_pairs[0] is editor
    value = {**editor.pair_expression, 'terms':[{'kind':'pair','barred':[],'unbarred':[1],'coefficient':'1','n0':'1'}]}
    send(board,'pair',occurrence_id='line:pair:0',value=value)
    assert board.blocks[0]['source'] == r'B\def \pa'
    assert board._document_session.occurrence_value('line:pair:0').state() == editor.pair_expression
    before = deepcopy(board.document_state)
    board.document_request = {'request_id':'invalid-pair','base_revision':before['revision'],
                              'action':'pair','occurrence_id':'line:pair:0','value':{'terms':[{'kind':'pair','unbarred':[1,2]}]}}
    assert board.document_feedback.get('error')
    assert board.document_state == before
    loaded = whiteboard(tmp_path/'pair.whiteboard',debug=True)
    assert loaded.embedded_pairs[0].pair_expression == editor.pair_expression


def test_patch_preserves_untouched_snapshots_and_rejects_stale_source():
    s = DocumentSession([{'id':'line','source':'x','projector_snapshots':{'0':{'revision':12}}}])
    s.patch_blocks([{'id':'next','fields':{'source':'y'},'remove':[]}],['line','next'],base_revision=0)
    assert s.blocks[0]['projector_snapshots'] == {'0':{'revision':12}}
    before = s.payload()
    with pytest.raises(ValueError,match='stale'):
        s.patch_blocks([{'id':'line','fields':{'source':'old'},'remove':[]}],['line'],base_revision=0)
    assert s.payload() == before


@pytest.mark.parametrize('change',[
    {'fields':{'source_edit':{'committed_source':'stale'}},'remove':[]},
    {'fields':{},'remove':['source_edit']},
])
def test_frontend_cannot_replace_or_remove_python_parse_metadata(change):
    session = DocumentSession([{'id':'line','source':'x'}])
    session.edit_source('line',r'\frac{1}{',base_revision=0)
    before = session.payload()
    with pytest.raises(ValueError,match='Python-owned'):
        session.patch_blocks([{'id':'line',**change}],['line'],base_revision=session.revision)
    assert session.payload()==before
