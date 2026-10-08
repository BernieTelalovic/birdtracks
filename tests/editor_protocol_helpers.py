"""Test gestures through the same versioned boundary as the shipped frontend."""

from copy import deepcopy
from uuid import uuid4


def send_editor(editor, action, **arguments):
    state = editor.editor_state
    editor.editor_request = {
        'request_id': f'test-{uuid4().hex}-{action}',
        'term_id': state['term_id'],
        'base_revision': state['revision'],
        'action': action,
        **arguments,
    }


def expand_editor(editor, proposal):
    state = editor.editor_state
    arguments = {'node_id': state['node_ids'][int(proposal['node'])]}
    if 'recursive_edge' in proposal:
        arguments['edge'] = proposal['recursive_edge']
    send_editor(editor, 'expand' if 'recursive_edge' in proposal else 'calculate_full', **arguments)


def create_editor(editor, snapshot):
    graph = snapshot['graph']
    edge_count = sum(len(graph[field]) for field in ('connections', 'external_inputs', 'external_outputs'))
    send_editor(editor, 'creation', snapshot=deepcopy(snapshot),
                node_ids=[None] * len(graph['nodes']), strand_ids=[None] * edge_count,
                save_revision=int(editor.save_command) or int(editor.saved_revision) + 1)
    assert not editor.editor_feedback.get('error'), editor.editor_feedback


def present_editor(editor, **fields):
    send_editor(editor, 'presentation', presentation={**editor._editor_session.state.presentation, **fields})
    assert not editor.editor_feedback.get('error'), editor.editor_feedback
