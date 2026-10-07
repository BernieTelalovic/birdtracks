"""Opt-in adapter between the existing canvas and the shared port editor."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
from typing import Any

from .configuration import ProjectorConfiguration
from .editor import EditorSession, EditorState, _rational
from .symmetrisers import Antisymmetriser, Symmetriser
from .whiteboard.projector_codec import projector_codec

_PRESENTATION = ("positions", "free_levels", "boundary_orders", "line_colors")


def attach_editor(editor: Any, outer_factor: Fraction = Fraction(1)) -> None:
    """Attach to an evaluation term only; existing whiteboard/create paths remain legacy."""
    if getattr(editor, "_editor_session", None) is not None:
        return
    import traitlets

    saved = editor.configuration.state().get("editor_state")
    if saved:
        session = EditorSession.decode(saved)
    else:
        session = EditorSession(EditorState.create(
            editor.projector, {key: deepcopy(getattr(editor, key)) for key in _PRESENTATION},
            outer_factor=outer_factor,
        ))
        # Materialize the initial drawing in Python with one relative compensation.
        changes = {
            session.state.node_ids[i]: editor.port_orders[str(i)]
            for i, node in enumerate(session.state.projector.nodes)
            if isinstance(node, (Symmetriser, Antisymmetriser))
        }
        session.reorder(changes, base_revision=0)
        session = EditorSession(replace(session.state, revision=0))
    editor._editor_session = session
    if session.state.outer_factor not in {Fraction(-1), Fraction(1)}:
        raise ValueError("canvas term factors must be +/-1; rational magnitudes belong to Projector.coefficient")
    if not set(_PRESENTATION) <= set(session.state.presentation):
        raise ValueError("canvas editor state requires complete drawing fields")
    editor._editor_seen_requests = set()
    editor.add_traits(
        editor_state=traitlets.Dict().tag(sync=True),
        editor_request=traitlets.Dict().tag(sync=True),
        editor_feedback=traitlets.Dict().tag(sync=True),
    )

    def publish() -> None:
        state = session.state
        # Port redraws leave topology/layout intact. Reuse the rendering plan,
        # rather than running default layout on every command.
        graph = deepcopy(editor.graph)
        graph["coefficient"] = _rational(state.projector.coefficient)
        graph["base_coefficient"] = graph["coefficient"]
        graph["port_swap_sign"] = 1
        graph["editor_value"] = dict(projector_codec.encode(state.projector))
        graph["term_sign"] = "-" if state.outer_factor < 0 else "" if editor.term_leading else "+"
        graph["term_leading"] = editor.term_leading
        # The exact ordered value is authoritative, not the legacy layout sign.
        orders = {str(i): {side: list(order) for side, order in sides.items()}
                  for i, sides in state.projector.port_orders.items()}
        for node in graph["nodes"]:
            node["input_labels"] = orders[str(node["index"])]["input"]
            node["output_labels"] = orders[str(node["index"])]["output"]
        presentation = state.presentation
        coefficient = state.displayed_coefficient
        if not isinstance(coefficient, Fraction):
            raise ValueError("this canvas slice renders rational prefactors; symbolic state is retained by the model")
        display = {
            "coefficient": _rational(abs(coefficient)),
            "sign": "-" if coefficient < 0 else "" if editor.term_leading else "+",
        }
        snapshot = {
            "graph": graph, "port_orders": orders,
            **presentation, "effective_coefficient": _rational(coefficient),
            "editor_state": session.payload(),
        }
        configured = ProjectorConfiguration.from_state(state.projector, snapshot)
        envelope = {
            "version": 1, "revision": state.revision,
            "term_id": state.term_id, "node_ids": list(state.node_ids),
            "strand_ids": list(state.strand_ids), "selection": list(state.selection),
            "graph": graph, "port_orders": orders, **presentation, "display": display,
            "can_undo": bool(session._undo), "can_redo": bool(session._redo),
        }
        with editor.hold_trait_notifications():
            editor._configured_projector = state.projector
            editor._configuration = configured
            editor.graph = graph
            editor.term_sign = graph["term_sign"]
            editor.port_orders = orders
            for key in _PRESENTATION:
                setattr(editor, key, deepcopy(presentation.get(key, {})))
            editor.effective_coefficient = snapshot["effective_coefficient"]
            # One transport publication contains mathematical and drawing state.
            editor.editor_state = envelope

    def on_request(change: dict[str, object]) -> None:
        request = change["new"]
        if not isinstance(request, dict) or not request:
            return
        request_id = request.get("request_id")
        try:
            if not isinstance(request_id, str) or not request_id:
                raise ValueError("editor command requires a request ID")
            if request_id in editor._editor_seen_requests:
                editor.editor_feedback = {"request_id": request_id, "revision": session.state.revision}
                return
            if editor.mode != "evaluate" or not editor.active_line:
                raise ValueError("port editor commands require the active evaluation term")
            if request.get("term_id") != session.state.term_id:
                raise ValueError("editor command belongs to another occurrence")
            revision = request.get("base_revision")
            session._check_revision(revision)
            action = request.get("action")
            save_revision = request.get("save_revision", 0)
            if action == "save" and (isinstance(save_revision, bool)
                    or not isinstance(save_revision, int) or save_revision < 0):
                raise ValueError("save revision must be a nonnegative integer")
            if action == "reorder":
                session.reorder(request.get("changes", {}), base_revision=revision,
                                presentation=request.get("presentation"), selection=request.get("selection"))
            elif action == "undo":
                session.undo(base_revision=revision)
            elif action == "redo":
                session.redo(base_revision=revision)
            elif action in {"presentation", "save"}:
                session.presentation_checkpoint(request.get("presentation", session.state.presentation),
                                                base_revision=revision)
            else:
                raise ValueError("unsupported shared editor command")
            publish()
            editor._editor_seen_requests.add(request_id)
            if action == "save":
                saved_revision = max(editor.save_request + 1, save_revision)
                # Immutable payload, not an algebra reconstruction from frontend traits.
                editor.save_request = saved_revision
                editor.saved_revision = saved_revision
            editor.editor_feedback = {"request_id": request_id, "revision": session.state.revision}
        except (TypeError, ValueError, KeyError, IndexError) as error:
            editor._last_error = error
            editor.editor_feedback = {
                "request_id": request_id, "revision": session.state.revision, "error": str(error),
            }

    def on_mode(change: dict[str, object]) -> None:
        if change["new"] == "create":
            # Structural creation is a later migration. Retain the exact value
            # as the legacy starting point, but release shared command ownership.
            editor.editor_state = {}
            editor._editor_session = None
            editor.unobserve(on_request, names="editor_request")
            editor.unobserve(on_mode, names="mode")
            editor.unobserve(on_leading, names="term_leading")

    def on_leading(change: dict[str, object]) -> None:
        del change
        publish()

    editor.observe(on_request, names="editor_request")
    editor.observe(on_mode, names="mode")
    editor.observe(on_leading, names="term_leading")
    editor._publish_editor = publish
    publish()


def bridge_outer_factor(editor: Any, factor: Fraction) -> None:
    """Keep the existing canvas term-sign operation outside port history."""
    session = getattr(editor, "_editor_session", None)
    if session is not None and session.state.outer_factor != factor:
        session.state = replace(session.state, outer_factor=factor, revision=session.state.revision + 1)
        session._undo.clear()
        session._redo.clear()
        editor._publish_editor()


def shared_snapshot(editor: Any) -> dict[str, object] | None:
    """Return the accepted saved representation, independent of pending traits."""
    if getattr(editor, "_editor_session", None) is None:
        return None
    return editor.configuration.state()
