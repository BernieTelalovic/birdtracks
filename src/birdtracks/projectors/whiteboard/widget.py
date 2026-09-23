"""Standalone whiteboard document widget and persistence entry point."""

from __future__ import annotations

from copy import deepcopy
from difflib import SequenceMatcher
from fractions import Fraction
import json
import logging
import os
import re
import subprocess
import sys
import traceback
from os import PathLike
from pathlib import Path
from tempfile import TemporaryDirectory

from ..projector import Projector
from ..projector_sum import ProjectorSum
from .diagram_backend import diagram_backend
from .diagram_codec import diagram_codec
from .calculation import (
    BackendTerm,
    calculate_projector_blocks,
    dimension_polynomial_source,
    evaluate_projector_expression,
    simplify_projector_value,
    SymbolicProjectorSum,
)
from .engine import EvaluationEnvironment
from .pair_calculation import (
    _PAIR_MARKER,
    evaluate_pair_blocks,
    pair_definitions,
    pair_definitions_before,
    pair_expression_with_prefactor,
    pair_expression_with_updated_prefactor,
    pair_source_uses_definitions,
)
from .projector_backend import projector_backend
from .projector_codec import projector_codec
from .sidecar import (
    TypedWhiteboardSidecar,
    WhiteboardSidecar,
    WhiteboardStores,
    resolve_sidecar_path,
    write_typed_sidecar,
)
from ...linear_combinations import DimensionPolynomial
from ...symbolic import SymbolicCoefficient


