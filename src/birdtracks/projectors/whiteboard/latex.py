"""Deterministic LaTeX export for the live whiteboard presentation state.

This module intentionally consumes widget state rather than algebra objects.
It translates saved projector topology and Young-pair content into the public
``birdtracks.sty`` syntax, and is also usable with a plain mapping so that the
exporter remains independent of the optional anywidget dependency.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import math
import re
from xml.etree import ElementTree


_PROJECTOR_MARKER = re.compile(r"\\birdtracks\b")
_PAIR_MARKER = re.compile(r"\\pair\b(?!\s*\{)")
_PREFACTOR = re.compile(
    r"[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:_\d+)?"
    r"(?:\s*/\s*\d+(?:[.,]\d*)?)?$"
)
_FRAC_PREFactor = re.compile(r"[+-]?\\frac\s*\{\s*\d+\s*\}\s*\{\s*\d+\s*\}$")


def _get(value: object, key: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _number(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _fmt(value: float) -> str:
    if not math.isfinite(value):
        return "0"
    return f"{value:.6g}"


def _tex_text(value: object) -> str:
    """Escape ordinary cell labels while leaving the source document raw."""

    text = str(value)
    return (text.replace("\\", r"\textbackslash{}")
            .replace("{", r"\{")
            .replace("}", r"\}")
            .replace("#", r"\#")
            .replace("%", r"\%")
            .replace("&", r"\&")
            .replace("_", r"\_")
            .replace("^", r"\textasciicircum{}"))


def _prefactor_before(source: str, marker_start: int) -> tuple[int, str] | None:
    end = marker_start
    while end > 0 and source[end - 1].isspace():
        end -= 1
    prefix = source[:end]
    match = _PREFACTOR.search(prefix) or _FRAC_PREFactor.search(prefix)
    if match is None:
        return None
    start = match.start()
    before = prefix[:start]
    if (before and re.search(r"[A-Za-z0-9_./^]$", before)
            and not re.search(r"\\(?:oplus|otimes|def)$", before)):
        return None
    return start, match.group(0)


class _ColorRegistry:
    """Give CSS colours stable xcolor names."""

    def __init__(self, *, enabled: bool = True) -> None:
        self._names: dict[str, str] = {}
        self.enabled = enabled

    def use(self, value: object, default: str = "black") -> str:
        if not self.enabled:
            return default
        raw = str(value or default).strip()
        if not raw:
            raw = default
        if raw.startswith("#"):
            hex_value = raw[1:]
            if len(hex_value) == 3:
                hex_value = "".join(character * 2 for character in hex_value)
            if re.fullmatch(r"[0-9a-fA-F]{6}", hex_value):
                key = f"#{hex_value.lower()}"
                if key not in self._names:
                    self._names[key] = f"btcolor{len(self._names)}"
                return self._names[key]
        rgb = re.fullmatch(
            r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", raw,
            re.IGNORECASE,
        )
        if rgb:
            return self.use("#%02x%02x%02x" % tuple(map(int, rgb.groups())), default)
        return raw

    def definitions(self) -> list[str]:
        return [
            rf"\definecolor{{{name}}}{{HTML}}{{{value[1:].upper()}}}"
            for value, name in self._names.items()
        ]


def _option_value(style: Mapping[str, object], *names: str) -> object:
    for name in names:
        if name in style:
            return style[name]
    return None


def _length_option(value: object, suffix: str = "pt") -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{_fmt(float(value))}{suffix}"
    raw = str(value or "").strip()
    if not raw:
        return ""
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", raw):
        return raw + suffix
    return raw


def _style_options(
    style: Mapping[str, object],
    colors: _ColorRegistry,
    *,
    default_fill: object = "white",
    default_draw: object = "black",
    default_width: object = 1.0,
    include_fill: bool = True,
) -> list[str]:
    fill = _option_value(style, "fill", "fill_color", "background_color")
    draw = _option_value(style, "draw", "stroke", "line_color", "stroke_color", "color")
    width = _option_value(style, "line_width", "stroke_width", "stroke-width")
    if fill is None:
        fill = default_fill
    if draw is None:
        draw = default_draw
    if width is None:
        width = default_width
    options = []
    if include_fill:
        options.append(f"fill={colors.use(fill, 'white')}")
    options.extend((f"draw={colors.use(draw)}", f"line width={_length_option(width)}"))
    line_style = _option_value(style, "line_style", "style", "stroke_style")
    if line_style:
        raw_style = str(line_style).strip()
        if raw_style in {"solid", "dashed", "dotted", "dashdotted", "double"}:
            options.append(raw_style)
        elif raw_style.startswith("dash pattern"):
            options.append(raw_style)
    dash = _option_value(style, "stroke_dasharray", "stroke-dasharray", "dash_array")
    if dash:
        parts = re.split(r"[ ,]+", str(dash).strip())
        if len(parts) >= 2:
            options.append(
                "dash pattern="
                + " ".join(
                    f"on {_length_option(part)}" if index % 2 == 0
                    else f"off {_length_option(part)}"
                    for index, part in enumerate(parts)
                )
            )
    cap = _option_value(style, "line_cap", "stroke_linecap")
    join = _option_value(style, "line_join", "stroke_linejoin")
    if cap:
        options.append(f"line cap={cap}")
    if join:
        options.append(f"line join={join}")
    return options


def _semantic_style_options(
    style: Mapping[str, object], colors: _ColorRegistry,
) -> list[str]:
    """Keep authored colours and stroke style, never whiteboard geometry."""
    if not colors.enabled:
        return []
    options: list[str] = []
    fill = _option_value(style, "fill", "fill_color", "background_color")
    draw = _option_value(style, "draw", "stroke", "line_color", "stroke_color", "color")
    if fill is not None and str(fill).lower() not in {"white", "#ffffff"}:
        options.append(f"fill={colors.use(fill, 'white')}")
    if draw is not None and str(draw).lower() not in {"black", "#000000", "#17202a"}:
        options.append(f"draw={colors.use(draw)}")
    line_style = _option_value(style, "line_style", "style", "stroke_style")
    if line_style in {"solid", "dashed", "dotted", "dashdotted", "double"}:
        options.append(str(line_style))
    elif _option_value(style, "stroke_dasharray", "stroke-dasharray", "dash_array"):
        options.append("dashed")
    return options


def _tikz_path(points: Sequence[tuple[float, float]]) -> str:
    if not points:
        return ""
    result = [f"({_fmt(points[0][0])},{_fmt(points[0][1])})"]
    for start, end in zip(points, points[1:]):
        if abs(start[1] - end[1]) < 1e-9:
            result.append(f"-- ({_fmt(end[0])},{_fmt(end[1])})")
        else:
            middle = (start[0] + end[0]) / 2
            result.append(
                ".. controls "
                f"({_fmt(middle)},{_fmt(start[1])}) and "
                f"({_fmt(middle)},{_fmt(end[1])}) .. "
                f"({_fmt(end[0])},{_fmt(end[1])})"
            )
    return " ".join(result)


def _picture(body: Sequence[str], *, scale: str = "1em") -> str:
    content = "\n".join(f"  {line}" for line in body)
    return (
        r"\tikz[x=" + scale + ",y=-" + scale
        + r",baseline=(current bounding box.center)]{" + "\n"
        + content + "\n}"
    )


def _young_cells(term: Mapping[str, object]) -> list[dict[str, object]]:
    barred = term.get("barred", [])
    unbarred = term.get("unbarred", [])
    if not isinstance(barred, list) or not isinstance(unbarred, list):
        return []
    cells: list[dict[str, object]] = []
    for row, width in enumerate(unbarred):
        for column in range(int(width)):
            cells.append({
                "side": "unbarred", "index": row, "row": row, "column": column,
            })
    for index, width in enumerate(barred):
        for column in range(int(width)):
            cells.append({
                "side": "barred", "index": index,
                "row": len(unbarred) + len(barred) - 1 - index,
                "column": -1 - column,
            })
    return cells


def _cell_style(
    styles: Mapping[str, object], term_index: int, cell: Mapping[str, object]
) -> Mapping[str, object]:
    side = str(cell.get("side", ""))
    row = cell.get("row")
    column = cell.get("column")
    candidates = (
        f"{term_index}:{side}:{row}:{column}",
        f"{term_index}:{row}:{column}",
        f"{term_index}:{cell.get('cell_index')}",
        f"{side}:{row}:{column}",
        f"{row}:{column}",
    )
    for key in candidates:
        value = styles.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _pair_term_latex(
    term: Mapping[str, object],
    term_index: int,
    styles: Mapping[str, object],
    colors: _ColorRegistry,
    *,
    pad_to_n0: bool,
    drawing: Mapping[str, object] | None = None,
) -> str:
    barred = term.get("barred", [])
    unbarred = term.get("unbarred", [])
    barred = barred if isinstance(barred, list) else []
    unbarred = unbarred if isinstance(unbarred, list) else []
    labels = term.get("labels", [])
    labels = labels if isinstance(labels, list) else []

    def cell(side: str, row: int, column: int) -> str:
        global_row = (
            row if side == "unbarred"
            else len(unbarred) + len(barred) - 1 - row
        )
        visual_column = column if side == "unbarred" else -1 - column
        descriptor = {"side": side, "row": global_row, "column": visual_column}
        descriptor["cell_index"] = next((
            index for index, candidate in enumerate(_young_cells(term))
            if candidate.get("side") == side
            and candidate.get("row") == global_row
            and candidate.get("column") == visual_column
        ), None)
        style = _cell_style(styles, term_index, descriptor)
        options = _semantic_style_options(style, colors)
        label = next((
            item for item in labels
            if isinstance(item, Mapping)
            and item.get("side") == side
            and item.get("row") == row
            and item.get("column") == column
        ), None)
        value = "" if label is None else _tex_text(label.get("value", ""))
        value_is_barred = False
        if drawing is not None:
            drawing_column = (
                len(barred) and int(barred[0]) - 1 - column
                if side == "barred" else (int(barred[0]) if barred else 0) + column
            )
            drawing_row = (
                len(unbarred) + len(barred) - 1 - row
                if side == "barred" else row
            )
            drawing_cell = next((
                item for item in drawing.get("cells", [])
                if isinstance(item, Mapping)
                and item.get("row") == drawing_row
                and item.get("column") == drawing_column
            ), None)
            drawing_labels = (
                drawing_cell.get("labels", [])
                if isinstance(drawing_cell, Mapping) else []
            )
            if isinstance(drawing_cell, Mapping) and drawing_cell.get("dashed"):
                options.append("dashed")
            texts = [
                _tex_text(item.get("text", ""))
                for item in drawing_labels if isinstance(item, Mapping)
            ]
            text_barred = [
                bool(item.get("barred"))
                for item in drawing_labels if isinstance(item, Mapping)
            ]
            if len(texts) >= 2:
                split_texts = [
                    rf"\overline{{{text}}}" if barred_text else text
                    for text, barred_text in zip(texts[:2], text_barred[:2], strict=True)
                ]
                value = rf"\splitbox{{{split_texts[0]}}}{{{split_texts[1]}}}"
            elif texts:
                value = texts[0]
                value_is_barred = text_barred[0]
            elif isinstance(drawing_cell, Mapping) and drawing_cell.get("bullet"):
                value = r"\bullet"
        if label is not None:
            text_color = _option_value(label, "text_color", "color")
            if text_color is not None:
                options.append(f"text={colors.use(text_color)}")
        if (side == "barred" or value_is_barred) and value and not value.startswith(
            (r"\splitbox", r"\bullet")
        ):
            value = rf"\overline{{{value}}}"
        if side == "barred" and not value:
            value = r"\bullet"
        if value and not value.startswith(r"\splitbox"):
            value = rf"\ensuremath{{{value}}}"
        return f"[{','.join(options)}] {value}"

    covar_rows = [
        " & ".join(cell("unbarred", row, column) for column in range(int(width)))
        for row, width in enumerate(unbarred)
    ]
    convar_rows = [
        " & ".join(cell("barred", row, column)
                   for column in reversed(range(int(barred[row]))))
        for row in reversed(range(len(barred)))
    ]
    drawing_hpad: int | None = None
    drawing_cells = (
        [item for item in drawing.get("cells", []) if isinstance(item, Mapping)]
        if isinstance(drawing, Mapping) else []
    )
    if drawing_cells:
        indexed_cells = list(enumerate(drawing_cells))
        axis = int(barred[0]) if barred else 0

        def drawing_cell(item: Mapping[str, object], index: int) -> str:
            raw_style = styles.get(f"{term_index}:{index}", {})
            style = raw_style if isinstance(raw_style, Mapping) else {}
            options = _semantic_style_options(style, colors)
            if item.get("dashed"):
                options.append("dashed")
            drawing_labels = [
                label for label in item.get("labels", [])
                if isinstance(label, Mapping)
            ]
            texts = [
                (rf"\overline{{{_tex_text(label.get('text', ''))}}}"
                 if label.get("barred") else _tex_text(label.get("text", "")))
                for label in drawing_labels
            ]
            if len(texts) >= 2:
                value = rf"\splitbox{{{texts[0]}}}{{{texts[1]}}}"
            elif texts:
                value = rf"\ensuremath{{{texts[0]}}}"
            elif item.get("bullet"):
                value = r"\ensuremath{\bullet}"
            else:
                value = ""
            return f"[{','.join(options)}] {value}"

        def drawing_rows(side: str) -> tuple[list[str], list[int]]:
            on_side = [
                (index, item) for index, item in indexed_cells
                if (int(item.get("column", 0)) >= axis) == (side == "unbarred")
            ]
            row_numbers = sorted({int(item.get("row", 0)) for _, item in on_side})
            rows = [
                " & ".join(
                    drawing_cell(item, index)
                    for index, item in sorted(
                        ((index, item) for index, item in on_side
                         if int(item.get("row", 0)) == row),
                        key=lambda candidate: int(candidate[1].get("column", 0)),
                    )
                )
                for row in row_numbers
            ]
            return rows, row_numbers

        covar_rows, covar_row_numbers = drawing_rows("unbarred")
        convar_rows, convar_row_numbers = drawing_rows("barred")
        if convar_row_numbers:
            drawing_hpad = max(
                0,
                convar_row_numbers[0]
                - (covar_row_numbers[-1] + 1 if covar_row_numbers else 0),
            )
    # The coefficient is intentionally part of the pair fragment.  The
    # whiteboard renderer hides a numeric prefix before a \pair marker for the
    # same reason: it belongs to the editable pair term.
    coefficient = str(term.get("coefficient", "1"))
    n0 = str(term.get("n0", "0"))
    prefactor = rf"{coefficient}_{{{_tex_text(n0)}}}\,"
    body = [r"\begin{ydpair}"]
    if covar_rows:
        body.extend((r"  \covar{", "    " + r" \\".join(covar_rows), "  }"))
    if pad_to_n0 and convar_rows and (covar_rows or drawing_hpad):
        padding = drawing_hpad or 0
        if drawing_hpad is None:
            try:
                padding = max(
                    0,
                    int(n0) - len(unbarred) - len(barred),
                )
            except ValueError:
                padding = 0
        body.append(rf"  \hpad{{{padding}}}")
    if convar_rows:
        body.extend((r"  \convar{", "    " + r" \\".join(convar_rows), "  }"))
    body.append(r"\end{ydpair}")
    return prefactor + "\n".join(body)


def _pair_latex(
    pair_widget: object,
    colors: _ColorRegistry,
    styles: Mapping[str, object],
    *,
    pad_to_n0: bool,
) -> str:
    owner = getattr(pair_widget, '_pair_session', None)
    expression = owner.value.state() if owner is not None else _get(pair_widget, "pair_expression", pair_widget)
    if owner is not None:
        styles = owner.styles
    if not isinstance(expression, Mapping):
        return r"\pair"
    terms = expression.get("terms", [])
    if not isinstance(terms, list) or not terms:
        return "0"
    syntax = expression.get("syntax")
    if not isinstance(syntax, list) or syntax.count("pair") != len(terms):
        syntax = [token for index in range(len(terms))
                  for token in ((["sum"] if index else []) + ["pair"])]
    result: list[str] = []
    index = 0
    for token in syntax:
        if token == "pair":
            term = terms[index]
            index += 1
            if isinstance(term, Mapping):
                result.append(_pair_term_latex(
                    term, index - 1, styles, colors, pad_to_n0=pad_to_n0,
                ))
        elif token == "sum":
            result.append(r"\oplus")
        elif token == "tensor":
            result.append(r"\otimes")
        elif token == "(":
            result.append(r"\left(")
        elif token == ")":
            result.append(r"\right)")
    return " ".join(result)


def _pair_tree_latex(
    tree: object,
    colors: _ColorRegistry,
    *,
    pad_to_n0: bool,
    styles: Mapping[str, object] | None = None,
) -> str:
    term_index = 0
    styles = styles or {}

    def render(node: object, parent: str | None = None) -> str:
        nonlocal term_index
        if not isinstance(node, Mapping):
            return ""
        kind = node.get("kind")
        if kind == "pair":
            term = node.get("term")
            drawing = node.get("drawing")
            if not isinstance(term, Mapping):
                return ""
            result = _pair_term_latex(
                term,
                term_index,
                styles,
                colors,
                pad_to_n0=pad_to_n0,
                drawing=drawing if isinstance(drawing, Mapping) else None,
            )
            term_index += 1
            return result
        children = node.get("children", [])
        if not isinstance(children, list):
            return ""
        operator = (
            r" \oplus " if kind == "sum" else r" \otimes "
        )
        value = operator.join(render(child, str(kind)) for child in children)
        return rf"\left({value}\right)" if parent == "tensor" and kind == "sum" else value

    return render(tree)


@dataclass
class _Endpoint:
    kind: str
    level: int | None = None
    side: str | None = None
    node: int | None = None
    label: int | None = None


class _ProjectorLatex:
    def __init__(self, widget: object, colors: _ColorRegistry) -> None:
        self.widget = widget
        self.colors = colors
        if getattr(widget, '_editor_session', None) is not None:
            widget = widget.configuration.state()
        graph = _get(widget, "graph", {})
        self.graph = graph if isinstance(graph, Mapping) else {}
        geometry = self.graph.get("geometry", {})
        self.geometry = geometry if isinstance(geometry, Mapping) else {}
        self.positions = _get(widget, "positions", {})
        self.positions = self.positions if isinstance(self.positions, Mapping) else {}
        self.port_orders = _get(widget, "port_orders", {})
        self.port_orders = self.port_orders if isinstance(self.port_orders, Mapping) else {}
        self.boundary_orders = _get(widget, "boundary_orders", {})
        self.boundary_orders = (
            self.boundary_orders if isinstance(self.boundary_orders, Mapping) else {}
        )
        self.free_levels = _get(widget, "free_levels", {})
        self.free_levels = self.free_levels if isinstance(self.free_levels, Mapping) else {}
        raw_nodes = self.graph.get("nodes", [])
        self.nodes: dict[int, dict[str, object]] = {}
        if isinstance(raw_nodes, list):
            for raw in raw_nodes:
                if not isinstance(raw, Mapping):
                    continue
                index = int(raw.get("index", len(self.nodes)))
                orders = self.port_orders.get(str(index), {})
                orders = orders if isinstance(orders, Mapping) else {}
                labels = list(raw.get("labels", []))
                position = self.positions.get(str(index), {})
                position = position if isinstance(position, Mapping) else {}
                spacing = self._geometry("level_spacing", 1)
                top = self._geometry("top_margin", 0)
                level = round(
                    (_number(position.get("y"), top) - top) / spacing
                    - (len(labels) - 1) / 2
                ) if position else 0
                self.nodes[index] = {
                    **raw,
                    "index": index,
                    "level": max(0, level),
                    "input_order": list(orders.get("input", raw.get("input_labels", labels))),
                    "output_order": list(orders.get("output", raw.get("output_labels", labels))),
                }
        self.line_colors = _get(widget, "line_colors", {})
        self.line_colors = self.line_colors if isinstance(self.line_colors, Mapping) else {}
        self.compiled = self._uses_compiled_display()
        self.columns = self._columns()
        self.layers = max(
            1,
            len(self.columns) if self.compiled else max(
                [int(node.get("layer", 0)) + 1 for node in self.nodes.values()] or [1]
            ),
        )

    def _geometry(self, key: str, default: float) -> float:
        return _number(self.geometry.get(key), default)

    def _columns(self) -> list[list[int]]:
        display = self.graph.get("display", {})
        columns = display.get("operator_columns", []) if isinstance(display, Mapping) else []
        if isinstance(columns, list):
            return [list(map(int, column)) for column in columns if isinstance(column, list)]
        return []

    def _uses_compiled_display(self) -> bool:
        if _get(self.widget, "mode", "evaluate") != "evaluate":
            return False
        display = self.graph.get("display", {})
        if not isinstance(display, Mapping) or not isinstance(display.get("strands"), list):
            return False
        columns = self._columns()
        if not columns or any(not column for column in columns):
            return False
        planned = {index for column in columns for index in column}
        live = {index for index, node in self.nodes.items() if node.get("kind") != "permutation"}
        return live == planned

    def _display_column(self, node: int) -> int:
        for index, column in enumerate(self.columns):
            if node in column:
                return index
        return -1





    def _boundary_level(self, side: str, label: int) -> int:
        order = self.boundary_orders.get(side, self.graph.get("boundary_labels", []))
        if not isinstance(order, list):
            order = []
        try:
            return order.index(label)
        except ValueError:
            labels = self.graph.get("boundary_labels", [])
            return labels.index(label) if isinstance(labels, list) and label in labels else 0

    def _endpoint(self, raw: Mapping[str, object], *, side: str | None = None) -> _Endpoint:
        if raw.get("type") == "right-anchor":
            return _Endpoint("right-anchor", level=int(raw.get("level", 0)))
        if raw.get("type") == "left-anchor":
            return _Endpoint("left-anchor", level=int(raw.get("level", 0)))
        return _Endpoint(
            "port", side=str(raw.get("side", side or "input")),
            node=int(raw.get("node", 0)), label=int(raw.get("label", 0)),
        )


    def _endpoint_layer(self, endpoint: _Endpoint) -> int:
        if endpoint.kind == "right-anchor":
            return self.layers
        if endpoint.kind == "left-anchor":
            return -1
        return int(self.nodes[endpoint.node or 0].get("layer", 0))


    def _connections(self) -> list[tuple[_Endpoint, _Endpoint, object]]:
        result = []
        raw = self.graph.get("connections", [])
        if isinstance(raw, list):
            for connection in raw:
                if not isinstance(connection, Mapping):
                    continue
                result.append((
                    self._endpoint(connection.get("source", {}), side="output"),
                    self._endpoint(connection.get("target", {}), side="input"),
                    connection.get("boundary_label"),
                ))
        for item, source_kind, target_kind in (
            ("external_inputs", "right-anchor", "port"),
            ("external_outputs", "port", "left-anchor"),
        ):
            values = self.graph.get(item, [])
            if not isinstance(values, list):
                continue
            for boundary in values:
                if not isinstance(boundary, Mapping):
                    continue
                label = int(boundary.get("boundary_label", 0))
                port = boundary.get("port", {})
                port = port if isinstance(port, Mapping) else {}
                if source_kind == "right-anchor":
                    source = _Endpoint("right-anchor", level=self._boundary_level("input", label))
                    target = self._endpoint({**port, "type": "port"}, side="input")
                else:
                    source = self._endpoint({**port, "type": "port"}, side="output")
                    target = _Endpoint("left-anchor", level=self._boundary_level("output", label))
                result.append((source, target, label))
        return result



    def _level_count(self) -> int:
        levels = [len(self.graph.get("boundary_labels", []))]
        levels.extend(int(node["level"]) + len(node.get("labels", [])) for node in self.nodes.values())
        for assignments in self.free_levels.values():
            if isinstance(assignments, Mapping):
                levels.extend(int(value) + 1 for value in assignments.values())
        return max(1, *(level for level in levels if level > 0))

    def _endpoint_key(self, endpoint: _Endpoint) -> str:
        if endpoint.kind == "right-anchor":
            return f"right-anchor:{endpoint.level}"
        if endpoint.kind == "left-anchor":
            return f"left-anchor:{endpoint.level}"
        return f"{endpoint.side}:{endpoint.node}:{endpoint.label}"



    def _display_endpoint(self, raw: Mapping[str, object]) -> _Endpoint:
        kind = raw.get("kind")
        label = int(raw.get("label", 0))
        if kind == "right_boundary":
            return _Endpoint("right-anchor", level=self._boundary_level("input", label))
        if kind == "left_boundary":
            return _Endpoint("left-anchor", level=self._boundary_level("output", label))
        return _Endpoint(
            "port", side="input" if kind == "operator_input" else "output",
            node=int(raw.get("node", 0)), label=label,
        )



    def render(self) -> str:
        """Translate the saved topology into the public layer DSL."""
        count = self._level_count()
        visible = (
            {index for column in self.columns for index in column}
            if self.compiled else set(self.nodes)
        )

        def direction(value: object) -> str:
            return "<" if value == "left" else ">" if value == "right" else ""

        def options_for(key: str, legacy: str | None = None, arrow: str = "") -> str:
            raw = self.line_colors.get(key)
            if raw is None and legacy:
                raw = self.line_colors.get(legacy)
            style = raw if isinstance(raw, Mapping) else {"color": raw} if raw else {}
            colour = _option_value(style, "draw", "stroke", "line_color", "color")
            options: list[str] = []
            if arrow:
                options.append(arrow)
            if self.colors.enabled and colour is not None and str(colour).lower() not in {
                "black", "#000000", "#17202a",
            }:
                options.append(f"draw={self.colors.use(colour)}")
            line_style = _option_value(style, "line_style", "style", "stroke_style")
            if line_style in {"solid", "dashed", "dotted", "dashdotted", "double"}:
                options.append(str(line_style))
            elif _option_value(
                style, "stroke_dasharray", "stroke-dasharray", "dash_array",
            ):
                options.append("dashed")
            if not options:
                return ""
            if len(options) == 1:
                return arrow if arrow else options[0]
            return "{" + ",".join(options) + "}"

        connections = self._connections()
        if self.compiled:
            # Use the same visible endpoint keys as whiteboard paint. A strand
            # can span hidden permutation nodes, so its colour is not stored
            # on any one of the concrete algebra edges.
            connections = [
                (
                    self._display_endpoint(strand["source"]),
                    self._display_endpoint(strand["target"]),
                    strand.get("strand_label"),
                )
                for strand in self.graph["display"]["strands"]
                if isinstance(strand, Mapping)
                and isinstance(strand.get("source"), Mapping)
                and isinstance(strand.get("target"), Mapping)
            ]

        def connection_label(
            item: tuple[_Endpoint, _Endpoint, object],
        ) -> object:
            if item[2] is not None:
                return item[2]
            if item[0].label is not None:
                return item[0].label
            return item[1].label

        def export_endpoint_layer(endpoint: _Endpoint) -> int:
            if not self.compiled or endpoint.kind != "port":
                return self._endpoint_layer(endpoint)
            return self._display_column(endpoint.node or 0)

        def connection_options(
            predicate: Callable[[tuple[_Endpoint, _Endpoint, object]], bool],
        ) -> str:
            item = next((value for value in connections if predicate(value)), None)
            if item is None:
                return ""
            key = f"{self._endpoint_key(item[0])}->{self._endpoint_key(item[1])}"
            return options_for(key, f"strand:{connection_label(item)}")

        def permutation_options(
            node: Mapping[str, object], input_label: object, output_label: object,
        ) -> str:
            """Carry a strand style through an explicit permutation node."""
            index = int(node.get("index", 0))
            internal_key = (
                f"input:{index}:{input_label}->output:{index}:{output_label}"
            )
            internal = options_for(internal_key)
            if internal:
                return internal
            entering = connection_options(lambda item: (
                item[1].kind == "port"
                and item[1].node == index
                and item[1].label == input_label
            ))
            if entering:
                return entering
            return connection_options(lambda item: (
                item[0].kind == "port"
                and item[0].node == index
                and item[0].label == output_label
            ))

        def node_line_options(
            node: Mapping[str, object], label: object, side: str,
        ) -> str:
            index = int(node.get("index", 0))
            endpoint = 0 if side == "left" else 1
            return connection_options(lambda item: (
                item[endpoint].kind == "port"
                and item[endpoint].node == index
                and item[endpoint].label == label
            ))

        def level_options(layer: int, level: int) -> str:
            assignments = layer_assignments(layer)
            label = next((
                int(raw_label) for raw_label, raw_level in assignments.items()
                if int(raw_level) == level
            ), None) if isinstance(assignments, Mapping) else None
            if label is None:
                labels = self.graph.get("boundary_labels", [])
                label = labels[level] if isinstance(labels, list) and level < len(labels) else None
            return connection_options(lambda item: (
                connection_label(item) == label
                and export_endpoint_layer(item[1]) <= layer
                and layer < export_endpoint_layer(item[0])
            ))

        def optional(styles: list[str]) -> str:
            return "[" + ",".join(styles) + "]" if any(styles) else ""

        def operator_optionals(left: list[str], right: list[str]) -> str:
            if left == right:
                return optional(left)
            return "[" + ",".join(left) + "][" + ",".join(right) + "]"

        def permutation_layer(
            targets: list[int] | None,
            styles: list[str],
            *,
            omit_identity: bool = False,
        ) -> str | None:
            if targets is None or sorted(targets) != list(range(1, count + 1)):
                return None
            if omit_identity and targets == list(range(1, count + 1)):
                return None
            numbers = ",".join(map(str, range(1, count + 1)))
            rendered_targets = ",".join(map(str, targets))
            return (
                "  \\layer{\\permute" + optional(styles)
                + rf"{{{numbers}}}{{{rendered_targets}}}}}"
            )

        topology_connections = connections

        def endpoint_level(endpoint: _Endpoint) -> int:
            if endpoint.kind != "port":
                return int(endpoint.level or 0)
            node = self.nodes[endpoint.node or 0]
            order = node[
                "input_order" if endpoint.side == "input" else "output_order"
            ]
            return int(node.get("level", 0)) + list(order).index(endpoint.label)

        def layer_assignments(export_layer: int) -> Mapping[str, object]:
            if self.compiled:
                display_levels = self.graph.get("display_free_levels")
                if isinstance(display_levels, Mapping):
                    # Python repairs these column routes after movement and
                    # rerouting. The Create/algebra namespace may be stale or
                    # alias multiple packed columns; never merge it over them.
                    return display_levels.get(str(export_layer), {})
                column = self.columns[export_layer]
                export_layer = int(self.nodes[column[0]].get("layer", export_layer))
            return self.free_levels.get(str(export_layer), {})

        def bypass_level(
            item: tuple[_Endpoint, _Endpoint, object], export_layer: int,
        ) -> int:
            assignments = layer_assignments(export_layer)
            label = connection_label(item)
            if isinstance(assignments, Mapping) and label is not None:
                assigned = assignments.get(str(label))
                if assigned is not None:
                    return int(assigned)
            source_layer = export_endpoint_layer(item[0])
            target_layer = export_endpoint_layer(item[1])
            if source_layer == target_layer:
                return endpoint_level(item[1])
            fraction = (
                (source_layer - export_layer) / (source_layer - target_layer)
            )
            interpolated = (
                endpoint_level(item[0])
                + (endpoint_level(item[1]) - endpoint_level(item[0])) * fraction
            )
            return max(0, min(count - 1, round(interpolated)))

        def cut_targets(cut: int) -> list[int] | None:
            """Map physical levels across one exact left-to-right cut."""
            targets: list[int | None] = [None] * count
            for item in topology_connections:
                source_layer = export_endpoint_layer(item[0])
                target_layer = export_endpoint_layer(item[1])
                if not target_layer <= cut < source_layer:
                    continue
                left_level = (
                    endpoint_level(item[1])
                    if target_layer == cut
                    else bypass_level(item, cut)
                )
                right_level = (
                    endpoint_level(item[0])
                    if source_layer == cut + 1
                    else bypass_level(item, cut + 1)
                )
                if not (0 <= left_level < count and 0 <= right_level < count):
                    return None
                target = right_level + 1
                if targets[left_level] not in {None, target}:
                    return None
                targets[left_level] = target
            if 0 <= cut < self.layers - 1:
                left_free = layer_assignments(cut)
                right_free = layer_assignments(cut + 1)
                if isinstance(left_free, Mapping) and isinstance(right_free, Mapping):
                    for label in left_free.keys() & right_free.keys():
                        left_level = int(left_free[label])
                        target = int(right_free[label]) + 1
                        if targets[left_level] not in {None, target}:
                            return None
                        if target in targets and targets[left_level] != target:
                            return None
                        targets[left_level] = target
            # Older saved graphs may omit straight pass-through connection
            # records.  The only safe inference for an unmatched level is an
            # unmatched level at the same position; never invent a crossing.
            used = {target for target in targets if target is not None}
            for level, target in enumerate(targets):
                if target is None and level + 1 not in used:
                    targets[level] = level + 1
                    used.add(level + 1)
            if any(target is None for target in targets):
                return None
            return [int(target) for target in targets]

        def left_boundary_options(level: int) -> str:
            item = next((value for value in connections if (
                value[1].kind == "left-anchor" and value[1].level == level
            )), None)
            if item is None:
                return ""
            key = f"{self._endpoint_key(item[0])}->{self._endpoint_key(item[1])}"
            return options_for(key, f"strand:{connection_label(item)}")

        def face_options(
            nodes: list[dict[str, object]], side: str, layer: int, level: int,
        ) -> str:
            for node in nodes:
                top = int(node.get("level", 0))
                order = list(node.get(f"{side}_order", node.get("labels", [])))
                if not top <= level < top + len(order):
                    continue
                label = order[level - top]
                index = int(node.get("index", 0))
                endpoint_index = 1 if side == "input" else 0
                item = next((value for value in connections if (
                    value[endpoint_index].kind == "port"
                    and value[endpoint_index].node == index
                    and value[endpoint_index].label == label
                )), None)
                if item is None:
                    return ""
                key = (
                    f"{self._endpoint_key(item[0])}->"
                    f"{self._endpoint_key(item[1])}"
                )
                return options_for(key, f"strand:{connection_label(item)}")
            return level_options(layer, level)

        start_options: list[str] = []
        end_options: list[str] = []
        boundary_arrow = direction(self.graph.get("out_direction"))
        for level in range(count):
            left = next((item for item in connections
                         if item[1].kind == "left-anchor" and item[1].level == level), None)
            right = next((item for item in connections
                          if item[0].kind == "right-anchor" and item[0].level == level), None)
            if left:
                key = f"{self._endpoint_key(left[0])}->{self._endpoint_key(left[1])}"
                start_options.append(options_for(
                    key, f"strand:{left[2]}", boundary_arrow,
                ))
            else:
                start_options.append(boundary_arrow)
            if right:
                key = f"{self._endpoint_key(right[0])}->{self._endpoint_key(right[1])}"
                end_options.append(options_for(
                    key, f"strand:{right[2]}", boundary_arrow,
                ))
            else:
                end_options.append(boundary_arrow)

        if self.compiled:
            layer_groups = [
                sorted(
                    (self.nodes[index] for index in column if index in visible),
                    key=lambda node: int(node.get("level", 0)),
                )
                for column in self.columns
            ]
        else:
            layer_groups = [
                sorted(
                    (node for index, node in self.nodes.items()
                     if index in visible and int(node.get("layer", 0)) == layer),
                    key=lambda node: int(node.get("level", 0)),
                )
                for layer in range(self.layers)
            ]

        rendered_layers: list[str] = []
        first_layer = next((
            (index, nodes) for index, nodes in enumerate(layer_groups) if nodes
        ), None)
        # Boundary permutations are side-specific topology.  Resolve the
        # output boundary only against the first operator face; never infer it
        # from, or move it from, the input boundary on the right.
        if first_layer is not None and any(
            node.get("kind") in {"symmetriser", "antisymmetriser"}
            for node in first_layer[1]
        ):
            boundary_permutation = permutation_layer(
                cut_targets(-1),
                [left_boundary_options(level) for level in range(count)],
                omit_identity=True,
            )
            if boundary_permutation is not None:
                rendered_layers.append(boundary_permutation)
        for layer_index, nodes in enumerate(layer_groups):
            permutation = next(
                (node for node in nodes if node.get("kind") == "permutation"), None,
            )
            if permutation is not None:
                target = list(range(1, count + 1))
                styles = ["" for _level in range(count)]
                top = int(permutation.get("level", 0))
                inputs = list(permutation.get("input_order", []))
                outputs = list(permutation.get("output_order", []))
                for mapping in permutation.get("mapping", []):
                    if isinstance(mapping, list) and len(mapping) == 2:
                        source_level = top + inputs.index(mapping[0])
                        target[source_level] = top + outputs.index(mapping[1]) + 1
                        styles[source_level] = permutation_options(
                            permutation, mapping[0], mapping[1],
                        )
                numbers = ",".join(map(str, range(1, count + 1)))
                targets = ",".join(map(str, target))
                for level in range(count):
                    if not styles[level]:
                        styles[level] = level_options(layer_index, level)
                rendered_layers.append(
                    "  \\layer{\\permute" + optional(styles)
                    + rf"{{{numbers}}}{{{targets}}}}}",
                )
                continue

            commands: list[str] = []
            cursor = 0
            for node in nodes:
                top = int(node.get("level", 0))
                if top > cursor:
                    styles = [level_options(layer_index, level) for level in range(cursor, top)]
                    commands.append(
                        "\\freelines" + optional(styles) + rf"{{{top - cursor}}}",
                    )
                labels = list(node.get("labels", []))
                size = len(labels)
                command = (
                    "antisymmetriser"
                    if node.get("kind") == "antisymmetriser"
                    else "symmetriser"
                )
                left_styles = [
                    node_line_options(node, label, "left") for label in labels
                ]
                right_styles = [
                    node_line_options(node, label, "right") for label in labels
                ]
                commands.append(
                    "\\" + command
                    + operator_optionals(left_styles, right_styles)
                    + rf"{{{size}}}",
                )
                cursor = top + size
            if cursor < count:
                styles = [
                    level_options(layer_index, level)
                    for level in range(cursor, count)
                ]
                commands.append(
                    "\\freelines" + optional(styles) + rf"{{{count - cursor}}}",
                )
            rendered_layers.append("  \\layer{" + "".join(commands) + "}")

            next_nodes = (
                layer_groups[layer_index + 1]
                if layer_index + 1 < len(layer_groups)
                else []
            )
            if (
                any(node.get("kind") in {"symmetriser", "antisymmetriser"}
                    for node in nodes)
                and any(node.get("kind") in {"symmetriser", "antisymmetriser"}
                        for node in next_nodes)
            ):
                layer_permutation = permutation_layer(
                    cut_targets(layer_index),
                    [face_options(nodes, "input", layer_index, level)
                     for level in range(count)],
                )
                if layer_permutation is not None:
                    rendered_layers.append(layer_permutation)

        last_layer = next((
            (index, nodes) for index, nodes in reversed(list(enumerate(layer_groups)))
            if nodes
        ), None)
        # Likewise, the input-boundary permutation belongs after the final
        # operator and cannot be exchanged with an output-boundary crossing.
        if last_layer is not None and any(
            node.get("kind") in {"symmetriser", "antisymmetriser"}
            for node in last_layer[1]
        ):
            boundary_permutation = permutation_layer(
                cut_targets(self.layers - 1),
                [face_options(last_layer[1], "input", last_layer[0], level)
                 for level in range(count)],
                omit_identity=True,
            )
            if boundary_permutation is not None:
                rendered_layers.append(boundary_permutation)

        body = [
            r"\begin{projector}",
            "  \\startnodes[" + ",".join(start_options) + "]",
            *rendered_layers,
            "  \\endnodes[" + ",".join(end_options) + "]",
            r"\end{projector}",
        ]
        return "\n".join(body)



def _projector_latex(widget: object, colors: _ColorRegistry) -> str:
    return _ProjectorLatex(widget, colors).render()


def _svg_number(value: object, default: float = 0.0) -> float:
    match = re.match(r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", str(value or ""))
    return float(match.group(1)) if match else default


def _svg_style(element: ElementTree.Element, inherited: Mapping[str, object]) -> dict[str, object]:
    style = dict(inherited)
    for key in ("fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap", "stroke-linejoin", "font-size", "text-anchor", "dominant-baseline"):
        if key in element.attrib:
            style[key] = element.attrib[key]
    for declaration in str(element.attrib.get("style", "")).split(";"):
        if ":" in declaration:
            key, value = declaration.split(":", 1)
            style[key.strip()] = value.strip()
    return style


def _svg_path(d: str, transform: tuple[float, float, float, float]) -> str:
    tokens = re.findall(r"[A-Za-z]|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", d)
    index = 0
    command = ""
    current = (0.0, 0.0)
    start = current
    output: list[str] = []
    ox, oy, sx, sy = transform

    def point(x: float, y: float) -> str:
        return f"({_fmt(ox + sx * x)},{_fmt(oy + sy * y)})"

    def number() -> float:
        nonlocal index
        value = float(tokens[index])
        index += 1
        return value

    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]
            index += 1
        relative = command.islower()
        verb = command.upper()
        if verb == "Z":
            output.append("-- cycle")
            current = start
            command = ""
            continue
        if verb == "M" or verb == "L":
            if index + 1 >= len(tokens):
                break
            x, y = number(), number()
            if relative:
                x += current[0]
                y += current[1]
            current = (x, y)
            if verb == "M":
                output.append(point(x, y))
                start = current
                command = "l" if relative else "L"
            else:
                output.append(f"-- {point(x, y)}")
            continue
        if verb == "H" or verb == "V":
            if index >= len(tokens):
                break
            value = number()
            x, y = (value, current[1]) if verb == "H" else (current[0], value)
            if relative:
                x, y = ((current[0] + value, current[1]) if verb == "H"
                        else (current[0], current[1] + value))
            current = (x, y)
            output.append(f"-- {point(x, y)}")
            continue
        if verb == "C":
            if index + 5 >= len(tokens):
                break
            values = [number() for _ in range(6)]
            controls = [tuple(values[:2]), tuple(values[2:4])]
            end = tuple(values[4:6])
            if relative:
                controls = [(x + current[0], y + current[1]) for x, y in controls]
                end = (end[0] + current[0], end[1] + current[1])
            output.append(
                f".. controls {point(*controls[0])} and {point(*controls[1])} .. {point(*end)}"
            )
            current = end
            continue
        if verb == "Q":
            if index + 3 >= len(tokens):
                break
            values = [number() for _ in range(4)]
            control = tuple(values[:2])
            end = tuple(values[2:4])
            if relative:
                control = (control[0] + current[0], control[1] + current[1])
                end = (end[0] + current[0], end[1] + current[1])
            output.append(f".. controls {point(*control)} and {point(*control)} .. {point(*end)}")
            current = end
            continue
        # Unsupported SVG commands are ignored after their command letter;
        # the exporter still retains every supported shape in the equation.
        command = ""
    return " ".join(output)


def _svg_latex(
    source: str,
    colors: _ColorRegistry,
    cell_styles: Mapping[str, object] | None = None,
) -> str:
    """Convert the small, generated whiteboard SVG dialect to TikZ."""

    try:
        root = ElementTree.fromstring(source)
    except ElementTree.ParseError:
        return r"\text{[invalid calculated drawing]}"
    cell_styles = cell_styles or {}
    body: list[str] = []

    def visit(
        element: ElementTree.Element,
        transform: tuple[float, float, float, float],
        inherited: Mapping[str, object],
        cell_key: str | None = None,
    ) -> None:
        tag = element.tag.rsplit("}", 1)[-1]
        style = _svg_style(element, inherited)
        local_cell = element.attrib.get("data-cell", cell_key)
        override = cell_styles.get(str(local_cell)) if local_cell is not None else None
        if isinstance(override, Mapping):
            style.update(override)
        ox, oy, sx, sy = transform
        if tag == "svg":
            x, y = _svg_number(element.attrib.get("x")), _svg_number(element.attrib.get("y"))
            viewbox = [
                _svg_number(value)
                for value in str(element.attrib.get("viewBox", "0 0 1 1")).replace(",", " ").split()
            ]
            if len(viewbox) == 4:
                width = _svg_number(element.attrib.get("width"), viewbox[2])
                height = _svg_number(element.attrib.get("height"), viewbox[3])
                transform = (
                    ox + sx * x - sx * viewbox[0] * width / viewbox[2],
                    oy + sy * y - sy * viewbox[1] * height / viewbox[3],
                    sx * width / viewbox[2],
                    sy * height / viewbox[3],
                )
        elif tag == "line":
            start = (ox + sx * _svg_number(element.attrib.get("x1")), oy + sy * _svg_number(element.attrib.get("y1")))
            end = (ox + sx * _svg_number(element.attrib.get("x2")), oy + sy * _svg_number(element.attrib.get("y2")))
            body.append(rf"\draw[{', '.join(_svg_options(style, colors))}] {_tikz_path([start, end])};")
        elif tag == "rect":
            x, y = _svg_number(element.attrib.get("x")), _svg_number(element.attrib.get("y"))
            width, height = _svg_number(element.attrib.get("width")), _svg_number(element.attrib.get("height"))
            options = _svg_options(style, colors)
            body.append(
                rf"\path[{', '.join(options)}] "
                rf"({_fmt(ox + sx * x)},{_fmt(oy + sy * y)}) rectangle "
                rf"({_fmt(ox + sx * (x + width))},{_fmt(oy + sy * (y + height))});"
            )
        elif tag == "circle":
            x, y = _svg_number(element.attrib.get("cx")), _svg_number(element.attrib.get("cy"))
            radius = _svg_number(element.attrib.get("r")) * min(abs(sx), abs(sy))
            body.append(
                rf"\path[{', '.join(_svg_options(style, colors))}] "
                rf"({_fmt(ox + sx * x)},{_fmt(oy + sy * y)}) circle ({_fmt(radius)});"
            )
        elif tag == "path":
            path = _svg_path(element.attrib.get("d", ""), transform)
            if path:
                body.append(rf"\draw[{', '.join(_svg_options(style, colors))}] {path};")
        elif tag == "text":
            x, y = _svg_number(element.attrib.get("x")), _svg_number(element.attrib.get("y"))
            text_parts: list[str] = []
            for child in element.iter():
                if child.text:
                    value = _tex_text(child.text)
                    if child is not element and child.attrib.get("baseline-shift") == "sub":
                        value = rf"_{{{value}}}"
                    text_parts.append(value)
            if not text_parts and element.text:
                text_parts.append(_tex_text(element.text))
            anchor = {"middle": "center", "end": "east", "start": "west"}.get(str(style.get("text-anchor")), "center")
            font_size = _svg_number(style.get("font-size"), 16) * min(abs(sx), abs(sy)) * .35
            options = [f"anchor={anchor}", f"font=\\fontsize{{{_fmt(font_size)}pt}}{{{_fmt(font_size * 1.2)}pt}}\\selectfont"]
            body.append(
                rf"\node[{', '.join(options)}] at "
                rf"({_fmt(ox + sx * x)},{_fmt(oy + sy * y)}) "
                rf"{{\ensuremath{{{''.join(text_parts)}}}}};"
            )
        for child in element:
            visit(child, transform, style, local_cell)

    def _svg_options(style: Mapping[str, object], registry: _ColorRegistry) -> list[str]:
        fill = style.get("fill", "none")
        stroke = style.get("stroke", "black")
        options: list[str] = []
        if str(fill) != "none":
            options.append(
                f"fill={registry.use('#17202a' if fill == 'currentColor' else fill)}"
            )
        else:
            options.append("fill=none")
        if str(stroke) != "none":
            options.append(
                f"draw={registry.use('#17202a' if stroke == 'currentColor' else stroke)}"
            )
        else:
            options.append("draw=none")
        width = _svg_number(style.get("stroke-width"), 1) * .35
        options.append(f"line width={_fmt(width)}pt")
        dash = style.get("stroke-dasharray")
        if dash and str(dash) != "none":
            parts = re.split(r"[ ,]+", str(dash))
            if len(parts) >= 2:
                options.append("dash pattern=" + " ".join(
                    f"on {_fmt(_svg_number(part) * .35)}pt" if index % 2 == 0
                    else f"off {_fmt(_svg_number(part) * .35)}pt"
                    for index, part in enumerate(parts)
                ))
        if style.get("stroke-linecap"):
            options.append(f"line cap={style['stroke-linecap']}")
        return options

    visit(root, (0.0, 0.0, 1.0, 1.0), {})
    return _picture(body, scale=".35pt")


def whiteboard_latex(
    document: object,
    *,
    include_preamble: bool = False,
    include_colors: bool = True,
    pad_to_n0: bool = False,
    include_equation_alignment: bool = False,
) -> str:
    """Render a whiteboard widget or state mapping as LaTeX.

    The returned fragment expects ``\\usepackage{birdtracks}`` to be loaded.
    ``include_preamble=True`` wraps it in a small standalone article, which is
    useful for copying the result to a TeX compiler.
    """

    blocks = _get(document, "blocks", [])
    if not isinstance(blocks, list):
        raise TypeError("whiteboard blocks must be a list")
    projector_ids = list(_get(document, "embedded_projector_ids", []) or [])
    projector_widgets = list(_get(document, "embedded_projectors", []) or [])
    pair_ids = list(_get(document, "embedded_pair_ids", []) or [])
    pair_widgets = list(_get(document, "embedded_pairs", []) or [])
    backend_ids = list(_get(document, "backend_projector_ids", []) or [])
    backend_widgets = list(_get(document, "backend_projectors", []) or [])
    projectors = dict(zip(map(str, projector_ids), projector_widgets, strict=False))
    pairs = dict(zip(map(str, pair_ids), pair_widgets, strict=False))
    backends = dict(zip(map(str, backend_ids), backend_widgets, strict=False))
    colors = _ColorRegistry(enabled=include_colors)
    rendered_blocks: list[str] = []

    def equation_source(value: str) -> str:
        value = re.sub(r"\\def\b", "=", value)
        return value.replace("=", "=&") if include_equation_alignment else value

    for block in blocks:
        if not isinstance(block, Mapping):
            continue
        source = str(block.get("source", ""))
        block_id = str(block.get("id", ""))
        calculation_svg = block.get("calculation_svg")
        if isinstance(calculation_svg, str) and calculation_svg:
            pair_tree = block.get("pair_expression_tree")
            if isinstance(pair_tree, Mapping):
                styles = block.get("calculation_cell_styles", {})
                styles = styles if isinstance(styles, Mapping) else {}
                rendered_blocks.append(
                    equation_source(source)
                    + _pair_tree_latex(
                        pair_tree,
                        colors,
                        pad_to_n0=pad_to_n0,
                        styles=styles,
                    )
                )
                continue
            styles = block.get("calculation_cell_styles", {})
            styles = styles if isinstance(styles, Mapping) else {}
            rendered_blocks.append(_svg_latex(calculation_svg, colors, styles))
            continue
        replacements: list[tuple[int, int, str]] = []
        for occurrence, match in enumerate(_PROJECTOR_MARKER.finditer(source)):
            child = projectors.get(f"{block_id}:projector:{occurrence}")
            if child is not None:
                replacements.append((match.start(), match.end(), _projector_latex(child, colors)))
        for occurrence, match in enumerate(_PAIR_MARKER.finditer(source)):
            child = pairs.get(f"{block_id}:pair:{occurrence}")
            if child is None:
                continue
            start = match.start()
            prefactor = _prefactor_before(source, start)
            if prefactor is not None:
                start = prefactor[0]
            styles = _get(child, "pair_cell_styles", {})
            styles = styles if isinstance(styles, Mapping) else {}
            replacements.append((
                start,
                match.end(),
                _pair_latex(child, colors, styles, pad_to_n0=pad_to_n0),
            ))
        terms = block.get("backend_terms", [])
        if isinstance(terms, list):
            for term in terms:
                if not isinstance(term, Mapping):
                    continue
                start, end = term.get("start"), term.get("end")
                if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(source):
                    continue
                child = backends.get(str(term.get("id", "")))
                if child is not None:
                    replacements.append((start, end, _projector_latex(child, colors)))
        replacements.sort(key=lambda item: (item[0], item[1]))
        output: list[str] = []
        position = 0
        for start, end, replacement in replacements:
            if start < position:
                continue
            output.append(equation_source(source[position:start]))
            output.append(replacement)
            position = end
        output.append(equation_source(source[position:]))
        rendered_blocks.append("".join(output))

    separator = " \\\\\n" if include_equation_alignment else "\n"
    body = separator.join(rendered_blocks)
    definitions = colors.definitions()
    if include_preamble:
        return "\n".join([
            r"\documentclass{article}",
            r"\usepackage{birdtracks}",
            *definitions,
            r"\begin{document}",
            body,
            r"\end{document}",
        ])
    return "\n".join((*definitions, body)) if definitions else body


to_latex = whiteboard_latex


__all__ = ["to_latex", "whiteboard_latex"]
