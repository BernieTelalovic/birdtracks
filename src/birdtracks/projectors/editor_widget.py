"""Shared command adapter for every projector editing surface."""

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
    """Attach an authoritative session; incomplete creation drafts stay local."""
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
        editor_rewrite=traitlets.Dict().tag(sync=True),
    )

    def publish() -> None:
        state = session.state
        # Compile topology only after structural edits. Default positions from
        # that projection are discarded; committed/manual presentation wins.
        from .layout import widget_graph
        if getattr(editor, "_editor_render_nodes", None) != state.projector.nodes or getattr(editor, "_editor_render_edges", None) != (state.projector.connections, dict(state.projector.input_boundary), dict(state.projector.output_boundary)):
            graph = widget_graph(state.projector, editor.graph["geometry"])
        else:
            graph = deepcopy(editor.graph)
        editor._editor_render_nodes = state.projector.nodes
        editor._editor_render_edges = (state.projector.connections, dict(state.projector.input_boundary), dict(state.projector.output_boundary))
        graph["coefficient"] = _rational(state.projector.coefficient)
        graph["base_coefficient"] = graph["coefficient"]
        graph["editor_value"] = dict(projector_codec.encode(state.projector))
        graph["term_sign"] = "-" if state.outer_factor < 0 else "" if editor.term_leading else "+"
        graph["term_leading"] = editor.term_leading
        # The exact ordered value is authoritative.
        orders = {str(i): {side: list(order) for side, order in sides.items()}
                  for i, sides in state.projector.port_orders.items()}
        for node in graph["nodes"]:
            node["editor_id"] = state.node_ids[node["index"]]
            node["input_labels"] = orders[str(node["index"])]["input"]
            node["output_labels"] = orders[str(node["index"])]["output"]
        from .editor_rewrites import edges
        from .projector import NodePort
        strand_ids = dict(zip(edges(state.projector),state.strand_ids,strict=True))
        for item in graph["connections"]:
            item["editor_id"] = strand_ids["connection",NodePort(**item["source"]),NodePort(**item["target"])]
        for side,section in (("input","external_inputs"),("output","external_outputs")):
            for item in graph[section]:
                item["editor_id"] = strand_ids[side,item["boundary_label"],NodePort(**item["port"])]
        presentation = state.presentation
        from .editor_presentation import column_routes
        from .layout import _node_layers
        graph["display_free_levels"] = column_routes(state,graph["geometry"])
        # Disposable compatibility projection. Explicit concrete controls stay
        # in the envelope; a render cannot replace the committed presentation.
        graph["free_levels"] = deepcopy(presentation["free_levels"])
        node_layers = _node_layers(state.projector)
        for column,members in enumerate(graph["display"]["operator_columns"]):
            graph["free_levels"][str(node_layers[members[0]])] = graph["display_free_levels"][str(column)]
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
            "editor_payload": session.payload(),
            "effective_coefficient": snapshot["effective_coefficient"],
            "graph": graph, "port_orders": orders, **presentation, "display": display,
            "can_undo": bool(session._undo), "can_redo": bool(session._redo),
        }
        if hasattr(editor, "_editor_document_history"):
            document_undo, document_redo = editor._editor_document_history()
            envelope["can_undo"] |= document_undo
            envelope["can_redo"] |= document_redo
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
            if not editor.active_line:
                raise ValueError("editor commands require the active term")
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
                if editor.mode != "evaluate":
                    raise ValueError("redraw reordering requires evaluation mode")
                session.reorder(request.get("changes", {}), base_revision=revision,
                                presentation=request.get("presentation"), selection=request.get("selection"))
            elif action == "undo":
                if not session._undo and hasattr(editor, "_editor_document_command"):
                    editor._editor_document_command("undo")
                else:
                    session.undo(base_revision=revision)
            elif action == "redo":
                if not session._redo and hasattr(editor, "_editor_document_command"):
                    editor._editor_document_command("redo")
                else:
                    session.redo(base_revision=revision)
            elif action in {"presentation", "save"}:
                session.presentation_checkpoint(request.get("presentation", session.state.presentation),
                                                base_revision=revision)
            elif action == "move":
                if "presentation" in request:
                    session.presentation_checkpoint(request["presentation"], base_revision=revision)
                else:
                    session.move(request.get("changes", {}), base_revision=revision)
            elif action == "reroute":
                session.reroute(request.get("changes", {}), base_revision=revision,
                                presentation=request.get("presentation"))
            elif action == "reconnect":
                if editor.mode != "create":
                    raise ValueError("connectivity editing requires creation mode")
                session.reconnect(request.get("changes", {}), base_revision=revision)
            elif action == "replace":
                replacement = projector_codec.decode(request["replacement"])
                if "node_ids" in request:
                    def cut(raw):
                        return {int(label):(endpoint["node_id"],endpoint["label"]) for label,endpoint in raw.items()}
                    session.replace_subgraph(request["node_ids"], replacement,
                                             input_ports=cut(request["input_ports"]),output_ports=cut(request["output_ports"]),
                                             base_revision=revision,geometry=editor.graph["geometry"])
                else:
                    session.replace_node(request["node_id"], replacement, base_revision=revision,
                                         geometry=editor.graph["geometry"])
            elif action == "expand":
                if editor.mode != "evaluate":
                    raise ValueError("expansion requires evaluation mode")
                branches = session.expand(request["node_id"], base_revision=revision,
                                          edge=request.get("edge", "bottom"), side=request.get("side", "input"),
                                          geometry=editor.graph["geometry"])
                from .projector_sum import ProjectorSum
                editor._expanded_editor_states = branches
                editor._expanded_projector_sum = ProjectorSum(s.projector * s.outer_factor for s in branches)
                # Published after candidate validation. Hosts insert the entire
                # next equation line as their existing document transaction.
                editor.editor_rewrite = {"request_id": request_id, "base_revision": revision,
                                         "parent_term_id": session.state.term_id,
                                         "states": [s.payload() for s in branches]}
            elif action == "tidy":
                from .layout import default_positions, widget_graph
                drawing = session.state.presentation
                drawing["positions"] = default_positions(session.state.projector, editor.graph["geometry"])
                drawing["free_levels"] = widget_graph(session.state.projector, editor.graph["geometry"])["free_levels"]
                drawing.pop("strand_routes", None)
                session.presentation_checkpoint(drawing, base_revision=revision)
            elif action == "creation":
                if editor.mode != "create":
                    raise ValueError("connectivity drafts require creation mode")
                # The browser supplies a complete graph proposal, not an
                # accepted value. Python constructor validation happens before
                # history, configuration, traits, or document callbacks change.
                from .widget import _projector_from_state
                from uuid import uuid4
                proposal = request["snapshot"]
                graph = deepcopy(proposal["graph"])
                graph.pop("editor_value", None)
                value = _projector_from_state(graph, proposal["port_orders"], proposal["boundary_orders"])
                if any(c.source.node <= c.target.node for c in value.connections):
                    raise ValueError("connections must run right-to-left")
                drawing = {key: proposal.get(key, {}) for key in _PRESENTATION}
                candidate = EditorState.create(value, drawing, term_id=session.state.term_id,
                                               outer_factor=session.state.outer_factor)
                def surviving_ids(raw, known, count):
                    if len(raw) != count or any(i is not None and i not in known for i in raw):
                        raise ValueError("draft references unknown survivor IDs")
                    result = tuple(i or uuid4().hex for i in raw)
                    if len(set(result)) != len(result):
                        raise ValueError("duplicate survivor IDs")
                    return result
                # Constructor sorts connections: carry IDs by concrete ports.
                from .editor_rewrites import edges
                from .projector import NodePort
                raw_edges = (
                    *(("connection", NodePort(**c["source"]), NodePort(**c["target"])) for c in graph["connections"]),
                    *(("input", c["boundary_label"], NodePort(**c["port"])) for c in graph["external_inputs"]),
                    *(("output", c["boundary_label"], NodePort(**c["port"])) for c in graph["external_outputs"]),
                )
                raw_ids = surviving_ids(request["strand_ids"], session.state.strand_ids, len(raw_edges))
                strand_map = dict(zip(raw_edges, raw_ids, strict=True))
                candidate = replace(candidate,
                    node_ids=surviving_ids(request["node_ids"], session.state.node_ids, len(value.nodes)),
                    strand_ids=tuple(strand_map[e] for e in edges(value)))
                session._commit(candidate)
            else:
                raise ValueError("unsupported shared editor command")
            publish()
            editor._editor_seen_requests.add(request_id)
            if action == "save":
                saved_revision = max(editor.save_request + 1, editor.saved_revision + 1, save_revision)
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
        del change
        publish()

    def on_leading(change: dict[str, object]) -> None:
        del change
        publish()

    editor.observe(on_request, names="editor_request")
    editor.observe(on_mode, names="mode")
    editor.observe(on_leading, names="term_leading")
    editor._publish_editor = publish
    publish()


def configuration_for_state(state: EditorState, geometry: dict[str, object]) -> ProjectorConfiguration:
    """Render projection for a rewrite descendant, retaining its owned drawing."""
    from .layout import widget_graph

    graph = widget_graph(state.projector, geometry)
    graph["editor_value"] = dict(projector_codec.encode(state.projector))
    graph["coefficient"] = _rational(state.projector.coefficient)
    graph["base_coefficient"] = graph["coefficient"]
    orders = {str(i): {side: list(order) for side, order in sides.items()}
              for i, sides in state.projector.port_orders.items()}
    return ProjectorConfiguration.from_state(state.projector, {
        "graph": graph, "port_orders": orders, **state.presentation,
        "effective_coefficient": _rational(state.projector.coefficient),
        "editor_state": EditorSession(state).payload(),
    })


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