def _open_text_file(path: Path) -> None:
    """Open a text file with the operating system's associated application."""

    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
        return
    command = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen(
        [command, str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


_PROJECTOR_MARKER = re.compile(r"\\birdtracks\b")
_LOGGER = logging.getLogger(__name__)


def _latex_export_path(path: Path) -> Path:
    """Return the neighbouring TeX filename for a whiteboard sidecar."""

    name = path.name
    for suffix in (".whiteboard.json", ".whiteboard"):
        if name.endswith(suffix):
            return path.with_name(name[: -len(suffix)] + ".tex")
    return path.with_suffix(".tex")


def _next_untitled_path(directory: Path | None = None) -> Path:
    """Return the first available default path for an explicitly saved board."""

    number = 1
    while True:
        candidate = (
            directory / f"Untitled_{number}.whiteboard"
            if directory is not None
            else resolve_sidecar_path(f"Untitled_{number}")
        )
        if not candidate.exists():
            return candidate
        number += 1


def _title_path(title: str, directory: Path | None = None) -> Path:
    """Resolve a title, keeping bare names beside their source document."""

    resolved = resolve_sidecar_path(title)
    if directory is not None and Path(title).parent == Path("."):
        return directory / resolved.name
    return resolved


def _expanded_line_colors(
    parent: Projector,
    child: Projector,
    colors: dict[str, object],
    expanded_node: int,
) -> dict[str, object]:
    """Follow visible edges from their surviving endpoint after expansion.

    S/A endpoints stop a colored line; hidden permutation nodes do not.
    Boundary labels and surviving operator ports anchor the correspondence.
    """
    from ..display_graph import DisplayEndpoint, DisplayStrand, compile_display_graph

    before = compile_display_graph(parent)
    after = compile_display_graph(child)
    old_nodes = [i for column in before.operator_columns for i in column
                 if i != expanded_node]
    new_nodes = [i for column in after.operator_columns for i in column]
    matcher = SequenceMatcher(None, [parent.nodes[i] for i in old_nodes],
                              [child.nodes[i] for i in new_nodes], autojunk=False)
    node_map = {old_nodes[a + offset]: new_nodes[b + offset]
                for a, b, count in matcher.get_matching_blocks()
                for offset in range(count)}

    def endpoint_key(endpoint: DisplayEndpoint, projector: Projector) -> str:
        if endpoint.node is None:
            side = "right" if endpoint.kind == "right_boundary" else "left"
            level = sorted(projector.support).index(endpoint.label)
            return f"{side}-anchor:{level}"
        side = "input" if endpoint.kind == "operator_input" else "output"
        return f"{side}:{endpoint.node}:{endpoint.label}"

    def key(strand: DisplayStrand, projector: Projector) -> str:
        return (f"{endpoint_key(strand.source, projector)}->"
                f"{endpoint_key(strand.target, projector)}")

    def matches(old: DisplayEndpoint, new: DisplayEndpoint) -> bool:
        if old.node is None:
            return old.kind == new.kind and old.label == new.label
        return (old.node in node_map and node_map[old.node] == new.node
                and old.kind == new.kind and old.label == new.label)

    result = {}
    for strand in before.strands:
        color = colors.get(key(strand, parent))
        if not color:
            continue
        anchors = [(side, endpoint) for side, endpoint in
                   (("source", strand.source), ("target", strand.target))
                   if endpoint.node is None or endpoint.node in node_map]
        for descendant in after.strands:
            if anchors and all(matches(endpoint, getattr(descendant, side))
                               for side, endpoint in anchors):
                result[key(descendant, child)] = color
    return result


def _result_source(value: ProjectorSum | SymbolicProjectorSum) -> tuple[str, list[dict[str, object]]]:
    """Typeset exact results through the ordinary whiteboard renderer."""
    from ..layout import _crossing_reduced_port_orders

    source = "= "
    terms: list[dict[str, object]] = []
    if isinstance(value, SymbolicProjectorSum):
        for index, (projector, coefficient) in enumerate(value.terms):
            _, presentation_sign = _crossing_reduced_port_orders(projector)
            displayed = coefficient * projector.coefficient * presentation_sign
            if index:
                source += " + "
            source += displayed.latex_factor()
            if projector.nodes:
                start = len(source)
                source += "R"
                terms.append({"start": start, "end": len(source),
                              "value": projector_codec.encode(projector)})
        return source if value.terms else "= 0", terms
    for index, (projector, coefficient) in enumerate(value.items()):
        term = projector * coefficient
        _, presentation_sign = _crossing_reduced_port_orders(term)
        number = term.coefficient * presentation_sign
        source += "- " if number < 0 else "+ " if index else ""
        magnitude = abs(number)
        if magnitude != 1 or not term.nodes:
            source += (str(magnitude.numerator) if magnitude.denominator == 1
                       else rf"\frac{{{magnitude.numerator}}}{{{magnitude.denominator}}}")
        if term.nodes:
            start = len(source)
            source += "R"
            terms.append({"start": start, "end": len(source),
                          "value": projector_codec.encode(term)})
        source += " "
    return source.rstrip() if value.terms else "= 0", terms


def _projector_color_candidates(
    blocks: list[dict[str, object]],
    explicit: dict[str, object],
) -> list[tuple[Projector, dict[str, object]]]:
    """Collect presentation colors associated with saved projector terms."""

    candidates: list[tuple[Projector, dict[str, object]]] = []
    for block in blocks:
        block_id = str(block.get("id") or "")
        raw_terms = block.get("calculation_terms", [])
        stored = block.get("backend_line_colors", {})
        if isinstance(raw_terms, list) and isinstance(stored, dict):
            for index, item in enumerate(raw_terms):
                if not isinstance(item, dict) or "value" not in item:
                    continue
                colors = stored.get(f"{block_id}:backend:{index}")
                if not isinstance(colors, dict):
                    continue
                try:
                    value = projector_codec.decode(item["value"])
                except (TypeError, ValueError):
                    continue
                if isinstance(value, Projector):
                    candidates.append((value, deepcopy(colors)))

        source = str(block.get("source") or "")
        occurrence = 0
        position = 0
        while True:
            match = _PROJECTOR_MARKER.search(source, position)
            if match is None:
                break
            key = f"{block_id}:projector:{occurrence}"
            editor = explicit.get(key)
            value = getattr(editor, "projector", None)
            colors = getattr(editor, "line_colors", {})
            if isinstance(value, Projector) and isinstance(colors, dict) and colors:
                candidates.append((value, deepcopy(colors)))
            occurrence += 1
            position = match.end()
    return candidates


def _calculation_color_map(
    generated_id: str,
    calculation_terms: list[dict[str, object]],
    candidates: list[tuple[Projector, dict[str, object]]],
) -> dict[str, dict[str, object]]:
    """Assign inherited colors to generated backend term ids."""

    inherited: dict[str, dict[str, object]] = {}
    for index, item in enumerate(calculation_terms):
        if not isinstance(item, dict) or "value" not in item:
            continue
        try:
            value = projector_codec.decode(item["value"])
        except (TypeError, ValueError):
            continue
        if not isinstance(value, Projector):
            continue
        colors: dict[str, object] = {}
        for candidate, candidate_colors in candidates:
            if candidate * value.coefficient == value * candidate.coefficient:
                colors.update(candidate_colors)
        if colors:
            inherited[f"{generated_id}:backend:{index}"] = colors
    return inherited


def _serialize_embedded_projectors(value: object, _owner: object) -> object:
    """Serialize child widgets when they are nested in a list trait."""

    if isinstance(value, (list, tuple)):
        return [_serialize_embedded_projectors(item, _owner) for item in value]
    model_id = getattr(value, "model_id", None)
    if model_id is not None:
        return f"anywidget:{model_id}"
    return value


def whiteboard_section_widget(
    blocks: list[dict[str, object]] | None = None,
    *,
    title: str = "",
    debug: bool = False,
) -> object:
    """Create the live-typeset whiteboard editor and its child canvases."""

    try:
        import anywidget
        import traitlets
    except ImportError as exc:
        raise ImportError(
            "interactive display requires: pip install 'birdtracks[notebook]'"
        ) from exc

    # Keep the optional whiteboard implementation in this package while
    # sharing the project's packaged widget asset directory.
    static = Path(__file__).parent.parent / "static"

    class WhiteboardSectionWidget(anywidget.AnyWidget):
        _esm = static / "whiteboard-widget.js"
        _css = static / "whiteboard-widget.css"

        widget_role = traitlets.Unicode("whiteboard").tag(sync=True)
        blocks = traitlets.List(trait=traitlets.Dict()).tag(sync=True)
        title = traitlets.Unicode().tag(sync=True)
        embedded_projector_ids = traitlets.List(
            trait=traitlets.Unicode()
        ).tag(sync=True)
        embedded_projectors = traitlets.List(
            trait=traitlets.Any()
        ).tag(sync=True, to_json=_serialize_embedded_projectors)
        backend_projector_ids = traitlets.List(
            trait=traitlets.Unicode()
        ).tag(sync=True)
        backend_projectors = traitlets.List(
            trait=traitlets.Any()
        ).tag(sync=True, to_json=_serialize_embedded_projectors)
        embedded_pair_ids = traitlets.List(
            trait=traitlets.Unicode()
        ).tag(sync=True)
        embedded_pairs = traitlets.List(
            trait=traitlets.Any()
        ).tag(sync=True, to_json=_serialize_embedded_projectors)
        simplify_request = traitlets.Dict().tag(sync=True)
        calculation_feedback = traitlets.Dict().tag(sync=True)
        open_error_log_request = traitlets.Dict().tag(sync=True)
        save_request = traitlets.Int().tag(sync=True)
        load_document_request = traitlets.Dict().tag(sync=True)
        export_request = traitlets.Int().tag(sync=True)
        export_content = traitlets.Unicode().tag(sync=True)

        @property
        def latex(self) -> str:
            """Return the current synchronized whiteboard as LaTeX."""

            from .latex import whiteboard_latex

            return whiteboard_latex(self)

        def to_latex(self, *, include_preamble: bool = False) -> str:
            """Export the current whiteboard, optionally as a TeX document."""

            from .latex import whiteboard_latex

            return whiteboard_latex(self, include_preamble=include_preamble)

    initial_blocks = (
        deepcopy(blocks)
        if blocks is not None
        else [{"id": "text-1", "source": ""}]
    )
    widget = WhiteboardSectionWidget(
        blocks=initial_blocks,
        title=title,
        embedded_projector_ids=[],
        embedded_projectors=[],
        backend_projector_ids=[],
        backend_projectors=[],
        embedded_pair_ids=[],
        embedded_pairs=[],
        simplify_request={},
        calculation_feedback={},
        open_error_log_request={},
        save_request=0,
        load_document_request={},
        export_request=0,
        export_content="",
    )
    widget.layout.width = "100%"
    widget.debug = debug
    return widget


def _blank_pair_widget() -> object:
    """Return an embedded Young pair editor for a whiteboard marker."""

    try:
        import anywidget
        import traitlets
    except ImportError as exc:
        raise ImportError(
            "interactive display requires: pip install 'birdtracks[notebook]'"
        ) from exc

    static = Path(__file__).parent.parent / "static"

    class PairWidget(anywidget.AnyWidget):
        _esm = static / "projector-widget.js"
        _css = static / "projector-widget.css"

        widget_role = traitlets.Unicode("pair").tag(sync=True)
        pair_expression = traitlets.Dict().tag(sync=True)
        pair_drawing_state = traitlets.Dict().tag(sync=True)
        pair_cell_styles = traitlets.Dict().tag(sync=True)
        read_only = traitlets.Bool(False).tag(sync=True)

        @traitlets.default("pair_expression")
        def _default_pair_expression(self) -> dict[str, object]:
            from ...young_diagrams import PairExpression

            return PairExpression().state()

        @traitlets.validate("pair_expression")
        def _validate_pair_expression(
            self, proposal: dict[str, object]
        ) -> dict[str, object]:
            from ...young_diagrams import PairExpression

            try:
                return PairExpression.from_state(proposal["value"]).state()
            except ValueError as exc:
                raise traitlets.TraitError(str(exc)) from exc

        @traitlets.observe("pair_expression")
        def _draw_pair(self, change: dict[str, object]) -> None:
            from ...young_diagrams import PairExpression

            expression = PairExpression.from_state(self.pair_expression)
            try:
                drawings = [term.drawing() for term in expression.terms]
            except ImportError:
                drawings = []
            self.pair_drawing_state = {
                "expression": expression.state(),
                "drawings": drawings,
            }

    return PairWidget()


def whiteboard(
    session: str | PathLike[str] | None = None,
    *,
    debug: bool = False,
    default_directory: Path | None = None,
    _loaded_state: (
        tuple[WhiteboardStores, list[dict[str, object]] | None, str] | None
    ) = None,
) -> object:
    """Open a standalone persisted whiteboard document.

    The projector canvas deliberately does not create this widget.  A bare
    session name is stored in the normal ``expressions`` directory with the
    ``.whiteboard`` suffix. Legacy ``.whiteboard.json`` files remain readable.
    """

    resolved = resolve_sidecar_path(session) if session is not None else None
    if session is not None and resolved is not None and not resolved.exists():
        supplied = Path(session)
        if (
            not supplied.name.endswith((".whiteboard", ".whiteboard.json"))
            and supplied.suffix != ".json"
        ):
            legacy = resolved.with_name(resolved.name + ".json")
            if legacy.exists():
                resolved = legacy
    if _loaded_state is not None:
        stores, blocks, stored_title = _loaded_state
    elif resolved is not None and resolved.exists():
        stores, blocks, stored_title = _load_whiteboard_state(resolved)
    else:
        stores = WhiteboardStores(
            projectors=EvaluationEnvironment(projector_backend),
            diagrams=EvaluationEnvironment(diagram_backend),
        )
        blocks = None
        stored_title = ""

    widget = whiteboard_section_widget(
        blocks,
        title=stored_title or _session_title(resolved),
        debug=debug,
    )

    embedded: dict[str, object] = {}
    embedded_pairs: dict[str, object] = {}
    backend_embedded: dict[str, object] = {}
    projector_listeners: dict[str, object] = {}
    projector_color_listeners: dict[str, object] = {}
    pair_listeners: dict[str, object] = {}
    backend_projector_listeners: dict[str, object] = {}
    backend_color_listeners: dict[str, object] = {}
    pair_style_listeners: dict[str, object] = {}

    def append_backend_expansion(
        block_id: str,
        term_index: int,
        expanded: ProjectorSum,
        expanded_node: int,
        expansion_parent: Projector,
        expansion_colors: dict[str, object],
    ) -> None:
        """Append a line after manually expanding one displayed term."""

        blocks = list(widget.blocks)
        selected = next(
            (
                block
                for block in blocks
                if str(block.get("id") or "") == block_id
                and isinstance(block.get("calculation_terms"), list)
            ),
            None,
        )
        if selected is None or term_index < 0:
            return
        raw_terms = selected["calculation_terms"]
        assert isinstance(raw_terms, list)
        decoded_terms: list[Projector] = []
        for item in raw_terms:
            if not isinstance(item, dict) or "value" not in item:
                return
            try:
                value = projector_codec.decode(item["value"])
            except (TypeError, ValueError):
                return
            if not isinstance(value, Projector):
                return
            decoded_terms.append(value)
        if term_index >= len(decoded_terms):
            return

        next_terms: list[Projector | tuple[Projector, Fraction]] = []
        for index, value in enumerate(decoded_terms):
            if index == term_index:
                next_terms.extend(expanded.items())
            else:
                next_terms.append(value)
        stored_value = projector_codec.decode(selected["calculation_value"])
        if isinstance(stored_value, ProjectorSum):
            next_terms.extend((term, coefficient) for term, coefficient in stored_value.items()
                              if not term.nodes)
        next_value = ProjectorSum(next_terms)
        from ..simplification import collect_fully_expanded_permutations

        next_value = collect_fully_expanded_permutations(next_value)

        parent_colors = selected.get("backend_line_colors", {})
        candidates: list[tuple[Projector, dict[str, object]]] = []
        if isinstance(parent_colors, dict):
            for index, value in enumerate(decoded_terms):
                if index == term_index:
                    continue
                colors = parent_colors.get(f"{block_id}:backend:{index}")
                if isinstance(colors, dict) and colors:
                    candidates.append((value, deepcopy(colors)))
            expanded_colors = expansion_colors
            if isinstance(expanded_colors, dict) and expanded_colors:
                candidates.extend(
                    (value, _expanded_line_colors(
                        expansion_parent, value, expanded_colors, expanded_node,
                    ))
                    for value, _coefficient in expanded.items()
                )

        group = str(selected.get("calculation_group") or "")
        group_indexes = [
            index
            for index, block in enumerate(blocks)
            if str(block.get("calculation_group") or "") == group
        ]
        if not group or not group_indexes:
            return
        step = max(
            int(block.get("calculation_step", 0))
            for block in blocks
            if str(block.get("calculation_group") or "") == group
        ) + 1
        display_source, calculation_terms = _result_source(next_value)
        generated_id = f"calculation-{group}-{step}"
        generated_colors = _calculation_color_map(
            generated_id, calculation_terms, candidates,
        )
        generated = {
            "id": generated_id,
            "source": display_source,
            "line_id": generated_id,
            "read_only": True,
            "calculation_group": group,
            "calculation_step": step,
            "calculation_value": projector_codec.encode(next_value),
            "calculation_terms": calculation_terms,
        }
        if generated_colors:
            generated["backend_line_colors"] = generated_colors
        updated = list(blocks)
        updated.insert(max(group_indexes) + 1, generated)
        widget.blocks = updated

    def sync_backend_calculation(
        change: dict[str, object] | None = None,
    ) -> None:
        del change
        nonlocal stores
        explicit = dict(zip(
            widget.embedded_projector_ids,
            widget.embedded_projectors,
            strict=False,
        ))
        pair_assignment_names = {
            match.group("name")
            for block in widget.blocks
            if _PAIR_MARKER.search(str(block.get("source") or ""))
            and (match := re.match(
                r"^\s*(?P<name>\S+?)\s*(?:\\def\b|:=)",
                str(block.get("source") or ""),
            ))
        }
        try:
            pair_assignment_names.update(
                pair_definitions(widget.blocks, explicit, {}).keys()
            )
        except (TypeError, ValueError, LookupError, NotImplementedError):
            pass
        # Stores mirror visible definitions; they are not an append-only
        # symbol cache.  Starting empty removes definitions whose source line
        # was deleted and prevents invisible values from being re-saved.
        initial_definitions: dict[str, object] = {}
        # A simplified definition is represented by a generated equality line
        # in the same calculation group.  Use its exact value when rebuilding
        # the environment so later references see the newest state.
        for block in widget.blocks:
            source = str(block.get("source") or "")
            assignment = re.match(r"^\s*(?P<name>\S+?)\s*(?:\\def\b|:=)", source)
            if not assignment:
                continue
            if assignment.group("name") in pair_assignment_names:
                continue
            group = str(block.get("calculation_group") or block.get("line_id") or "")
            candidates = [
                item for item in widget.blocks
                if group
                and str(item.get("calculation_group") or "") == group
                and "calculation_step" in item
                and "calculation_value" in item
            ]
            if not candidates:
                continue
            latest = max(candidates, key=lambda item: int(item.get("calculation_step", 0)))
            try:
                initial_definitions[assignment.group("name")] = projector_codec.decode(
                    latest["calculation_value"]
                )
            except (KeyError, TypeError, ValueError):
                continue
        projector_blocks = [
            block for block in widget.blocks
            if not (
                (assignment := re.match(
                    r"^\s*(?P<name>\S+?)\s*(?:\\def\b|:=)",
                    str(block.get("source") or ""),
                ))
                and assignment.group("name") in pair_assignment_names
            )
        ]
        stores_projectors, terms = calculate_projector_blocks(
            projector_blocks,
            explicit,
            initial_definitions,
        )
        stored_terms: list[BackendTerm] = []
        for block in widget.blocks:
            block_id = str(block.get("id") or "")
            raw_terms = block.get("calculation_terms", [])
            if not isinstance(raw_terms, list):
                continue
            for item in raw_terms:
                if not isinstance(item, dict) or "value" not in item:
                    continue
                try:
                    value = projector_codec.decode(item["value"])
                except (TypeError, ValueError):
                    continue
                if not isinstance(value, Projector):
                    continue
                stored_terms.append(
                    BackendTerm(
                        block_id,
                        int(item.get("start", 0)),
                        int(item.get("end", 0)),
                        value,
                    )
                )
        terms = (*terms, *stored_terms)
        stores = WhiteboardStores(
            projectors=stores_projectors,
            diagrams=stores.diagrams,
        )

        requested: list[str] = []
        per_block_index: dict[str, int] = {}
        backend_terms: dict[str, list[dict[str, object]]] = {}
        for term in terms:
            index = per_block_index.get(term.block_id, 0)
            per_block_index[term.block_id] = index + 1
            key = f"{term.block_id}:backend:{index}"
            requested.append(key)
            if key not in backend_embedded:
                from ..widget import projector_widget

                editor = projector_widget(
                    term.value,
                    mode="evaluate",
                    embedded=True,
                    debug=debug,
                )
                editor.widget_role = "embedded"
                backend_embedded[key] = editor

                def on_backend_expand(
                    change: dict[str, object],
                    *,
                    block_id=term.block_id,
                    term_index=index,
                    editor=editor,
                ) -> None:
                    request = change.get("new")
                    if not isinstance(request, dict) or not request:
                        return
                    expanded = getattr(editor, "expanded_projector_sum", None)
                    if isinstance(expanded, ProjectorSum):
                        from ..widget import _projector_from_state

                        append_backend_expansion(
                            block_id, term_index, expanded, int(request["node"]),
                            _projector_from_state(
                                editor.graph, editor.port_orders, editor.boundary_orders,
                            ),
                            deepcopy(editor.line_colors),
                        )

                editor.observe(on_backend_expand, names="expand_node_request")
                backend_projector_listeners[key] = on_backend_expand

                def on_backend_line_colors(
                    change: dict[str, object],
                    *,
                    key: str = key,
                    block_id: str = term.block_id,
                ) -> None:
                    colors = change.get("new")
                    if not isinstance(colors, dict):
                        return
                    updated = []
                    changed = False
                    for block in widget.blocks:
                        copy = deepcopy(block)
                        if str(block.get("id") or "") == block_id:
                            stored = copy.setdefault("backend_line_colors", {})
                            if not isinstance(stored, dict):
                                stored = {}
                                copy["backend_line_colors"] = stored
                            stored[key] = deepcopy(colors)
                            changed = copy != block
                        updated.append(copy)
                    if changed:
                        widget.blocks = updated

                backend_color_listeners[key] = on_backend_line_colors
                editor.observe(on_backend_line_colors, names="line_colors")
            source_block = next(
                (block for block in widget.blocks
                 if str(block.get("id") or "") == term.block_id),
                None,
            )
            stored_colors = (
                source_block.get("backend_line_colors", {}).get(key, {})
                if isinstance(source_block, dict)
                and isinstance(source_block.get("backend_line_colors"), dict)
                else {}
            )
            if (
                not stored_colors
                and isinstance(source_block, dict)
                and isinstance(source_block.get("line_colors"), dict)
            ):
                stored_colors = source_block["line_colors"]
            if isinstance(stored_colors, dict):
                backend_embedded[key].line_colors = deepcopy(stored_colors)
            backend_terms.setdefault(term.block_id, []).append({
                "id": key,
                "start": term.start,
                "end": term.end,
                "prefactor_owned": any(
                    block.get("id") == term.block_id and "calculation_step" in block
                    for block in widget.blocks
                ),
            })

        for key in tuple(backend_embedded):
            if key not in requested:
                listener = backend_projector_listeners.pop(key, None)
                if listener is not None:
                    backend_embedded[key].unobserve(
                        listener, names="expand_node_request"
                    )
                color_listener = backend_color_listeners.pop(key, None)
                if color_listener is not None:
                    backend_embedded[key].unobserve(color_listener, names="line_colors")
                del backend_embedded[key]
        widget.backend_projector_ids = requested
        widget.backend_projectors = [backend_embedded[key] for key in requested]

        updated_blocks = []
        for block in widget.blocks:
            copy = deepcopy(block)
            calculated = backend_terms.get(str(block.get("id") or ""), [])
            if calculated:
                copy["backend_terms"] = calculated
            else:
                copy.pop("backend_terms", None)
            updated_blocks.append(copy)
        if updated_blocks != list(widget.blocks):
            widget.blocks = updated_blocks

    def sync_pair_definitions(
        change: dict[str, object] | None = None,
    ) -> None:
        del change
        nonlocal stores
        explicit = dict(zip(
            widget.embedded_pair_ids,
            widget.embedded_pairs,
            strict=False,
        ))
        values = pair_definitions(widget.blocks, explicit, {})
        diagrams = EvaluationEnvironment(diagram_backend)
        for name, value in values.items():
            diagrams.define(name, value)
        stores = WhiteboardStores(
            projectors=stores.projectors,
            diagrams=diagrams,
        )

    def watch_projector(projector_id: str, editor: object) -> None:
        if projector_id in projector_listeners:
            return

        def on_saved(change: dict[str, object]) -> None:
            del change
            snapshot = getattr(editor, "save_snapshot", None)
            if isinstance(snapshot, dict) and snapshot:
                block_id, occurrence = projector_id.split(":projector:", 1)
                updated = []
                for block in widget.blocks:
                    copy = deepcopy(block)
                    if str(block.get("id") or "") == block_id:
                        snapshots = copy.get("projector_snapshots", {})
                        if not isinstance(snapshots, dict):
                            snapshots = {}
                        snapshots[occurrence] = deepcopy(snapshot)
                        copy["projector_snapshots"] = snapshots
                    updated.append(copy)
                if updated != list(widget.blocks):
                    widget.blocks = updated
            sync_backend_calculation()
            if resolved is not None:
                persist()

        projector_listeners[projector_id] = on_saved
        editor.observe(on_saved, names="saved_revision")

        def on_line_colors(change: dict[str, object]) -> None:
            colors = change.get("new")
            if not isinstance(colors, dict):
                return
            block_id = projector_id.split(":projector:", 1)[0]
            updated = []
            changed = False
            for block in widget.blocks:
                copy = deepcopy(block)
                if str(block.get("id") or "") == block_id:
                    copy["line_colors"] = deepcopy(colors)
                    changed = copy != block
                updated.append(copy)
            if changed:
                widget.blocks = updated

        projector_color_listeners[projector_id] = on_line_colors
        editor.observe(on_line_colors, names="line_colors")

    def sync_embedded_projectors(
        change: dict[str, object] | None = None,
    ) -> None:
        del change
        from ..configuration import ProjectorConfiguration
        from ..widget import (
            _blank_creator_widget,
            _projector_from_state,
            projector_widget,
        )

        requested: list[str] = []
        for block in widget.blocks:
            block_id = str(block.get("id", ""))
            source = str(block.get("source", ""))
            occurrence = 0
            position = 0
            while True:
                match = _PROJECTOR_MARKER.search(source, position)
                if match is None:
                    break
                key = f"{block_id}:projector:{occurrence}"
                requested.append(key)
                if key not in embedded:
                    snapshots = block.get("projector_snapshots", {})
                    snapshot = (
                        snapshots.get(str(occurrence))
                        if isinstance(snapshots, dict)
                        else None
                    )
                    mode = "evaluate" if block.get("read_only") else "create"
                    if isinstance(snapshot, dict):
                        projector = _projector_from_state(
                            snapshot["graph"],
                            snapshot["port_orders"],
                            snapshot["boundary_orders"],
                        )
                        editor = projector_widget(
                            projector,
                            configuration=ProjectorConfiguration.from_state(
                                projector, snapshot
                            ),
                            mode=mode,
                            debug=debug,
                            embedded=True,
                        )
                        revision = max(1, int(snapshot.get("revision", 1)))
                        editor.save_request = revision
                        editor.saved_revision = revision
                    else:
                        assignment = re.match(
                            r"^\s*(?P<name>\S+?)\s*(?:\\def\b|:=)", source
                        )
                        stored = None
                        if (
                            assignment is not None
                            and source[assignment.end():].strip() == r"\birdtracks"
                        ):
                            try:
                                stored = stores.projectors.resolve(
                                    assignment.group("name")
                                )
                            except LookupError:
                                pass
                        if isinstance(stored, Projector):
                            editor = projector_widget(
                                stored,
                                mode=mode,
                                debug=debug,
                                embedded=True,
                            )
                            editor.save_request = 1
                            editor.saved_revision = 1
                        else:
                            editor = _blank_creator_widget(
                                debug=debug, embedded=True
                            )
                    editor.widget_role = "embedded"  # type: ignore[attr-defined]
                    embedded[key] = editor
                embedded[key].mode = "evaluate" if block.get("read_only") else "create"
                colors = block.get("line_colors")
                if isinstance(colors, dict):
                    embedded[key].line_colors = deepcopy(colors)
                watch_projector(key, embedded[key])
                occurrence += 1
                position = match.end()

        # Occurrence keys are positional, so a deleted projector can otherwise
        # be reused when a new projector is typed at the same location.
        for key in tuple(embedded):
            if key not in requested:
                listener = projector_listeners.pop(key, None)
                if listener is not None:
                    embedded[key].unobserve(listener, names="saved_revision")
                color_listener = projector_color_listeners.pop(key, None)
                if color_listener is not None:
                    embedded[key].unobserve(color_listener, names="line_colors")
                del embedded[key]
        widget.embedded_projector_ids = requested
        widget.embedded_projectors = [embedded[key] for key in requested]
        sync_backend_calculation()

    def sync_embedded_pairs(
        change: dict[str, object] | None = None,
    ) -> None:
        del change
        from ...young_diagrams import PairExpression

        requested: list[str] = []
        for block in widget.blocks:
            block_id = str(block.get("id", ""))
            source = str(block.get("source", ""))
            occurrence = 0
            position = 0
            while True:
                match = _PAIR_MARKER.search(source, position)
                if match is None:
                    break
                key = f"{block_id}:pair:{occurrence}"
                stored_styles = block.get("pair_cell_styles", {})
                styles: object = {}
                if isinstance(stored_styles, dict):
                    legacy_flat = any(":" in str(name) for name in stored_styles)
                    if legacy_flat and occurrence == 0:
                        styles = stored_styles
                    elif not legacy_flat:
                        styles = stored_styles.get(str(occurrence), {})
                styles = deepcopy(styles) if isinstance(styles, dict) else {}
                requested.append(key)
                if key not in embedded_pairs:
                    editor = _blank_pair_widget()
                    snapshots = block.get("pair_snapshots", {})
                    snapshot = (
                        snapshots.get(str(occurrence))
                        if isinstance(snapshots, dict)
                        else None
                    )
                    if isinstance(snapshot, dict):
                        editor.pair_expression = PairExpression.from_state(
                            snapshot
                        ).state()
                    else:
                        assignment = re.match(
                            r"^\s*(?P<name>\S+?)\s*(?:\\def\b|:=)", source
                        )
                        stored = None
                        if (
                            assignment is not None
                            and source[assignment.end():].strip() == r"\pair"
                        ):
                            try:
                                stored = stores.diagrams.resolve(
                                    assignment.group("name")
                                )
                            except LookupError:
                                pass
                        editor.pair_expression = (
                            stored.state()
                            if isinstance(stored, PairExpression)
                            else pair_expression_with_prefactor(
                                source, match.start()
                            ).state()
                        )
                    editor.pair_cell_styles = styles
                    embedded_pairs[key] = editor
                    listener = (
                        lambda change, key=key: on_pair_changed(key, change)
                    )
                    pair_listeners[key] = listener
                    editor.observe(listener, names="pair_expression")
                    style_listener = (
                        lambda change, key=key: on_pair_styles_changed(key, change)
                    )
                    pair_style_listeners[key] = style_listener
                    editor.observe(style_listener, names="pair_cell_styles")
                else:
                    editor = embedded_pairs[key]
                    if editor.pair_cell_styles != styles:
                        style_listener = pair_style_listeners.get(key)
                        if style_listener is not None:
                            editor.unobserve(style_listener, names="pair_cell_styles")
                        try:
                            editor.pair_cell_styles = styles
                        finally:
                            if style_listener is not None:
                                editor.observe(style_listener, names="pair_cell_styles")
                editor = embedded_pairs[key]
                expression = PairExpression.from_state(editor.pair_expression)
                prefactored = pair_expression_with_updated_prefactor(
                    expression, source, match.start()
                )
                if prefactored != expression:
                    listener = pair_listeners.get(key)
                    if listener is not None:
                        editor.unobserve(listener, names="pair_expression")
                    try:
                        editor.pair_expression = prefactored.state()
                    finally:
                        if listener is not None:
                            editor.observe(listener, names="pair_expression")
                embedded_pairs[key].read_only = bool(block.get("read_only"))
                occurrence += 1
                position = match.end()

        for key in tuple(embedded_pairs):
            if key in requested:
                continue
            listener = pair_listeners.pop(key, None)
            if listener is not None:
                embedded_pairs[key].unobserve(listener, names="pair_expression")
            style_listener = pair_style_listeners.pop(key, None)
            if style_listener is not None:
                embedded_pairs[key].unobserve(style_listener, names="pair_cell_styles")
            del embedded_pairs[key]
        widget.embedded_pair_ids = requested
        widget.embedded_pairs = [embedded_pairs[key] for key in requested]
        sync_pair_definitions()

    def on_pair_changed(key: str, change: dict[str, object]) -> None:
        expression = change.get("new")
        if isinstance(expression, dict):
            block_id, occurrence = key.split(":pair:", 1)
            updated = []
            for block in widget.blocks:
                copy = deepcopy(block)
                if str(block.get("id") or "") == block_id:
                    snapshots = copy.get("pair_snapshots", {})
                    if not isinstance(snapshots, dict):
                        snapshots = {}
                    snapshots[occurrence] = deepcopy(expression)
                    copy["pair_snapshots"] = snapshots
                updated.append(copy)
            if updated != list(widget.blocks):
                widget.blocks = updated
        sync_backend_calculation()
        sync_pair_definitions()
        if resolved is not None:
            persist()

    def on_pair_styles_changed(key: str, change: dict[str, object]) -> None:
        styles = change.get("new")
        if not isinstance(styles, dict):
            return
        block_id = key.split(":pair:", 1)[0]
        occurrence = key.split(":pair:", 1)[1]
        updated = []
        changed = False
        for block in widget.blocks:
            copy = deepcopy(block)
            if str(block.get("id") or "") == block_id:
                stored = copy.get("pair_cell_styles", {})
                if not isinstance(stored, dict):
                    stored = {}
                # Older in-memory documents used the child-local flat map;
                # keep it readable while moving the persisted form to one map
                # per marker occurrence.
                if str(occurrence) not in stored and any(
                    isinstance(value, dict) and ":" in str(name)
                    for name, value in stored.items()
                ):
                    stored = {occurrence: stored}
                stored[occurrence] = deepcopy(styles)
                copy["pair_cell_styles"] = stored
                changed = copy != block
            updated.append(copy)
        if changed:
            widget.blocks = updated
        if resolved is not None:
            persist()

    widget.observe(sync_embedded_projectors, names="blocks")
    widget.observe(sync_embedded_pairs, names="blocks")
    sync_embedded_projectors()
    sync_embedded_pairs()

    def persist(change: dict[str, object] | None = None) -> None:
        nonlocal resolved
        title = str(widget.title).strip()
        if resolved is None:
            if not title:
                if not change or change.get("name") != "save_request":
                    return
                resolved = _next_untitled_path(default_directory)
                title = _session_title(resolved)
                widget.title = title
            else:
                resolved = _title_path(title, default_directory)
            widget.session = resolved
        write_typed_sidecar(
            resolved,
            stores,
            projector_backend=projector_backend,
            projector_codec=projector_codec,
            diagram_backend=diagram_backend,
            diagram_codec=diagram_codec,
            document={"title": title, "blocks": deepcopy(widget.blocks)},
        )

    widget.observe(persist, names="blocks")
    widget.observe(persist, names="title")
    widget.observe(persist, names="save_request")

    def export_latex(change: dict[str, object]) -> None:
        del change
        content = widget.to_latex(include_preamble=True)
        if resolved is not None:
            export_path = _latex_export_path(resolved)
            export_path.parent.mkdir(parents=True, exist_ok=True)
            export_path.write_text(content, encoding="utf-8")
        widget.export_content = content

    widget.observe(export_latex, names="export_request")

    def feedback(
        line_id: str,
        action: str,
        reason: str = "",
        error_log: str = "",
    ) -> None:
        revision = int(widget.calculation_feedback.get("revision", 0)) + 1
        widget.calculation_feedback = {
            "line_id": line_id,
            "action": action,
            "reason": reason,
            "traceback": error_log,
            "revision": revision,
        }

    error_log_directory = TemporaryDirectory(prefix="birdtracks-error-")
    widget._error_log_directory = error_log_directory

    def open_error_log(change: dict[str, object]) -> None:
        request = change.get("new")
        if not isinstance(request, dict):
            return
        current = widget.calculation_feedback
        line_id = request.get("line_id")
        if (
            current.get("action") != "rejected"
            or not isinstance(line_id, str)
            or current.get("line_id") != line_id
        ):
            return
        contents = str(
            current.get("traceback")
            or current.get("reason")
            or "Calculation failed."
        )
        path = Path(error_log_directory.name) / "calculation-error.txt"
        path.write_text(contents, encoding="utf-8")
        try:
            _open_text_file(path)
        except Exception as error:
            error_traceback = traceback.format_exc()
            _LOGGER.warning("could not open calculation error log:\n%s", error_traceback)
            feedback(line_id, "rejected", str(error), error_traceback)

    widget.observe(open_error_log, names="open_error_log_request")

    def handle_simplify_request(change: dict[str, object]) -> None:
        request = change.get("new")
        if not isinstance(request, dict):
            return
        action = request.get("action")
        line_id = request.get("line_id")
        if action not in {"evaluate", "restore"} or not isinstance(line_id, str):
            return
        blocks = list(widget.blocks)
        selected = next(
            (block for block in blocks if str(block.get("id") or "") == line_id),
            None,
        )
        if selected is None:
            return
        if action == "evaluate" and selected.get("calculation_scalar"):
            feedback(line_id, "completed")
            return
        group = str(
            selected.get("calculation_group")
            or selected.get("line_id")
            or selected.get("id")
            or ""
        )
        if action == "restore":
            restored = []
            for block in blocks:
                block_group = str(
                    block.get("calculation_group")
                    or block.get("line_id")
                    or block.get("id")
                    or ""
                )
                if block_group != group:
                    restored.append(block)
                    continue
                if "calculation_step" in block:
                    continue
                copy = deepcopy(block)
                for key in ("read_only", "calculation_group"):
                    copy.pop(key, None)
                restored.append(copy)
            widget.blocks = restored
            return

        group_blocks = [
            block
            for block in blocks
            if str(
                block.get("calculation_group")
                or block.get("line_id")
                or block.get("id")
                or ""
            ) == group
        ]
        explicit_pairs = dict(zip(
            widget.embedded_pair_ids,
            widget.embedded_pairs,
            strict=False,
        ))
        pair_assigned_names = {
            match.group("name")
            for block in blocks
            if (match := re.match(
                r"^\s*(?P<name>\S+?)\s*(?:\\def\b|:=)",
                str(block.get("source") or ""),
            ))
        }
        pair_initial = {
            definition.name: definition.value
            for definition in stores.diagrams.definitions
            if definition.name not in pair_assigned_names
        }
        pair_known = {
            definition.name: definition.value
            for definition in stores.diagrams.definitions
        }
        pair_input_blocks = [
            block for block in group_blocks if "calculation_step" not in block
        ]
        available_pair_definitions = pair_definitions_before(
            blocks,
            explicit_pairs,
            group,
            pair_initial,
        )
        has_pair_expression = any(
            _PAIR_MARKER.search(str(block.get("source") or ""))
            or pair_source_uses_definitions(
                str(block.get("source") or ""),
                {**pair_known, **available_pair_definitions},
            )
            for block in pair_input_blocks
        )
        projector_known = {
            definition.name: definition.value
            for definition in stores.projectors.definitions
            if not isinstance(definition.value, SymbolicCoefficient)
        }
        has_birdtrack_expression = any(
            _PROJECTOR_MARKER.search(str(block.get("source") or ""))
            or pair_source_uses_definitions(
                str(block.get("source") or ""), projector_known
            )
            for block in pair_input_blocks
        )
        if has_pair_expression and has_birdtrack_expression:
            try:
                raise NotImplementedError(
                    "operations mixing pairs and birdtracks are not implemented"
                )
            except NotImplementedError as error:
                error_log = traceback.format_exc()
                _LOGGER.warning(
                    "whiteboard expression %s mixes pairs and birdtracks:\n%s",
                    line_id,
                    error_log,
                )
                feedback(line_id, "rejected", str(error), error_log)
                return
        if has_pair_expression:
            definitions = {
                definition.name: definition.value
                for definition in stores.projectors.definitions
                if isinstance(definition.value, SymbolicCoefficient)
            }
            # A diagram definition is the authoritative meaning of a name in
            # a pair expression.  Stale scalar/projector definitions can
            # coexist in a loaded sidecar and must not replace it.
            definitions.update(available_pair_definitions)
            try:
                latest_pair = max(
                    (
                        block for block in group_blocks
                        if isinstance(block.get("pair_calculation"), dict)
                    ),
                    key=lambda block: int(block.get("calculation_step", 0)),
                    default=None,
                )
                if latest_pair is None:
                    calculation = evaluate_pair_blocks(
                        pair_input_blocks,
                        explicit_pairs,
                        definitions,
                    )
                    line_index = 1
                else:
                    calculation = latest_pair["pair_calculation"]
                    assert isinstance(calculation, dict)
                    line_index = int(calculation["line_index"]) + 1
                lines = calculation["lines"]
                if (
                    latest_pair is None
                    and isinstance(lines, list)
                    and len(lines) == 1
                ):
                    line_index = 0
                if not isinstance(lines, list) or line_index >= len(lines):
                    feedback(line_id, "completed")
                    return
                line = lines[line_index]
                if not isinstance(line, dict):
                    raise ValueError("pair calculation line must be an object")
            except Exception as error:
                error_log = traceback.format_exc()
                _LOGGER.warning(
                    "whiteboard pair expression %s could not be evaluated:\n%s",
                    line_id,
                    error_log,
                )
                feedback(line_id, "rejected", str(error), error_log)
                return

            group_name = group
            updated = []
            for block in blocks:
                copy = deepcopy(block)
                if block in group_blocks and "calculation_step" not in block:
                    copy["read_only"] = True
                    copy["calculation_group"] = group_name
                updated.append(copy)
            step = max(
                (
                    int(block.get("calculation_step", 0))
                    for block in updated
                    if str(block.get("calculation_group") or "") == group_name
                ),
                default=0,
            ) + 1
            calculation_state = {
                "line_index": line_index,
                "lines": calculation["lines"],
                "result": calculation["result"],
            }
            generated_id = f"calculation-{group_name}-{step}"
            generated = {
                "id": generated_id,
                "source": "= ",
                "line_id": generated_id,
                "read_only": True,
                "calculation_group": group_name,
                "calculation_step": step,
                "pair_calculation": calculation_state,
                "calculation_svg": line["svg"],
                "calculation_caption": line.get("caption", ""),
            }
            insert_at = max(
                index for index, block in enumerate(updated)
                if str(block.get("calculation_group") or "") == group_name
            ) + 1
            updated.insert(insert_at, generated)
            widget.blocks = updated
            feedback(line_id, "completed")
            return
        if any(
            re.search(r"(?<!:)=\s*(?![=])", str(block.get("source") or ""))
            for block in group_blocks if "calculation_step" not in block
        ):
            _LOGGER.warning(
                "whiteboard expression %s contains non-sequential simplification",
                line_id,
            )
            feedback(line_id, "rejected", "non-sequential simplification")
            return

        explicit = dict(zip(
            widget.embedded_projector_ids,
            widget.embedded_projectors,
            strict=False,
        ))
        try:
            snapshots = request.get("snapshots", {})
            if isinstance(snapshots, dict):
                for key, snapshot in snapshots.items():
                    if key in explicit and isinstance(snapshot, dict) and snapshot:
                        explicit[key].save_snapshot = snapshot
            if "calculation_value" in selected:
                value = projector_codec.decode(selected["calculation_value"])
            else:
                environment, _terms = calculate_projector_blocks(
                    blocks,
                    explicit,
                    {
                        definition.name: definition.value
                        for definition in stores.projectors.definitions
                    },
                )
                value = evaluate_projector_expression(
                    [block for block in group_blocks if "calculation_step" not in block],
                    explicit, environment
                )
            simplified = (
                value if isinstance(value, (DimensionPolynomial, SymbolicCoefficient))
                else simplify_projector_value(value)
            )
        except Exception as error:
            error_log = traceback.format_exc()
            _LOGGER.warning(
                "whiteboard expression %s could not be evaluated:\n%s",
                line_id,
                error_log,
            )
            feedback(line_id, "rejected", str(error), error_log)
            return

        if isinstance(simplified, (DimensionPolynomial, SymbolicCoefficient)):
            group_indexes = [index for index, block in enumerate(blocks) if block in group_blocks]
            if not group_indexes:
                return
            group_name = group
            updated = []
            for block in blocks:
                copy = deepcopy(block)
                if block in group_blocks and "calculation_step" not in block:
                    copy["read_only"] = True
                    copy["calculation_group"] = group_name
                updated.append(copy)
            step = max(
                int(block.get("calculation_step", 0))
                for block in updated
                if str(block.get("calculation_group") or "") == group_name
            ) + 1
            generated_id = f"calculation-{group_name}-{step}"
            updated.insert(max(group_indexes) + 1, {
                "id": generated_id,
                "source": "= " + (
                    dimension_polynomial_source(simplified)
                    if isinstance(simplified, DimensionPolynomial)
                    else simplified.latex()
                ),
                "line_id": generated_id,
                "read_only": True,
                "calculation_group": group_name,
                "calculation_step": step,
                "calculation_scalar": True,
            })
            widget.blocks = updated
            feedback(line_id, "completed")
            return

        current = (
            value if isinstance(value, (ProjectorSum, SymbolicProjectorSum))
            else ProjectorSum((value,))
        )
        if simplified == current and "calculation_step" in selected:
            return
        group_indexes = [index for index, block in enumerate(blocks) if block in group_blocks]
        if not group_indexes:
            return
        group_name = group
        updated = []
        for block in blocks:
            copy = deepcopy(block)
            if block in group_blocks and "calculation_step" not in block:
                copy["read_only"] = True
                copy["calculation_group"] = group_name
                editor = explicit.get(f"{block.get('id')}:projector:0")
                if editor is not None:
                    copy["line_colors"] = deepcopy(editor.line_colors)
            updated.append(copy)
        last_index = max(group_indexes)
        step = max(
            int(block.get("calculation_step", 0))
            for block in updated
            if str(block.get("calculation_group") or "") == group_name
        ) + 1
        display_source, calculation_terms = _result_source(simplified)
        generated_id = f"calculation-{group_name}-{step}"
        generated_colors = _calculation_color_map(
            generated_id,
            calculation_terms,
            _projector_color_candidates(group_blocks, explicit),
        )
        generated = {
            "id": generated_id,
            "source": display_source,
            "line_id": generated_id,
            "read_only": True,
            "calculation_group": group_name,
            "calculation_step": step,
            "calculation_terms": calculation_terms,
        }
        if isinstance(simplified, ProjectorSum):
            generated["calculation_value"] = projector_codec.encode(simplified)
        if generated_colors:
            generated["backend_line_colors"] = generated_colors
        updated.insert(last_index + 1, generated)
        widget.blocks = updated
        feedback(line_id, "completed")

    widget.observe(handle_simplify_request, names="simplify_request")
    widget.session = resolved
    persist()
    return widget


def whiteboard_workspace(
    session: str | PathLike[str] | None = None,
    *,
    debug: bool = False,
) -> object:
    """Create the standalone tabbed workspace with isolated documents."""

    try:
        import anywidget
        import traitlets
    except ImportError as exc:
        raise ImportError(
            "interactive display requires: pip install 'birdtracks[notebook]'"
        ) from exc

    static = Path(__file__).parent.parent / "static"

    class WhiteboardWorkspaceWidget(anywidget.AnyWidget):
        _esm = static / "whiteboard-widget.js"
        _css = static / "whiteboard-widget.css"

        widget_role = traitlets.Unicode("workspace").tag(sync=True)
        documents = traitlets.List(trait=traitlets.Any()).tag(
            sync=True, to_json=_serialize_embedded_projectors
        )
        active_index = traitlets.Int(0).tag(sync=True)
        new_document_request = traitlets.Int(0).tag(sync=True)
        close_document_request = traitlets.Int(-1).tag(sync=True)
        close_document_revision = traitlets.Int(0).tag(sync=True)

    first_document = whiteboard(session, debug=debug)
    workspace = WhiteboardWorkspaceWidget(
        documents=[first_document],
        active_index=0,
        new_document_request=0,
        close_document_request=-1,
        close_document_revision=0,
    )
    workspace.layout.width = "100%"

    def add_document(change: dict[str, object]) -> None:
        del change
        source = getattr(first_document, "session", None)
        directory = source.parent if source is not None else None
        document = whiteboard(
            debug=debug, default_directory=directory
        )
        document.observe(load_document, names="load_document_request")
        documents = [*workspace.documents, document]
        workspace.documents = documents
        workspace.active_index = len(documents) - 1

    def close_document(change: dict[str, object]) -> None:
        del change
        index = workspace.close_document_request
        documents = list(workspace.documents)
        if not 0 <= index < len(documents):
            return
        del documents[index]
        if not documents:
            document = whiteboard(debug=debug)
            document.observe(load_document, names="load_document_request")
            documents.append(document)
        workspace.documents = documents
        workspace.active_index = min(index, len(documents) - 1)

    def load_document(change: dict[str, object]) -> None:
        request = change.get("new")
        if not isinstance(request, dict):
            return
        content = request.get("content")
        name = request.get("name")
        if not isinstance(content, str) or not isinstance(name, str):
            return
        loaded = _load_whiteboard_content(content)
        stores, blocks, title = loaded
        if not title:
            title = _session_title(Path(name))
        document = whiteboard(
            debug=debug,
            default_directory=Path.cwd(),
            _loaded_state=(stores, blocks, title),
        )
        document.observe(load_document, names="load_document_request")
        documents = [*workspace.documents, document]
        workspace.documents = documents
        workspace.active_index = len(documents) - 1

    first_document.observe(load_document, names="load_document_request")
    workspace.observe(add_document, names="new_document_request")
    workspace.observe(close_document, names="close_document_revision")
    return workspace


def _load_whiteboard_state(
    path: Path,
) -> tuple[WhiteboardStores, list[dict[str, object]] | None, str]:
    """Load the typed format, migrating the earlier projector-only format."""

    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("whiteboard sidecar must contain a JSON object")
    if state.get("version") == 2:
        loaded = TypedWhiteboardSidecar.load(
            path,
            projector_backend=projector_backend,
            projector_codec=projector_codec,
            diagram_backend=diagram_backend,
            diagram_codec=diagram_codec,
        )
        document = loaded.document
        return loaded.stores, _blocks_from_document(document), _title_from_document(document)
    if state.get("version") == 1:
        loaded = WhiteboardSidecar.load(
            path,
            backend=projector_backend,
            codec=projector_codec,
        )
        stores = WhiteboardStores(
            projectors=loaded.environment,
            diagrams=EvaluationEnvironment(diagram_backend),
        )
        document = loaded.document
        return stores, _blocks_from_document(document), _title_from_document(document)
    raise ValueError("unsupported whiteboard sidecar version")


def _load_whiteboard_content(
    content: str,
) -> tuple[WhiteboardStores, list[dict[str, object]] | None, str]:
    """Load uploaded sidecar text through the established file codecs."""

    with TemporaryDirectory(prefix="birdtracks-whiteboard-load-") as temporary:
        path = Path(temporary) / "uploaded.whiteboard"
        path.write_text(content, encoding="utf-8")
        return _load_whiteboard_state(path)


def _blocks_from_document(document: dict[str, object]) -> list[dict[str, object]] | None:
    blocks = document.get("blocks", document.get("whiteboard"))
    if blocks is None:
        return None
    if not isinstance(blocks, list) or any(not isinstance(block, dict) for block in blocks):
        raise ValueError("whiteboard document blocks must be an array of objects")
    return deepcopy(blocks)


def _title_from_document(document: dict[str, object]) -> str:
    title = document.get("title", "")
    return title.strip() if isinstance(title, str) else ""


def _session_title(path: Path | None) -> str:
    if path is None:
        return ""
    if path.name.endswith(".whiteboard.json"):
        return path.name.removesuffix(".whiteboard.json")
    return path.name.removesuffix(".whiteboard")


__all__ = ["whiteboard", "whiteboard_section_widget", "whiteboard_workspace"]
