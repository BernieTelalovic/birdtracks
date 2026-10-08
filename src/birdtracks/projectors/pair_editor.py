"""Revisioned Python ownership for pair editing; no multiplication/rendering."""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any
from uuid import uuid4

from ..young_diagrams import PairExpression


class PairEditorSession:
    """Keep exact values, cell styles, and undo in one committed Python owner."""

    def __init__(self, value: object, styles: object = None) -> None:
        self.identity = uuid4().hex
        self.revision = 0
        self.value = PairExpression.from_state(value)
        self.styles = self._styles({} if styles is None else styles)
        self.undo: list[tuple[PairExpression, dict[str, Any]]] = []
        self.redo: list[tuple[PairExpression, dict[str, Any]]] = []

    @staticmethod
    def _styles(styles: object) -> dict[str, Any]:
        if not isinstance(styles, dict):
            raise ValueError('pair styles must be a mapping')
        return json.loads(json.dumps(styles, allow_nan=False, sort_keys=True))

    def state(self) -> dict[str, Any]:
        return {'version':1, 'session_id':self.identity, 'revision':self.revision,
                'value':self.value.state(), 'styles':deepcopy(self.styles),
                'can_undo':bool(self.undo), 'can_redo':bool(self.redo)}

    def payload(self) -> dict[str, Any]:
        def records(values):
            return [{'value':value.state(),'styles':deepcopy(styles)} for value,styles in values]
        return {**self.state(),'undo':records(self.undo),'redo':records(self.redo)}

    @classmethod
    def decode(cls, payload: object) -> PairEditorSession:
        if (not isinstance(payload, dict) or type(payload.get('version')) is not int
                or payload['version'] != 1 or not isinstance(payload.get('session_id'), str)
                or not payload['session_id']):
            raise ValueError('invalid pair editor payload')
        revision=payload.get('revision')
        if isinstance(revision,bool) or not isinstance(revision,int) or revision<0:
            raise ValueError('invalid pair editor revision')
        if not {'value', 'styles'} <= payload.keys():
            raise ValueError('pair payload requires value and styles')
        session=cls(payload['value'],payload['styles'])
        session.identity=payload['session_id']
        session.revision=revision
        for field in ('undo','redo'):
            records=payload.get(field,[])
            if (not isinstance(records,list) or any(not isinstance(item, dict)
                    or not {'value', 'styles'} <= item.keys() for item in records)):
                raise ValueError('invalid pair history')
            setattr(session,field,[(PairExpression.from_state(item['value']),session._styles(item['styles'])) for item in records])
        return session

    def commit(self, value: object = None, styles: object = None, *,
               operation: str = 'edit', remember: bool = True) -> None:
        """Validate a complete candidate before changing either value or history."""
        before = (self.value, self.styles)
        if operation in {'undo','redo'}:
            source, target = (self.undo,self.redo) if operation=='undo' else (self.redo,self.undo)
            if not source:
                return
            candidate = source.pop()
            target.append(before)
        elif operation=='edit':
            candidate = (self.value if value is None else PairExpression.from_state(value),
                         self.styles if styles is None else self._styles(styles))
            if candidate==before:
                return
            if remember:
                self.undo.append(before)
                self.redo.clear()
            else:
                self.undo.clear()
                self.redo.clear()
        else:
            raise ValueError('unknown pair command')
        self.value, self.styles = candidate
        self.revision += 1


def attach_pair_editor(editor: Any, payload: object = None) -> None:
    """Expose one command/state boundary, also used by document-owned pairs."""
    if hasattr(editor,'_pair_session'):
        return
    import traitlets

    session = (PairEditorSession.decode(payload) if payload is not None else
               PairEditorSession(editor.pair_expression, getattr(editor,'pair_cell_styles',{})))
    editor._pair_session = session
    editor.add_traits(pair_editor_state=traitlets.Dict().tag(sync=True),
                      pair_editor_request=traitlets.Dict().tag(sync=True),
                      pair_editor_feedback=traitlets.Dict().tag(sync=True),
                      pair_cell_styles=traitlets.Dict().tag(sync=True))
    seen = set()
    publishing = False

    def publish():
        nonlocal publishing
        publishing = True
        try:
            with editor.hold_trait_notifications():
                editor.pair_expression = session.value.state()
                editor.pair_cell_styles = deepcopy(session.styles)
                editor.pair_editor_state = session.state()
        finally:
            publishing = False

    def trusted_update(change):
        if publishing:
            return
        session.commit(editor.pair_expression,editor.pair_cell_styles,remember=False)
        publish()

    def command(change):
        request=change['new']
        identity=request.get('request_id')
        try:
            if not isinstance(identity,str) or not identity:
                raise ValueError('pair command requires a request ID')
            if identity in seen:
                editor.pair_editor_feedback={'request_id':identity,'revision':session.revision}
                return
            revision=request.get('base_revision')
            if (request.get('session_id')!=session.identity or isinstance(revision,bool)
                    or not isinstance(revision,int) or revision!=session.revision):
                raise ValueError('stale pair command; use committed pair state')
            if getattr(editor,'read_only',False) and ('value' in request or request.get('operation') in {'undo','redo'}):
                raise ValueError('pair value is read-only')
            session.commit(request.get('value'),request.get('styles'),operation=request.get('operation','edit'))
            publish()
            seen.add(identity)
            editor.pair_editor_feedback={'request_id':identity,'revision':session.revision}
        except (KeyError,TypeError,ValueError) as error:
            editor.pair_editor_feedback={'request_id':identity,'revision':session.revision,'error':str(error)}

    editor._publish_pair_editor=publish
    editor.observe(trusted_update,names=['pair_expression','pair_cell_styles'])
    editor.observe(command,names='pair_editor_request')
    publish()
