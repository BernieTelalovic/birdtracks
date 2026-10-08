"""Optional interactive Jupyter canvas for projector diagrams."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from fractions import Fraction
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from .configuration import ProjectorConfiguration
    from .projector import Projector
    from .projector_sum import ProjectorSum


# The whiteboard owns the prefactor. An embedded canvas must start its
# diagram at the left edge so `2\birdtracks` reads like a normal term.
_EMBEDDED_COEFFICIENT_SPACE = 0.0


def _ordered_display_items(
    value: ProjectorSum,
    candidates: list[object],
) -> tuple[tuple[object, object], ...]:
    """Order collected terms by their first position in an algebraic rewrite."""
    remaining = list(value)
    ordered: list[tuple[object, object]] = []
    for candidate in candidates:
        candidate_projector = (
            candidate[0] if isinstance(candidate, tuple) else candidate
        )
        for index, item in enumerate(remaining):
            projector, _coefficient = item
            if projector % candidate_projector:
                ordered.append(item)
                remaining.pop(index)
                break
    ordered.extend(remaining)
    return tuple(ordered)


def projector_sum_widget(
    projector_sum: ProjectorSum,
    *,
    style: str | PathLike[str] | None = None,
    initial_editor: object | None = None,
    mode: str = "evaluate",
    session: str | PathLike[str] | None = None,
    detangler: str | PathLike[str] | object | None = None,
    prompt_for_session: bool = False,
    debug: bool = False,
    shared_editor: bool = True,
    pair_expression: dict[str, object] | None = None,
    create_kind: str = "birdtracks",
    restored_lines: list[
        tuple[ProjectorSum, tuple[object, ...], tuple[int, ...]]
    ]
    | None = None,
    restored_redo_lines: list[dict[str, object]] | None = None,
) -> object:
    """Create the unified projector canvas in create or evaluate mode."""
    if mode not in {"create", "evaluate"}:
        raise ValueError("projector canvas mode must be 'create' or 'evaluate'")
    try:
        import ipywidgets
    except ImportError as exc:
        raise ImportError(
            "interactive display requires: pip install 'birdtracks[notebook]'"
        ) from exc

    from .projector_sum import ProjectorSum
    from .simplification import remove_automatically_vanishing_terms
    shared_editor = shared_editor or bool(
        initial_editor is not None and initial_editor.configuration.state().get("editor_state")
    ) or bool(restored_lines and any(
        editor.configuration.state().get("editor_state")
        for _value, editors, _signs in restored_lines for editor in editors
    ))
    learned_detangler = None
    automatic_detangler = detangler is None
    if detangler is None:
        from .detangle_training import default_detangler_checkpoint

        detangler = default_detangler_checkpoint()
    if detangler is not None and detangler is not False:
        from .detangle_training import LearnedDetangler

        if isinstance(detangler, (str, PathLike)):
            try:
                learned_detangler = LearnedDetangler.load(detangler)
            except (ImportError, ValueError):
                if not automatic_detangler:
                    raise
                # An optional source-tree checkpoint must not prevent the
                # calculator from opening when its training dependency is not
                # installed or its visible-layout schema is stale. Explicit
                # paths still fail loudly.
                learned_detangler = None
        else:
            learned_detangler = detangler
        if learned_detangler is not None and not isinstance(
            learned_detangler, LearnedDetangler
        ):
            raise TypeError(
                "detangler must be a checkpoint path or LearnedDetangler"
            )

    if not isinstance(projector_sum, ProjectorSum):
        raise TypeError("projector canvas expects a ProjectorSum")
    projector_sum = remove_automatically_vanishing_terms(projector_sum)
    if not projector_sum:
        initial_editor = None

    group_id = uuid4().hex
    toolbar = _projector_toolbar_widget(group_id, mode)
    if pair_expression is not None:
        toolbar.pair_expression = pair_expression
    toolbar.create_kind = create_kind
    if initial_editor is not None:
        initial_editor.group_id = group_id
    if restored_lines is not None:
        for _value, editors, _signs in restored_lines:
            for editor in editors:
                editor.group_id = group_id

    class ProjectorCanvas(ipywidgets.VBox):
        _term_editors: tuple[object, ...]
        _term_signs: tuple[int, ...]
        _saved_projector_sum: ProjectorSum
        _history: list[ProjectorSum]

        @property
        def current_pair_expression(self) -> object:
            """Return the synchronized, ordered Young-diagram edit document."""
            from ..young_diagrams import PairExpression

            return PairExpression.from_state(self._toolbar.pair_expression)

        @property
        def projector_sum(self) -> ProjectorSum:
            """Return the value captured by the latest save action."""
            return self._saved_projector_sum

        @property
        def projector(self) -> Projector:
            """Return the sole saved projector in a one-term editor."""
            items = tuple(self._saved_projector_sum)
            if len(items) != 1 or items[0][1] != 1:
                raise ValueError("the current value is not a single unit projector")
            return items[0][0]

        @property
        def current_projector_sum(self) -> ProjectorSum:
            """Return the sum represented by current synchronized canvas state."""
            from .editor_rewrites import expression_value

            return remove_automatically_vanishing_terms(
                expression_value(
                    sign
                    * _projector_from_state(
                        editor.graph,
                        editor.port_orders,
                        editor.boundary_orders,
                    )
                    for sign, editor in zip(
                        self._term_signs, self._term_editors, strict=True
                    )
                )
            )

        def on_save(self, callback: object, remove: bool = False) -> None:
            """Register a callback receiving this canvas after a completed Save."""
            if not callable(callback):
                raise TypeError("save callback must be callable")
            if remove:
                if callback in self._save_callbacks:
                    self._save_callbacks.remove(callback)
            elif callback not in self._save_callbacks:
                self._save_callbacks.append(callback)

    def apply_editor_zoom(editor: object) -> None:
        """Scale the flex item with its SVG so zoom creates no empty gutters."""
        zoom = max(0.5, min(3.0, float(editor.zoom)))
        base_width = getattr(editor, "_canvas_base_width", None)
        rendered_width = float(getattr(editor, "rendered_width", 0.0))
        if rendered_width > 0:
            width = f"{rendered_width:g}rem"
        elif base_width is None:
            width = f"{100 * zoom:g}%"
        else:
            width = f"{base_width * zoom:g}px"
        editor.layout = ipywidgets.Layout(
            flex="0 0 auto",
            width=width,
            min_width="0",
            margin="0",
        )
        equals = getattr(editor, "_canvas_equals", None)
        if equals is not None:
            equals.layout = ipywidgets.Layout(
                flex="0 0 auto",
                width=f"{1.5 * zoom:g}rem",
                height=f"{1.5 * zoom:g}rem",
                margin=f"0 {0.35 * zoom:g}rem",
            )

    save_step = ipywidgets.Button(description="Save")
    session_name = ipywidgets.Text(
        placeholder="equation filename", description="Equation filename:"
    )
    session_name.layout = ipywidgets.Layout(width="24rem")
    confirm_session = ipywidgets.Button(description="Save", button_style="primary")
    cancel_session = ipywidgets.Button(description="Cancel")
    session_prompt = ipywidgets.HBox(
        children=(session_name, confirm_session, cancel_session)
    )
    session_prompt.layout = ipywidgets.Layout(display="none", align_items="center")
    result = ProjectorCanvas(children=(toolbar,))
    result.mode = mode
    result._toolbar = toolbar
    result._rows = []
    result._line_states = []
    result._redo_lines = list(restored_redo_lines or [])
    result._saved_projector_sum = projector_sum
    result._save_step_button = save_step
    result._session_name_prompt = session_prompt
    result._history = [projector_sum]
    result._save_callbacks = []
    result._learned_detangler = learned_detangler
    result._trace_polynomial = None
    result._trace_result_row = None
    result._trace_delimiters = {}
    result._last_error = None
    result.session = None
    guarded_callbacks: dict[tuple[int, int, str], object] = {}

    def canvas_observe(widget: object, callback: object, names: object) -> None:
        if debug:
            widget.observe(callback, names=names)
            return

        def guarded(change: dict[str, object]) -> None:
            try:
                callback(change)
            except Exception as error:
                result._last_error = error

        guarded_callbacks[(id(widget), id(callback), str(names))] = guarded
        widget.observe(guarded, names=names)

    def canvas_unobserve(widget: object, callback: object, names: object) -> None:
        guarded = guarded_callbacks.pop(
            (id(widget), id(callback), str(names)), callback
        )
        widget.unobserve(guarded, names=names)

    def persist() -> None:
        if session is None:
            return
        from .canvas_session import write_canvas_session

        result.session = write_canvas_session(
            session,
            {
                "mode": result.mode,
                "create_kind": toolbar.create_kind,
                "pair_expression": toolbar.pair_expression,
                "lines": [
                    {
                        "terms": [
                            {
                                "sign": sign,
                                "state": _canvas_editor_state(editor),
                            }
                            for editor, sign in zip(editors, signs, strict=True)
                        ]
                    }
                    for _value, _row, editors, signs in result._line_states
                ],
                "redo_lines": [entry if isinstance(entry, dict) else {
                    "terms":[{"sign":sign,"state":_canvas_editor_state(child)}
                             for child, sign in zip(entry[2],entry[3],strict=True)]}
                    for entry in result._redo_lines],
            },
        )

    def current_from(
        editors: tuple[object, ...], signs: tuple[int, ...]
    ) -> ProjectorSum:
        from .editor_rewrites import expression_value

        return remove_automatically_vanishing_terms(
            expression_value(
                sign
                * _projector_from_state(
                    editor.graph, editor.port_orders, editor.boundary_orders
                )
                for sign, editor in zip(signs, editors, strict=True)
            )
        )

    def trace_row(row: object) -> None:
        if id(row) in result._trace_delimiters:
            return
        children = list(row.children)
        prefix: list[object] = []
        if children and "birdtracks-equation-equals-cell" in getattr(
            children[0], "_dom_classes", ()
        ):
            prefix.append(children.pop(0))
        trace_open = ipywidgets.HTML(value=_trace_delimiter_html("open"))
        trace_open.add_class("birdtracks-trace-delimiter")
        trace_open.add_class("birdtracks-trace-open")
        trace_open.layout = ipywidgets.Layout(
            width="2.15rem", flex="0 0 2.15rem", margin="0 -1.55rem 0 0"
        )
        trace_close = ipywidgets.HTML(value=_trace_delimiter_html("close"))
        trace_close.add_class("birdtracks-trace-delimiter")
        trace_close.add_class("birdtracks-trace-close")
        trace_close.layout = ipywidgets.Layout(
            width="0.55rem", flex="0 0 0.55rem", margin="0 0 0 0.35rem"
        )
        row.add_class("birdtracks-traced-row")
        row.children = (*prefix, trace_open, *children, trace_close)
        result._trace_delimiters[id(row)] = (trace_open, trace_close)

    def untrace_row(row: object) -> None:
        delimiters = result._trace_delimiters.pop(id(row), None)
        if delimiters is None:
            return
        trace_open, trace_close = delimiters
        row.children = tuple(
            child for child in row.children if child not in (trace_open, trace_close)
        )
        row.remove_class("birdtracks-traced-row")

    def update_canvas_children() -> None:
        young = toolbar.create_kind == "young"
        for row in result._rows:
            row.layout.display = "none" if young else "flex"
        trailing = (
            (result._trace_result_row,)
            if result._trace_result_row is not None
            else ()
        )
        prompt = (session_prompt,) if prompt_for_session else ()
        result.children = (
            toolbar,
            *result._rows,
            *trailing,
            *prompt,
            save_step,
        )

    def append_row(
        value: ProjectorSum,
        first_editor: object | None = None,
        line_editors: tuple[object, ...] | None = None,
        line_signs: tuple[int, ...] | None = None,
        display_items: tuple[tuple[object, object], ...] | None = None,
        optimize_layout: bool = False,
        compact_permutation_width: bool = False,
    ) -> None:
        for previous_editor in getattr(result, "_term_editors", ()):
            previous_editor.active_line = False
        row_children: list[object] = []
        editors: list[object] = []
        signs: list[int] = []
        equals = None
        if result._rows and value:
            equals = ipywidgets.HTML(
                value=(
                    '<svg class="birdtracks-equation-equals" viewBox="0 0 24 24" '
                    'role="img" aria-label="equals">'
                    '<line x1="4" y1="9" x2="20" y2="9"></line>'
                    '<line x1="4" y1="15" x2="20" y2="15"></line>'
                    "</svg>"
                )
            )
            equals.add_class("birdtracks-equation-equals-cell")
            row_children.append(equals)
        if not value:
            zero = ipywidgets.HTML(
                value='<span class="birdtracks-zero" role="img" aria-label="zero">0</span>'
            )
            zero.add_class("birdtracks-zero-cell")
            row_children.append(zero)
        if display_items is not None:
            items = display_items
        elif line_editors is not None and line_signs is not None:
            items = tuple(
                (
                    _projector_from_state(
                        editor.graph, editor.port_orders, editor.boundary_orders
                    ),
                    sign,
                )
                for editor, sign in zip(
                    line_editors, line_signs, strict=True
                )
            )
        else:
            items = tuple(value)
        for term_index, (projector, coefficient) in enumerate(items):
            term = coefficient * projector
            from .layout import rendering_projector

            term = rendering_projector(term)
            sign = -1 if term.coefficient < 0 else 1
            magnitude = -term if sign < 0 else term
            if line_editors is not None:
                editor = line_editors[term_index]
            elif term_index == 0 and first_editor is not None:
                editor = first_editor
            else:
                configuration = None
                if optimize_layout and learned_detangler is not None:
                    learned = learned_detangler.optimize(magnitude)
                    magnitude = learned.projector
                    configuration = learned.configuration(style)
                editor = projector_widget(
                    magnitude,
                    style=style,
                    configuration=configuration,
                    mode=result.mode,
                    group_id=group_id,
                    debug=debug,
                    shared_editor=False,
                )
            graph = dict(editor.graph)
            graph["term_sign"] = "-" if sign < 0 else "+" if term_index else ""
            graph["term_leading"] = term_index == 0
            editor.graph = graph
            editor.term_sign = graph["term_sign"]
            editor.term_leading = term_index == 0
            editor.active_line = True
            geometry = graph["geometry"]
            base_width = None
            if result.mode != "create":
                display_right = float(geometry["right_boundary"])
                width = max(
                    96.0,
                    40.0 * display_right,
                )
                base_width = width
            editor._canvas_base_width = base_width
            editor._canvas_leading = term_index == 0
            editor._canvas_equals = equals
            editor._canvas_outer_factor = Fraction(line_signs[term_index] if line_signs is not None else sign)
            if editor.projector.nodes and (shared_editor or editor.configuration.state().get("editor_state")):
                from .editor_widget import attach_editor

                attach_editor(editor, Fraction(line_signs[term_index] if line_signs is not None else sign))
                sign = int(editor._editor_session.state.outer_factor)
            apply_editor_zoom(editor)
            row_children.append(editor)
            editors.append(editor)
            signs.append(sign if getattr(editor, "_editor_session", None) is not None
                         else line_signs[term_index] if line_signs is not None else sign)

        editor_tuple = tuple(editors)
        sign_tuple = tuple(signs)
        if any(getattr(editor, "_editor_session", None) is not None for editor in editors):
            value = current_from(editor_tuple, sign_tuple)
            result._history[-1] = value
            result._saved_projector_sum = value
        row = ipywidgets.HBox(children=tuple(row_children))
        row.add_class("birdtracks-equation-row")
        row.layout = ipywidgets.Layout(
            align_items="center",
            justify_content="flex-start",
            flex_flow="row nowrap",
            overflow="visible",
            width="100%",
        )
        result._term_editors = editor_tuple
        result._term_signs = sign_tuple
        result._rows.append(row)
        result._line_states.append((value, row, editor_tuple, sign_tuple))
        if toolbar.trace_enabled:
            trace_row(row)
        update_canvas_children()

        def wire_editor(editor: object) -> None:
            def expand_selection(
                change: dict[str, object],
                editor: object = editor,
            ) -> None:
                request = change["new"]
                if not request:
                    return
                editors = result._term_editors
                signs = result._term_signs
                if (
                    editor.mode != "evaluate"
                    or editor not in editors
                ):
                    return
                if getattr(editor, "_editor_session", None) is not None:
                    return  # Shared local/calculation rewrites publish provenance.
                selected = editors.index(editor)
                result.mode = "evaluate"
                toolbar.mode = "evaluate"
                assert isinstance(request, dict)
                current_terms = [
                    sign
                    * _projector_from_state(
                        item.graph, item.port_orders, item.boundary_orders
                    )
                    for sign, item in zip(signs, editors, strict=True)
                ]
                from .simplification import (
                    collect_fully_expanded_permutations,
                    remove_automatically_vanishing_terms,
                )

                expanded = _expand_from_canvas_request(
                    current_terms[selected], request
                )
                next_terms: list[object] = [
                    *current_terms[:selected],
                    *expanded.items(),
                    *current_terms[selected + 1 :],
                ]
                next_value = remove_automatically_vanishing_terms(
                    ProjectorSum(next_terms)
                )
                next_value = collect_fully_expanded_permutations(next_value)
                result._history.append(next_value)
                append_row(
                    next_value,
                    display_items=_ordered_display_items(
                        next_value, next_terms
                    ),
                    optimize_layout=True,
                    compact_permutation_width="recursive_edge" in request,
                )
                persist()

            canvas_observe(editor, expand_selection, "expand_node_request")

            def insert_shared_rewrite(change, editor=editor):
                rewrite = change["new"]
                if not rewrite or editor not in result._term_editors:
                    return
                session = getattr(editor, "_editor_session", None)
                if (session is None or rewrite["parent_term_id"] != session.state.term_id
                        or rewrite["base_revision"] != session.state.revision):
                    return
                from dataclasses import replace
                from uuid import uuid4
                from .editor import EditorState
                from .editor_widget import configuration_for_state

                descendants = []
                for current in result._term_editors:
                    if current is editor:
                        descendants.extend(EditorState.decode(s) for s in rewrite["states"])
                    else:
                        # Copy occurrences before collection, including manual
                        # layout, exact scalar, selection, and concrete IDs.
                        descendants.append(replace(current._editor_session.state, term_id=uuid4().hex, revision=0))
                if rewrite.get("calculation") == "full":
                    from .editor_rewrites import collect_calculated_occurrences
                    descendants = collect_calculated_occurrences(tuple(descendants))
                value = ProjectorSum(s.projector * s.outer_factor for s in descendants)
                children = tuple(projector_widget(s.projector, style=style,
                    configuration=configuration_for_state(s, editor.graph["geometry"]),
                    group_id=group_id, debug=debug) for s in descendants)
                result._history.append(value)
                result._redo_lines.clear()
                append_row(value, line_editors=children,
                           line_signs=tuple(int(s.outer_factor) for s in descendants),
                           display_items=tuple((s.projector, s.outer_factor) for s in descendants))
                persist()

            # Blank creation acquires these traits on its first valid Save.
            canvas_observe(editor, insert_shared_rewrite, "editor_rewrite")

            def reorder_term(
                change: dict[str, object], editor: object = editor
            ) -> None:
                request = change["new"]
                if not request or not isinstance(request, dict):
                    return
                line_index = next(
                    (
                        index
                        for index, (_value, _row, line_editors, _signs) in enumerate(
                            result._line_states
                        )
                        if editor in line_editors
                    ),
                    None,
                )
                if line_index is None:
                    return
                value, line_row, line_editors, line_signs = result._line_states[
                    line_index
                ]
                source = line_editors.index(editor)
                target = request.get("target")
                if isinstance(target, bool) or not isinstance(target, int):
                    return
                target = max(0, min(target, len(line_editors) - 1))
                if source == target:
                    return

                reordered_editors = list(line_editors)
                reordered_signs = list(line_signs)
                moved_editor = reordered_editors.pop(source)
                moved_sign = reordered_signs.pop(source)
                reordered_editors.insert(target, moved_editor)
                reordered_signs.insert(target, moved_sign)
                new_editors = tuple(reordered_editors)
                new_signs = tuple(reordered_signs)

                children = list(line_row.children)
                term_slots = [
                    index for index, child in enumerate(children) if child in line_editors
                ]
                for slot, term_editor in zip(term_slots, new_editors, strict=True):
                    children[slot] = term_editor
                line_row.children = tuple(children)

                for index, (term_editor, sign) in enumerate(
                    zip(new_editors, new_signs, strict=True)
                ):
                    graph = dict(term_editor.graph)
                    graph["term_sign"] = "-" if sign < 0 else "+" if index else ""
                    graph["term_leading"] = index == 0
                    term_editor.graph = graph
                    term_editor.term_sign = graph["term_sign"]
                    term_editor.term_leading = index == 0
                    term_editor._canvas_leading = index == 0

                result._line_states[line_index] = (
                    value,
                    line_row,
                    new_editors,
                    new_signs,
                )
                if line_editors == result._term_editors:
                    result._term_editors = new_editors
                    result._term_signs = new_signs
                persist()

            canvas_observe(editor, reorder_term, "term_order_request")

            def flip_term_sign(
                change: dict[str, object], editor: object = editor
            ) -> None:
                if not change["new"] or editor not in result._term_editors:
                    return
                signs = list(result._term_signs)
                index = result._term_editors.index(editor)
                signs[index] = -signs[index]
                new_signs = tuple(signs)
                value, row, editors, _old_signs = result._line_states[-1]
                from .editor_widget import bridge_outer_factor

                editor._canvas_outer_factor = Fraction(new_signs[index])
                bridge_outer_factor(editor, Fraction(new_signs[index]))
                new_value = current_from(editors, new_signs)
                result._term_signs = new_signs
                result._line_states[-1] = (
                    new_value,
                    row,
                    editors,
                    new_signs,
                )
                result._history[-1] = new_value
                persist()

            canvas_observe(editor, flip_term_sign, "term_sign_flip_request")

            def delete_term(
                change: dict[str, object], editor: object = editor
            ) -> None:
                if (
                    not change["new"]
                    or result.mode != "create"
                    or editor not in result._term_editors
                ):
                    return
                _value, row, editors, signs = result._line_states[-1]
                index = editors.index(editor)
                remaining_editors = list(editors)
                remaining_signs = list(signs)
                remaining_editors.pop(index)
                remaining_signs.pop(index)
                replacement = None
                if not remaining_editors:
                    replacement = _blank_creator_widget(
                        style=style, group_id=group_id, debug=debug
                    )
                    remaining_editors.append(replacement)
                    remaining_signs.append(1)

                new_editors = tuple(remaining_editors)
                new_signs = tuple(remaining_signs)
                children = list(row.children)
                slot = children.index(editor)
                if replacement is None:
                    children.pop(slot)
                else:
                    children[slot] = replacement
                    result._wire_editor(replacement)
                row.children = tuple(children)
                editor.active_line = False

                for term_index, (term_editor, sign) in enumerate(
                    zip(new_editors, new_signs, strict=True)
                ):
                    graph = dict(term_editor.graph)
                    graph["term_sign"] = (
                        "-" if sign < 0 else "+" if term_index else ""
                    )
                    graph["term_leading"] = term_index == 0
                    term_editor.graph = graph
                    term_editor.term_sign = graph["term_sign"]
                    term_editor.term_leading = term_index == 0
                    term_editor._canvas_leading = term_index == 0
                    apply_editor_zoom(term_editor)

                new_value = current_from(new_editors, new_signs)
                result._term_editors = new_editors
                result._term_signs = new_signs
                result._line_states[-1] = (
                    new_value,
                    row,
                    new_editors,
                    new_signs,
                )
                result._history[-1] = new_value
                persist()

            canvas_observe(editor, delete_term, "term_delete_request")

            def resize_editor(
                change: dict[str, object], editor: object = editor
            ) -> None:
                del change
                apply_editor_zoom(editor)

            canvas_observe(editor, resize_editor, ("zoom", "rendered_width"))

            def undo_equation_line(
                change: dict[str, object],
                editor: object = editor,
            ) -> None:
                known_editors = {
                    known
                    for _value, _row, line_editors, _signs in result._line_states
                    for known in line_editors
                }
                if not change["new"] or editor not in known_editors:
                    return
                if getattr(editor, "_editor_session", None) is not None and editor._editor_session._undo:
                    editor.local_undo_command += 1
                    return
                if len(result._line_states) <= 1:
                    editor.local_undo_command += 1
                    return
                removed_state = result._line_states.pop()
                result._redo_lines.append(removed_state)
                _value, removed_row, removed_editors, _removed_signs = removed_state
                for removed in removed_editors:
                    removed.active_line = False
                result._rows.pop()
                if len(result._history) > 1:
                    result._history.pop()
                _value, _row, previous_editors, previous_signs = (
                    result._line_states[-1]
                )
                for previous in previous_editors:
                    previous.active_line = True
                result._term_editors = previous_editors
                result._term_signs = previous_signs
                for previous in previous_editors:
                    if hasattr(previous, "_publish_editor"):
                        previous._publish_editor()
                result._trace_delimiters.pop(id(removed_row), None)
                update_canvas_children()
                persist()

            canvas_observe(editor, undo_equation_line, "undo_request")

            def document_command(action, editor=editor):
                if editor not in result._term_editors:
                    return
                if action == "undo":
                    undo_equation_line({"new":True})
                elif action == "redo" and result._redo_lines:
                    entry = result._redo_lines.pop()
                    if isinstance(entry, dict):
                        from .configuration import ProjectorConfiguration
                        children, signs = [], []
                        for term in entry["terms"]:
                            snapshot = term["state"]
                            p = _projector_from_state(snapshot["graph"],snapshot["port_orders"],snapshot["boundary_orders"])
                            children.append(projector_widget(p,configuration=ProjectorConfiguration.from_state(p,snapshot),
                                                             style=style,group_id=group_id,debug=debug))
                            signs.append(term["sign"])
                        value = current_from(tuple(children),tuple(signs))
                        result._history.append(value)
                        append_row(value,line_editors=tuple(children),line_signs=tuple(signs))
                    else:
                        for child in result._term_editors:
                            child.active_line = False
                        result._line_states.append(entry)
                        value, row, children, signs = entry
                        result._rows.append(row)
                        result._history.append(value)
                        result._term_editors, result._term_signs = children, signs
                        for child in children:
                            child.active_line = True
                        update_canvas_children()
                    persist()

            editor._editor_document_command = document_command
            editor._editor_document_history = lambda editor=editor: (
                editor in result._term_editors and len(result._line_states) > 1,
                editor in result._term_editors and bool(result._redo_lines))

            def persist_saved_editor(
                change: dict[str, object], editor: object = editor
            ) -> None:
                if not change["new"]:
                    return
                if (change.get("name") == "editor_state" and change.get("old")
                        and change["new"].get("revision") != change["old"].get("revision")):
                    result._redo_lines.clear()
                    editor._publish_editor()
                if editor in result._term_editors:
                    result._saved_projector_sum = current_from(
                        result._term_editors, result._term_signs
                    )
                persist()

            canvas_observe(editor, persist_saved_editor, "saved_revision")
            canvas_observe(editor, persist_saved_editor, "editor_state")
            if hasattr(editor, "editor_state"):
                editor._publish_editor()

        for editor in editor_tuple:
            wire_editor(editor)
        result._wire_editor = wire_editor

    if restored_lines is None:
        append_row(projector_sum, initial_editor)
    else:
        result._history = []
        for value, editors, signs in restored_lines:
            result._history.append(value)
            append_row(value, line_editors=editors, line_signs=signs)
        result._saved_projector_sum = result._history[-1]

    def request_global_undo(change: dict[str, object]) -> None:
        if toolbar.create_kind == "young":
            return
        request = change["new"]
        if not request or not isinstance(request, dict):
            return
        selected_id = request.get("editor_id")
        editors = tuple(
            editor
            for _value, _row, line_editors, _signs in result._line_states
            for editor in line_editors
        )
        selected = next(
            (
                editor
                for editor in editors
                if getattr(editor, "model_id", None) == selected_id
            ),
            result._term_editors[0] if result._term_editors else None,
        )
        if selected is not None:
            selected.undo_request += 1

    canvas_observe(toolbar, request_global_undo, "undo_request")

    def insert_term(change: dict[str, object]) -> None:
        request = change["new"]
        if (
            not request
            or not isinstance(request, dict)
            or result.mode != "create"
            or toolbar.create_kind == "young"
        ):
            return
        requested_sign = request.get("sign")
        if requested_sign not in {-1, 1}:
            return
        selected_id = request.get("editor_id")
        def complete_insertion() -> None:
            _value, row, editors, signs = result._line_states[-1]
            selected = next(
                (
                    index
                    for index, editor in enumerate(editors)
                    if getattr(editor, "model_id", None) == selected_id
                ),
                0,
            )
            new_editor = _blank_creator_widget(
                style=style, group_id=group_id, debug=debug
            )
            new_editors = (*editors[:selected], new_editor, *editors[selected:])
            new_signs = (*signs[:selected], requested_sign, *signs[selected:])
            children = list(row.children)
            children.insert(children.index(editors[selected]), new_editor)
            row.children = tuple(children)
            for index, (term_editor, sign) in enumerate(
                zip(new_editors, new_signs, strict=True)
            ):
                graph = dict(term_editor.graph)
                graph["term_sign"] = "-" if sign < 0 else "+" if index else ""
                graph["term_leading"] = index == 0
                term_editor.graph = graph
                term_editor.term_sign = graph["term_sign"]
                term_editor.term_leading = index == 0
                term_editor._canvas_leading = index == 0
                term_editor._canvas_outer_factor = Fraction(sign)
            result._wire_editor(new_editor)
            result._term_editors = new_editors
            result._term_signs = new_signs
            value = current_from(new_editors, new_signs)
            result._line_states[-1] = (value, row, new_editors, new_signs)
            result._history[-1] = value
            for term_editor in new_editors:
                apply_editor_zoom(term_editor)
            persist()

        pending = {
            editor: int(editor.save_command) + 1
            for editor in result._term_editors
        }

        def finish_saving(change: dict[str, object]) -> None:
            del change
            if any(
                int(editor.saved_revision) < revision
                for editor, revision in pending.items()
            ):
                return
            for editor in pending:
                canvas_unobserve(editor, finish_saving, "saved_revision")
            complete_insertion()

        for editor in pending:
            canvas_observe(editor, finish_saving, "saved_revision")
        for editor, revision in pending.items():
            editor.save_command = revision

    canvas_observe(toolbar, insert_term, "add_term_request")

    def synchronize_canvas_mode(change: dict[str, object]) -> None:
        new_mode = change["new"]
        if new_mode not in {"create", "evaluate"}:
            return
        result.mode = new_mode
        if toolbar.create_kind == "young":
            persist()
            return
        if new_mode == "create":
            toolbar.trace_enabled = False
            for editor in result._term_editors:
                editor.mode = "create"
                apply_editor_zoom(editor)
            return

        old_editors = result._term_editors
        old_signs = result._term_signs
        pending = {
            editor: int(editor.save_command) + 1 for editor in old_editors
        }

        def rebuild_evaluate_row() -> None:
            value, row, line_editors, line_signs = result._line_states[-1]
            if line_editors != old_editors:
                return
            rebuilt: list[object] = []
            for index, (old_editor, sign) in enumerate(
                zip(old_editors, old_signs, strict=True)
            ):
                if getattr(old_editor, "_editor_session", None) is not None:
                    # Mode changes are views of the same accepted occurrence,
                    # not imports that regenerate IDs, routes, or history.
                    old_editor.mode = "evaluate"
                    old_editor.active_line = True
                    rebuilt.append(old_editor)
                    continue
                projector = _projector_from_state(
                    old_editor.graph,
                    old_editor.port_orders,
                    old_editor.boundary_orders,
                )
                editor = projector_widget(
                    projector,
                    positions=old_editor.positions,
                    style=style,
                    mode="evaluate",
                    group_id=group_id,
                    debug=debug,
                    shared_editor=False,
                )
                graph = dict(editor.graph)
                graph["term_sign"] = "-" if sign < 0 else "+" if index else ""
                graph["term_leading"] = index == 0
                editor.graph = graph
                editor.term_sign = graph["term_sign"]
                editor.term_leading = index == 0
                editor.active_line = True
                editor._canvas_base_width = max(
                    96.0, 40.0 * float(graph["geometry"]["right_boundary"])
                )
                editor._canvas_leading = index == 0
                editor._canvas_equals = getattr(old_editor, "_canvas_equals", None)
                if shared_editor:
                    from .editor_widget import attach_editor

                    attach_editor(editor, Fraction(sign))
                result._wire_editor(editor)
                rebuilt.append(editor)

            new_editors = tuple(rebuilt)
            children = list(row.children)
            slots = [
                index for index, child in enumerate(children) if child in old_editors
            ]
            for slot, editor in zip(slots, new_editors, strict=True):
                children[slot] = editor
            row.children = tuple(children)
            for editor in old_editors:
                if editor not in new_editors:
                    editor.active_line = False
            new_value = current_from(new_editors, line_signs)
            result._term_editors = new_editors
            result._term_signs = line_signs
            result._line_states[-1] = (
                new_value,
                row,
                new_editors,
                line_signs,
            )
            result._history[-1] = new_value
            for editor in new_editors:
                apply_editor_zoom(editor)
            persist()

        def finish_rebuild_save(change: dict[str, object]) -> None:
            del change
            if any(
                int(editor.saved_revision) < revision
                for editor, revision in pending.items()
            ):
                return
            for editor in pending:
                canvas_unobserve(editor, finish_rebuild_save, "saved_revision")
            rebuild_evaluate_row()

        if not pending:
            rebuild_evaluate_row()
            return
        for editor in pending:
            canvas_observe(editor, finish_rebuild_save, "saved_revision")
        for editor, revision in pending.items():
            editor.save_command = revision

    canvas_observe(toolbar, synchronize_canvas_mode, "mode")

    def synchronize_create_kind(change: dict[str, object]) -> None:
        if toolbar.create_kind == "young":
            toolbar.trace_enabled = False
        update_canvas_children()
        persist()

    canvas_observe(toolbar, synchronize_create_kind, "create_kind")
    canvas_observe(toolbar, lambda change: persist(), "pair_expression")
    def save_current_step(_button: object) -> None:
        if prompt_for_session and session is None:
            session_prompt.layout.display = "flex"
            session_name.value = ""
            save_step.description = "Choose name…"
            return
        save_step.description = "Saving…"
        if toolbar.create_kind == "young":
            persist()
            save_step.description = "Saved"
            for callback in tuple(result._save_callbacks):
                callback(result)
            return
        pending = {
            editor: int(editor.save_command) + 1
            for editor in result._term_editors
        }
        if not pending:
            result._saved_projector_sum = ProjectorSum()
            save_step.description = "Saved"
            persist()
            for callback in tuple(result._save_callbacks):
                callback(result)
            return

        def finish_save(change: dict[str, object]) -> None:
            if any(
                int(editor.saved_revision) < revision
                for editor, revision in pending.items()
            ):
                return
            for editor in pending:
                canvas_unobserve(editor, finish_save, "saved_revision")
            result._saved_projector_sum = current_from(
                result._term_editors, result._term_signs
            )
            save_step.description = "Saved"
            persist()
            for callback in tuple(result._save_callbacks):
                callback(result)

        for editor in pending:
            canvas_observe(editor, finish_save, "saved_revision")
        for editor, revision in pending.items():
            editor.save_command = revision

    save_step.on_click(save_current_step)

    def confirm_session_name(_button: object) -> None:
        nonlocal session
        name = session_name.value.strip()
        if not name:
            session_name.description = "Name required:"
            return
        if Path(name).name != name or name in {".", ".."}:
            session_name.description = "Filename only:"
            return
        session = name
        session_prompt.layout.display = "none"
        session_name.description = "Equation filename:"
        save_current_step(confirm_session)

    def cancel_session_name(_button: object) -> None:
        session_prompt.layout.display = "none"
        save_step.description = "Save"

    confirm_session.on_click(confirm_session_name)
    cancel_session.on_click(cancel_session_name)

    def toggle_trace_equation(change: dict[str, object]) -> None:
        if change["new"]:
            current = current_from(result._term_editors, result._term_signs)
            polynomial = _trace_scalar_polynomial(current)
            result._trace_polynomial = polynomial

            for row in result._rows:
                trace_row(row)

            equals = ipywidgets.HTML(
                value=(
                    '<svg class="birdtracks-equation-equals" viewBox="0 0 24 24" '
                    'role="img" aria-label="equals">'
                    '<line x1="4" y1="9" x2="20" y2="9"></line>'
                    '<line x1="4" y1="15" x2="20" y2="15"></line>'
                    "</svg>"
                )
            )
            equals.add_class("birdtracks-equation-equals-cell")
            equals.layout = ipywidgets.Layout(
                width="1.875rem", height="1.875rem", flex="0 0 auto"
            )
            formula = ipywidgets.HTML(value=_dimension_polynomial_html(polynomial))
            formula.add_class("birdtracks-trace-polynomial")
            polynomial_row = ipywidgets.HBox(children=(equals, formula))
            polynomial_row.add_class("birdtracks-equation-row")
            polynomial_row.add_class("birdtracks-trace-result-row")
            polynomial_row.layout = ipywidgets.Layout(
                align_items="center",
                justify_content="flex-start",
                flex_flow="row nowrap",
                overflow="visible",
                width="100%",
            )
            result._trace_result_row = polynomial_row
        else:
            for row in result._rows:
                untrace_row(row)
            result._trace_polynomial = None
            result._trace_result_row = None
        update_canvas_children()

    canvas_observe(toolbar, toggle_trace_equation, "trace_enabled")
    result.layout = ipywidgets.Layout(
        width="100%",
    )
    result.add_class("birdtracks-projector-sum")
    result.add_class("birdtracks-calculator-app")
    persist()
    return result


def projector_canvas_from_session(
    saved_session: object,
    *,
    style: str | PathLike[str] | None = None,
    detangler: str | PathLike[str] | object | None = None,
    debug: bool = False,
) -> object:
    """Reconstruct every equation line in a saved projector canvas."""
    from .canvas_session import ProjectorCanvasSession
    from .configuration import ProjectorConfiguration
    from .projector_sum import ProjectorSum

    if not isinstance(saved_session, ProjectorCanvasSession):
        raise TypeError("saved_session must be a ProjectorCanvasSession")
    document = saved_session.state()
    mode = document["mode"]
    group_id = uuid4().hex
    restored: list[tuple[ProjectorSum, tuple[object, ...], tuple[int, ...]]] = []
    for line in document["lines"]:
        if not isinstance(line, dict) or not isinstance(line.get("terms"), list):
            raise ValueError("projector canvas equation line must contain terms")
        projectors: list[object] = []
        editors: list[object] = []
        signs: list[int] = []
        shared_line = all(term.get("state", {}).get("editor_state") for term in line["terms"])
        for term in line["terms"]:
            if not isinstance(term, dict) or term.get("sign") not in {-1, 1}:
                raise ValueError("projector canvas term must have sign -1 or 1")
            state = term.get("state")
            if not isinstance(state, dict):
                raise ValueError("projector canvas term must contain saved state")
            projector = _projector_from_state(
                state["graph"], state["port_orders"], state["boundary_orders"]
            )
            configuration = ProjectorConfiguration.from_state(projector, state)
            editor = projector_widget(
                projector,
                style=style,
                configuration=configuration,
                mode=mode,
                group_id=group_id,
                debug=debug,
            )
            sign = int(term["sign"])
            projectors.append(sign * projector)
            editors.append(editor)
            signs.append(sign)
        value = ProjectorSum(projectors)
        display_items = _ordered_display_items(value, projectors)
        if len(display_items) != len(editors):
            if shared_line:
                # Shared occurrences deliberately survive collection. Never
                # rebuild their widgets from an aggregate during reload.
                restored.append((value, tuple(editors), tuple(signs)))
                continue
            # Older sessions may contain multiple editor panels whose values
            # now share one canonical topology. Rebuild only that equation
            # line from the collected sum rather than replaying stale panels.
            editors = []
            signs = []
            for projector, coefficient in display_items:
                term = coefficient * projector
                sign = -1 if term.coefficient < 0 else 1
                magnitude = -term if sign < 0 else term
                editors.append(
                    projector_widget(
                        magnitude,
                        style=style,
                        mode=mode,
                        group_id=group_id,
                        debug=debug,
                    )
                )
                signs.append(sign)
        restored.append((value, tuple(editors), tuple(signs)))
    return projector_sum_widget(
        restored[0][0],
        style=style,
        mode=mode,
        session=saved_session.path,
        restored_lines=restored,
        restored_redo_lines=document.get("redo_lines", []),
        detangler=detangler,
        debug=debug,
        pair_expression=document.get("pair_expression"),
        create_kind=document.get("create_kind", "birdtracks"),
    )


def projector_widget(
    projector: Projector,
    positions: Mapping[int | str, tuple[float, float] | Mapping[str, float]] | None = None,
    style: str | PathLike[str] | None = None,
    *,
    configuration: ProjectorConfiguration | None = None,
    mode: str = "evaluate",
    group_id: str = "",
    debug: bool = False,
    embedded: bool = False,
    shared_editor: bool = True,
) -> object:
    """Create one projector term within the shared canvas.

    Embedded whiteboard editors reserve only a small internal coefficient slot;
    their prefactor is supplied by the surrounding whiteboard expression.
    """
    if mode not in {"create", "evaluate"}:
        raise ValueError("projector widget mode must be 'create' or 'evaluate'")
    try:
        import anywidget
        import traitlets
    except ImportError as exc:
        raise ImportError(
            "interactive display requires: pip install 'birdtracks[notebook]'"
        ) from exc

    from .layout import _compiled_display_state, validated_positions, widget_graph
    from .style import load_projector_style

    static = Path(__file__).parent / "static"

    class ProjectorWidget(anywidget.AnyWidget):
        _esm = static / "projector-widget.js"
        _css = static / "projector-widget.css"

        graph = traitlets.Dict().tag(sync=True)
        positions = traitlets.Dict().tag(sync=True)
        port_orders = traitlets.Dict().tag(sync=True)
        free_levels = traitlets.Dict().tag(sync=True)
        boundary_orders = traitlets.Dict().tag(sync=True)
        effective_coefficient = traitlets.Dict().tag(sync=True)
        line_colors = traitlets.Dict().tag(sync=True)
        prefactor_owned = traitlets.Bool(False).tag(sync=True)
        mode = traitlets.Unicode("evaluate").tag(sync=True)
        widget_role = traitlets.Unicode("editor").tag(sync=True)
        group_id = traitlets.Unicode().tag(sync=True)
        active_line = traitlets.Bool(True).tag(sync=True)
        term_sign = traitlets.Unicode().tag(sync=True)
        term_leading = traitlets.Bool(True).tag(sync=True)
        term_order_request = traitlets.Dict().tag(sync=True)
        term_sign_flip_request = traitlets.Int(0).tag(sync=True)
        term_delete_request = traitlets.Int(0).tag(sync=True)
        expand_node_request = traitlets.Dict().tag(sync=True)
        save_request = traitlets.Int(0).tag(sync=True)
        # Some widget frontends send their uninitialized snapshot as null.
        # It is a no-op until a complete save snapshot arrives.
        save_snapshot = traitlets.Dict(allow_none=True).tag(sync=True)
        save_command = traitlets.Int(0).tag(sync=True)
        undo_request = traitlets.Int(0).tag(sync=True)
        local_undo_command = traitlets.Int(0).tag(sync=True)
        zoom = traitlets.Float(1.0).tag(sync=True)
        rendered_width = traitlets.Float(0.0).tag(sync=True)
        saved_revision = traitlets.Int(0).tag(sync=True)

        _source_projector: Projector
        _configured_projector: Projector
        _configuration: ProjectorConfiguration
        _expanded_projector_sum: ProjectorSum | None = None

        def notify_change(self, change: dict[str, object]) -> None:
            """Dispatch traits quietly unless canvas debugging is enabled."""
            try:
                super().notify_change(change)
            except Exception as error:
                self._last_error = error
                if debug:
                    raise

        @property
        def projector(self) -> Projector:
            """The committed value (the last saved value while creating)."""
            return self._configured_projector

        @property
        def projector_sum(self) -> ProjectorSum:
            """The last saved projector promoted to a one-term exact sum."""
            from .projector_sum import ProjectorSum

            return ProjectorSum((self._configured_projector,))

        @property
        def configuration(self) -> ProjectorConfiguration:
            """The accepted exact editor snapshot, separate from preview traits."""
            return self._configuration

        @property
        def expanded_projector_sum(self) -> ProjectorSum | None:
            """The most recent exact expansion requested in evaluate mode."""
            return self._expanded_projector_sum

        @traitlets.observe("expand_node_request")
        def _expand_requested_node(self, change: dict[str, object]) -> None:
            request = change["new"]
            if self.mode != "evaluate" or not request:
                return
            assert isinstance(request, dict)
            session = getattr(self, "_editor_session", None)
            if session is not None:
                from .editor_rewrites import calculate_full_expansion
                from .projector_sum import ProjectorSum
                base_revision = request.get("base_revision", session.state.revision)
                session._check_revision(base_revision)
                if request.get("term_id", session.state.term_id) != session.state.term_id:
                    raise ValueError("expansion calculation belongs to another occurrence")
                node_id = request.get("node_id", session.state.node_ids[int(request["node"])])
                if node_id not in session.state.node_ids:
                    raise ValueError("expansion references an unknown operator")
                if "recursive_edge" in request:
                    branches = session.expand(node_id, base_revision=base_revision,
                                              edge=request["recursive_edge"], geometry=self.graph["geometry"])
                else:
                    branches = calculate_full_expansion(session.state, node_id, geometry=self.graph["geometry"])
                self._expanded_editor_states = branches
                self._expanded_projector_sum = ProjectorSum(s.projector*s.outer_factor for s in branches)
                self.editor_rewrite = {"request_id": f"calculation-{request['revision']}",
                                       "base_revision":base_revision,"parent_term_id":session.state.term_id,
                                       **({"calculation":"full"} if "recursive_edge" not in request else {}),
                                       "states":[s.payload() for s in branches]}
                return
            current = session.state.projector if session is not None else _projector_from_state(
                self.graph, self.port_orders, self.boundary_orders
            )
            self._expanded_projector_sum = _expand_from_canvas_request(
                current, request
            )

        @traitlets.observe("save_snapshot")
        def _save_projector(self, change: dict[str, object]) -> None:
            snapshot = change["new"]
            if getattr(self, "_editor_session", None) is not None:
                self._last_error = ValueError("shared editor saves require a revisioned editor command")
                return
            if not snapshot or not hasattr(self, "_source_projector"):
                return
            assert isinstance(snapshot, dict)
            if int(snapshot["revision"]) < self.saved_revision:
                self._last_error = ValueError("stale creation snapshot")
                return
            snapshot_graph = snapshot.get("graph", self.graph)
            assert isinstance(snapshot_graph, dict)
            self._configured_projector = _projector_from_state(
                snapshot_graph,
                snapshot["port_orders"],
                snapshot["boundary_orders"],
            )
            configuration_graph = snapshot_graph
            if snapshot_graph.get("created"):
                from .layout import widget_graph

                configuration_graph = widget_graph(
                    self._configured_projector, snapshot_graph["geometry"]
                )
            self._configuration = _configuration_from_state(
                self._configured_projector,
                configuration_graph,
                snapshot,
            )
            # The create-to-evaluate bridge must start from this complete,
            # accepted snapshot, not traits from before the creation save.
            with self.hold_trait_notifications():
                self.graph = configuration_graph
                for field in ("positions", "port_orders", "free_levels", "boundary_orders", "effective_coefficient"):
                    setattr(self, field, deepcopy(snapshot[field]))
            snapshot_colors = snapshot.get("line_colors")
            if isinstance(snapshot_colors, dict):
                self.line_colors = deepcopy(snapshot_colors)
            if getattr(self, "_shared_editor_enabled", False) and self.projector.nodes:
                from .editor_widget import attach_editor

                if hasattr(self, "_whiteboard_source_value"):
                    self._whiteboard_source_value = self.projector
                attach_editor(self, getattr(self, "_canvas_outer_factor", Fraction(1)))
            self.saved_revision = int(snapshot["revision"])

    configured_style = load_projector_style(style)
    if embedded:
        configured_style["coefficient_space"] = _EMBEDDED_COEFFICIENT_SPACE
    saved_state = configuration.state() if configuration is not None else None
    if saved_state is None:
        graph = widget_graph(projector, configured_style)
    else:
        # ``display`` is a disposable routing cache. Older frontend saves
        # retained it after topology edits, so trusting it on replay could
        # route a strand to a stale operator port and visibly disconnect it.
        graph = deepcopy(saved_state["graph"])
        geometry = deepcopy(graph["geometry"])
        graph["display"] = _compiled_display_state(projector, geometry)
        graph["geometry"] = geometry
    initial_positions = (
        saved_state["positions"]
        if saved_state is not None
        else validated_positions(projector, positions or {}, configured_style)
    )
    initial_port_orders = (
        saved_state["port_orders"]
        if saved_state is not None
        else {
            str(node["index"]): {
                "input": node["input_labels"],
                "output": node["output_labels"],
            }
            for node in graph["nodes"]
        }
    )
    initial_free_levels = (
        saved_state["free_levels"]
        if saved_state is not None
        else graph["free_levels"]
    )
    initial_boundary_orders = (
        saved_state["boundary_orders"]
        if saved_state is not None
        else {
            "input": list(graph["boundary_labels"]),
            "output": list(graph["boundary_labels"]),
        }
    )
    initial_coefficient = (
        saved_state["effective_coefficient"]
        if saved_state is not None
        else graph["coefficient"]
    )
    editor = ProjectorWidget(
        graph=graph,
        positions=initial_positions,
        port_orders=initial_port_orders,
        free_levels=initial_free_levels,
        boundary_orders=initial_boundary_orders,
        effective_coefficient=initial_coefficient,
        line_colors=(
            saved_state.get("line_colors", {})
            if saved_state is not None
            else {}
        ),
        mode=mode,
        group_id=group_id,
        term_sign=str(graph.get("term_sign", "")),
        term_leading=bool(graph.get("term_leading", True)),
    )
    editor._source_projector = projector
    editor._initial_automatic_positions = (
        deepcopy(saved_state.get("automatic_positions", {})) if saved_state is not None else
        {i: deepcopy(position) for i, position in initial_positions.items()
         if i not in {str(index) for index in positions or {}}}
    )
    if saved_state is not None and saved_state.get("source_value"):
        from .whiteboard.projector_codec import projector_codec

        editor._whiteboard_source_value = projector_codec.decode(saved_state["source_value"])
    editor._last_error = None
    editor._shared_editor_enabled = shared_editor
    editor._configured_projector = projector
    editor._configuration = (
        configuration
        if configuration is not None
        else _configuration_from_widget(editor)
    )
    if shared_editor:
        from .editor_widget import attach_editor

        def attach_on_evaluate(change=None):
            if editor.mode == "evaluate" or editor.projector.nodes and not editor.graph.get("creator"):
                attach_editor(editor)

        editor.observe(attach_on_evaluate, names="mode")
        attach_on_evaluate()
    return editor


def _projector_toolbar_widget(group_id: str, mode: str) -> object:
    """Create the one shared browser-side toolbar for a projector sum."""
    try:
        import anywidget
        import traitlets
    except ImportError as exc:
        raise ImportError(
            "interactive display requires: pip install 'birdtracks[notebook]'"
        ) from exc

    static = Path(__file__).parent / "static"

    class ProjectorToolbarWidget(anywidget.AnyWidget):
        _esm = static / "projector-widget.js"
        _css = static / "projector-widget.css"

        widget_role = traitlets.Unicode("toolbar").tag(sync=True)
        group_id = traitlets.Unicode().tag(sync=True)
        mode = traitlets.Unicode("evaluate").tag(sync=True)
        trace_enabled = traitlets.Bool(False).tag(sync=True)
        add_term_request = traitlets.Dict().tag(sync=True)
        undo_request = traitlets.Dict().tag(sync=True)
        create_kind = traitlets.Enum(["birdtracks", "young"], default_value="birdtracks").tag(sync=True)
        pair_expression = traitlets.Dict().tag(sync=True)
        pair_drawing_state = traitlets.Dict().tag(sync=True)
        pair_evaluation = traitlets.Dict().tag(sync=True)

        @traitlets.default("pair_expression")
        def _default_pair_expression(self) -> dict[str, object]:
            from ..young_diagrams import PairExpression

            return PairExpression().state()

        @traitlets.validate("pair_expression")
        def _validate_pair_expression(self, proposal: dict[str, object]) -> dict[str, object]:
            from ..young_diagrams import PairExpression

            try:
                return PairExpression.from_state(proposal["value"]).state()
            except ValueError as exc:
                raise traitlets.TraitError(str(exc)) from exc

        @traitlets.observe("mode", "create_kind", "pair_expression")
        def _evaluate_pairs(self, change: dict[str, object]) -> None:
            if self.create_kind != "young" or self.mode != "evaluate":
                self.pair_evaluation = {}
                return
            from ..young_diagrams import PairExpression
            from ..pair_evaluation import evaluate

            try:
                result = evaluate(PairExpression.from_state(self.pair_expression))
            except (ValueError, ImportError) as exc:
                result = {"lines": [], "error": str(exc)}
            self.pair_evaluation = result

        @traitlets.observe("pair_expression", "create_kind")
        def _draw_pairs(self, change: dict[str, object]) -> None:
            if self.create_kind != "young":
                return
            from ..young_diagrams import PairExpression

            expression = PairExpression.from_state(self.pair_expression)
            try:
                drawings = [term.drawing() for term in expression.terms]
            except ImportError:
                # Creation remains available without the optional algebra package.
                drawings = []
            self.pair_drawing_state = {"expression": expression.state(), "drawings": drawings}

    toolbar = ProjectorToolbarWidget(group_id=group_id, mode=mode)
    toolbar.layout.width = "100%"
    return toolbar


def _trace_scalar_polynomial(value: ProjectorSum) -> object:
    """Return the exact dimension polynomial obtained by closing ``value``."""
    from birdtracks.linear_combinations import (
        DimensionPolynomial,
        PermutationSum,
        PolynomialPermutationSum,
    )

    collapsed = value.trace().collapse()
    if isinstance(collapsed, PolynomialPermutationSum):
        terms = tuple(collapsed)
        if any(permutation for permutation, _coefficient in terms):
            raise AssertionError("a fully traced projector must collapse to a scalar")
        return sum(
            (coefficient for _permutation, coefficient in terms),
            DimensionPolynomial(),
        )
    if isinstance(collapsed, PermutationSum):
        terms = tuple(collapsed)
        if any(permutation for permutation, _coefficient in terms):
            raise AssertionError("a fully traced projector must collapse to a scalar")
        return DimensionPolynomial(
            {0: sum((coefficient for _permutation, coefficient in terms), 0)}
        )
    raise AssertionError("trace collapse returned an unsupported algebraic value")


def _dimension_polynomial_html(polynomial: object) -> str:
    """Typeset an exact dimension polynomial without a MathJax dependency."""
    terms = tuple(polynomial)
    if not terms:
        return '<span class="birdtracks-polynomial">0</span>'
    parts: list[str] = []
    for power, coefficient in reversed(terms):
        magnitude = abs(coefficient)
        if parts:
            parts.append(" − " if coefficient < 0 else " + ")
        elif coefficient < 0:
            parts.append("−")
        variable = "" if power == 0 else "N"
        if power > 1:
            variable += f"<sup>{power}</sup>"
        if magnitude == 1 and variable:
            scalar = ""
        elif magnitude.denominator == 1:
            scalar = str(magnitude.numerator)
        else:
            scalar = (
                '<span class="birdtracks-polynomial-fraction">'
                f'<span>{magnitude.numerator}</span>'
                f'<span>{magnitude.denominator}</span></span>'
            )
        parts.append(scalar + variable)
    return '<span class="birdtracks-polynomial">' + "".join(parts) + "</span>"


def _trace_delimiter_html(side: str) -> str:
    """Return a trace delimiter whose bracket stretches without enlarging text."""
    if side not in {"open", "close"}:
        raise ValueError("trace delimiter side must be 'open' or 'close'")
    path = (
        "M10 2 C4 16 4 84 10 98"
        if side == "open"
        else "M2 2 C8 16 8 84 2 98"
    )
    symbol = '<span class="birdtracks-trace-symbol">tr</span>' if side == "open" else ""
    return (
        '<span class="birdtracks-trace-notation">'
        + symbol
        + '<svg class="birdtracks-trace-bracket" viewBox="0 0 12 100" '
        + 'preserveAspectRatio="none" aria-hidden="true">'
        + f'<path d="{path}"></path></svg></span>'
    )


def projector_creator(
    *,
    style: str | PathLike[str] | None = None,
    session: str | PathLike[str] | None = None,
    detangler: str | PathLike[str] | object | None = None,
    prompt_for_session: bool = False,
    debug: bool = False,
) -> object:
    """Create a blank one-term projector canvas in create mode."""
    from .projector import Projector
    from .projector_sum import ProjectorSum

    editor = _blank_creator_widget(style=style, debug=debug)
    return projector_sum_widget(
        ProjectorSum((Projector([]),)),
        style=style,
        initial_editor=editor,
        mode="create",
        session=session,
        detangler=detangler,
        prompt_for_session=prompt_for_session,
        debug=debug,
    )


def _blank_creator_widget(
    *,
    style: str | PathLike[str] | None = None,
    group_id: str = "",
    debug: bool = False,
    embedded: bool = False,
) -> object:
    """Return a genuinely empty editable term, not an identity strand."""
    from .projector import Projector

    editor = projector_widget(
        Projector([]),
        style=style,
        mode="create",
        group_id=group_id,
        debug=debug,
        embedded=embedded,
    )
    graph = dict(editor.graph)
    graph.update(
        creator=True,
        nodes=[],
        connections=[],
        external_inputs=[],
        external_outputs=[],
        boundary_labels=[],
        free_levels={},
        layer_count=0,
    )
    editor.graph = graph
    editor.positions = {}
    editor.port_orders = {}
    editor.free_levels = {}
    editor.boundary_orders = {"input": [], "output": []}
    return editor


def _canvas_editor_state(editor: object) -> dict[str, object]:
    """Copy the complete synchronized state of one canvas term."""
    from .editor_widget import shared_snapshot

    snapshot = shared_snapshot(editor)
    if snapshot is not None:
        return snapshot
    return deepcopy(
        {
            "graph": editor.graph,
            "positions": editor.positions,
            "port_orders": editor.port_orders,
            "free_levels": editor.free_levels,
            "boundary_orders": editor.boundary_orders,
            "line_colors": editor.line_colors,
            "effective_coefficient": editor.effective_coefficient,
        }
    )


def _configuration_from_widget(editor: object) -> ProjectorConfiguration:
    return _configuration_from_state(
        editor._configured_projector,
        editor.graph,
        {
            "positions": editor.positions,
            "port_orders": editor.port_orders,
            "free_levels": editor.free_levels,
            "boundary_orders": editor.boundary_orders,
            "line_colors": editor.line_colors,
            "effective_coefficient": editor.effective_coefficient,
        },
    )


def _configuration_from_state(
    projector: Projector,
    graph: object,
    snapshot: Mapping[str, object],
) -> ProjectorConfiguration:
    from .configuration import ProjectorConfiguration

    return ProjectorConfiguration.from_state(
        projector,
        {
            "graph": graph,
            "positions": snapshot["positions"],
            "port_orders": snapshot["port_orders"],
            "free_levels": snapshot["free_levels"],
            "boundary_orders": snapshot["boundary_orders"],
            "line_colors": snapshot.get("line_colors", {}),
            "effective_coefficient": snapshot["effective_coefficient"],
        },
    )


def _projector_from_state(
    graph: Mapping[str, object],
    port_orders: Mapping[str, Mapping[str, list[int]]],
    boundary_orders: Mapping[str, list[int]],
) -> Projector:
    """Build an immutable algebraic snapshot of synchronized editor state."""
    if "editor_value" in graph:
        from .whiteboard.projector_codec import projector_codec
        from .projector import Projector

        value = projector_codec.decode(graph["editor_value"])
        if not isinstance(value, Projector):
            raise ValueError("shared canvas state requires an exact Projector")
        return value
    from .projector import Connection, NodePort, Projector
    from .symmetrisers import Antisymmetriser, Symmetriser
    nodes = graph["nodes"]
    assert isinstance(nodes, list)
    complete_port_orders = {
        str(int(node_data["index"])): {
            "input": list(
                port_orders.get(str(int(node_data["index"])), {}).get(
                    "input", node_data["input_labels"]
                )
            ),
            "output": list(
                port_orders.get(str(int(node_data["index"])), {}).get(
                    "output", node_data["output_labels"]
                )
            ),
        }
        for node_data in nodes
    }
    labels = list(graph["boundary_labels"])
    input_boundary = _boundary_from_order(
        labels, boundary_orders["input"], graph["external_inputs"], NodePort
    )
    output_boundary = _boundary_from_order(
        labels, boundary_orders["output"], graph["external_outputs"], NodePort
    )
    projector_nodes = tuple(_node_from_data(item) for item in nodes)
    serialized_connections = graph["connections"]
    assert isinstance(serialized_connections, list)
    connections = tuple(
        Connection(
            NodePort(int(item["source"]["node"]), int(item["source"]["label"])),
            NodePort(int(item["target"]["node"]), int(item["target"]["label"])),
        )
        for item in serialized_connections
    )
    baseline = Projector(
        projector_nodes,
        connections,
        coefficient=_graph_coefficient(graph),
        input_boundary=input_boundary,
        output_boundary=output_boundary,
        in_direction=graph.get("in_direction", "neutral"),
        out_direction=graph.get("out_direction", "neutral"),
        port_orders={
            int(index): {
                "input": tuple(orders["input"]),
                "output": tuple(orders["output"]),
            }
            for index, orders in {
                str(node["index"]): {"input": node["input_labels"], "output": node["output_labels"]}
                for node in nodes
            }.items()
        },
    )
    from .editor import project_port_orders

    return project_port_orders(baseline, {
        int(index): sides for index, sides in complete_port_orders.items()
        if isinstance(projector_nodes[int(index)], (Symmetriser, Antisymmetriser))
    })


def _expand_from_canvas_request(
    projector: Projector, request: Mapping[str, object]
) -> ProjectorSum:
    """Apply either a full expansion or an edge-selected recursion."""
    from .simplification import (
        expand_node,
        recursive_expand_node,
    )

    node_index = int(request["node"])
    edge = request.get("recursive_edge")
    if edge is None:
        return expand_node(projector, node_index)
    if edge not in {"top", "bottom"}:
        raise ValueError("recursive_edge must be 'top' or 'bottom'")

    return recursive_expand_node(
        projector, node_index, side="input", edge=edge
    )


def _node_from_data(item: Mapping[str, object]) -> object:
    from birdtracks.permutations import Permutation

    from .permutation_node import PermutationNode
    from .symmetrisers import Antisymmetriser, Symmetriser

    kind = item["kind"]
    if kind == "permutation":
        mapping = item.get("mapping")
        if not isinstance(mapping, list):
            raise ValueError("saved permutation node requires a mapping")
        return PermutationNode(
            Permutation(tuple(tuple(pair) for pair in mapping)),
            support=item["labels"],
            in_direction=item.get("in_direction", "neutral"),
            out_direction=item.get("out_direction", "neutral"),
        )
    node_type = Antisymmetriser if kind == "antisymmetriser" else Symmetriser
    return node_type(item["labels"])


def _graph_coefficient(graph: Mapping[str, object]) -> Fraction:
    from fractions import Fraction

    coefficient = graph["coefficient"]
    assert isinstance(coefficient, dict)
    return Fraction(int(coefficient["numerator"]), int(coefficient["denominator"]))


def _boundary_from_order(
    fixed_labels: list[int],
    order: list[int],
    serialized: object,
    port_type: type,
) -> dict[int, object]:
    if sorted(order) != sorted(fixed_labels):
        raise ValueError("saved boundary order must permute every boundary label")
    assert isinstance(serialized, list)
    ports = {
        int(item["boundary_label"]): port_type(
            int(item["port"]["node"]), int(item["port"]["label"])
        )
        for item in serialized
    }
    return {
        fixed_label: ports[moved_label]
        for fixed_label, moved_label in zip(fixed_labels, order)
    }


__all__ = [
    "projector_canvas_from_session",
    "projector_sum_widget",
    "projector_widget",
]
