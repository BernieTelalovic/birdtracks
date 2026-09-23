"""Deterministic LaTeX export for the live whiteboard presentation state.

This module intentionally consumes widget state rather than algebra objects.
The browser renderer and this exporter therefore share the same source text,
saved layout, endpoint colour keys, and Young-cell drawing coordinates.  It is
also usable with a plain mapping, which keeps the exporter independent of the
optional anywidget dependency.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
    if start > 0 and re.match(r"[A-Za-z0-9_./^]", prefix[start - 1]):
        return None
    return start, match.group(0)


class _ColorRegistry:
    """Give CSS colours stable xcolor names."""

    def __init__(self) -> None:
        self._names: dict[str, str] = {}

    def use(self, value: object, default: str = "black") -> str:
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
) -> str:
    cells = _young_cells(term)
    barred = term.get("barred", [])
    unbarred = term.get("unbarred", [])
    rows = max(1, len(barred) + len(unbarred))
    body: list[str] = [
        rf"\draw[dashed,draw={colors.use('#94a3b8')},line width=.35pt] "
        rf"(0,.5) -- (0,-{_fmt(rows - .5)});"
    ]
    for cell in cells:
        x = _number(cell.get("column"))
        y = _number(cell.get("row"))
        style = _cell_style(styles, term_index, cell)
        options = _style_options(
            style, colors, default_fill="white", default_draw="#17202a",
            default_width=1.3,
        )
        body.append(
            rf"\path[{', '.join(options)}] "
            rf"({_fmt(x)},{_fmt(-y)}) rectangle ({_fmt(x + 1)},{_fmt(-y - 1)});"
        )
        label = next(
            (
                item for item in term.get("labels", [])
                if isinstance(item, Mapping)
                and item.get("side") == cell.get("side")
                and item.get("row") == (
                    len(unbarred) + len(barred) - 1 - int(cell.get("row", 0))
                    if cell.get("side") == "barred" else cell.get("row")
                )
                and item.get("column") == (
                    -1 - int(cell.get("column", 0))
                    if cell.get("side") == "barred" else cell.get("column")
                )
            ),
            None,
        )
        if label is not None:
            text_color = _option_value(label, "text_color", "color")
            label_options = ["inner sep=0pt", "anchor=center"]
            if text_color is not None:
                label_options.append(f"text={colors.use(text_color)}")
            body.append(
                rf"\node[{', '.join(label_options)}] at "
                rf"({_fmt(x + .5)},{_fmt(-y - .5)}) "
                rf"{{\ensuremath{{{_tex_text(label.get('value', ''))}}}}};"
            )
            if cell.get("side") == "barred":
                body.append(
                    rf"\draw[draw={colors.use(_option_value(label, 'text_color', 'color') or '#17202a')},"
                    rf"line width=.9pt] ({_fmt(x + .18)},{_fmt(-y - .18)}) -- "
                    rf"({_fmt(x + .82)},{_fmt(-y - .18)});"
                )
        elif cell.get("side") == "barred":
            body.append(
                rf"\fill[{colors.use('#17202a')}] ({_fmt(x + .5)},{_fmt(-y - .5)}) circle (.1);"
            )
    # The coefficient is intentionally part of the pair fragment.  The
    # whiteboard renderer hides a numeric prefix before a \pair marker for the
    # same reason: it belongs to the editable pair term.
    coefficient = str(term.get("coefficient", "1"))
    n0 = str(term.get("n0", "0"))
    prefactor = rf"\mathord{{{_tex_text(coefficient)}_{{{_tex_text(n0)}}}}}\,"
    return prefactor + _picture(body, scale="1.15em")


def _pair_latex(
    pair_widget: object, colors: _ColorRegistry, styles: Mapping[str, object]
) -> str:
    expression = _get(pair_widget, "pair_expression", pair_widget)
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
                result.append(_pair_term_latex(term, index - 1, styles, colors))
        elif token == "sum":
            result.append(r"\mathbin{\oplus}")
        elif token == "tensor":
            result.append(r"\mathbin{\otimes}")
        elif token == "(":
            result.append(r"\left(")
        elif token == ")":
            result.append(r"\right)")
    return " ".join(result)


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

    def _x_for_layer(self, layer: int) -> float:
        return self._geometry("first_layer_x", 0) + layer * self._geometry("layer_step", 1)

    def _x_for_node(self, node: Mapping[str, object]) -> float:
        if not self.compiled:
            return self._x_for_layer(int(node.get("layer", 0)))
        column = self._display_column(int(node["index"]))
        widths = self.graph.get("display", {}).get("corridor_widths", [])
        widths = widths if isinstance(widths, list) else []
        x = self._geometry("left_boundary", 0) + _number(widths[0] if widths else None, self._geometry("step", 1))
        x += self._geometry("node_width", self._geometry("operator_width", 1)) / 2
        for index in range(1, column + 1):
            x += self._geometry("node_width", self._geometry("operator_width", 1))
            x += _number(widths[index] if index < len(widths) else None, self._geometry("step", 1))
        return x

    def _node_width(self) -> float:
        return self._geometry("node_width", self._geometry("operator_width", 1))

    def _y(self, level: float) -> float:
        return self._geometry("top_margin", 0) + level * self._geometry("level_spacing", 1)

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

    def _coordinate(self, endpoint: _Endpoint) -> tuple[float, float]:
        width = self._node_width()
        if endpoint.kind == "right-anchor":
            return self._right_boundary(), self._y(endpoint.level or 0)
        if endpoint.kind == "left-anchor":
            return self._geometry("left_boundary", 0), self._y(endpoint.level or 0)
        node = self.nodes[endpoint.node or 0]
        order = node["input_order"] if endpoint.side == "input" else node["output_order"]
        row = list(order).index(endpoint.label)
        centre = self._x_for_node(node)
        return (
            centre + (width / 2 if endpoint.side == "input" else -width / 2),
            self._y(int(node["level"]) + row),
        )

    def _endpoint_layer(self, endpoint: _Endpoint) -> int:
        if endpoint.kind == "right-anchor":
            return self.layers
        if endpoint.kind == "left-anchor":
            return -1
        return int(self.nodes[endpoint.node or 0].get("layer", 0))

    def _right_boundary(self) -> float:
        if self.compiled and "right_boundary" in self.geometry:
            return self._geometry("right_boundary", 0)
        return (
            self._geometry("first_layer_x", 0)
            + (self.layers - 1) * self._geometry("layer_step", 1)
            + self._geometry("step", 1)
        )

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

    def _route_level(self, source: _Endpoint, target: _Endpoint, label: object, layer: int) -> int:
        assignments = self.free_levels.get(str(layer), {})
        if isinstance(assignments, Mapping) and label is not None:
            assigned = assignments.get(str(label))
            if assigned is not None:
                return int(assigned)
        start = self._coordinate(source)
        end = self._coordinate(target)
        start_layer = self._endpoint_layer(source)
        end_layer = self._endpoint_layer(target)
        fraction = (start_layer - layer) / (start_layer - end_layer) if start_layer != end_layer else 0
        level = round((start[1] + (end[1] - start[1]) * fraction - self._geometry("top_margin", 0)) / self._geometry("level_spacing", 1))
        return max(0, min(self._level_count() - 1, level))

    def _route_points(self, source: _Endpoint, target: _Endpoint, label: object) -> list[tuple[float, float]]:
        points = [self._coordinate(source)]
        for layer in range(self._endpoint_layer(source) - 1, self._endpoint_layer(target), -1):
            x = self._x_for_layer(layer)
            y = self._y(self._route_level(source, target, label, layer))
            points.extend(((x + self._node_width() / 2, y), (x - self._node_width() / 2, y)))
        points.append(self._coordinate(target))
        return points

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

    def _line_options(self, key: str, legacy: str | None = None) -> list[str]:
        raw = self.line_colors.get(key)
        if raw is None and legacy:
            raw = self.line_colors.get(legacy)
        style = raw if isinstance(raw, Mapping) else {"color": raw} if raw else {}
        if not isinstance(style, Mapping):
            style = {}
        default = self.geometry.get("line_color", "black")
        options = _style_options(
            style, self.colors, default_fill="none", default_draw=default,
            default_width=self.geometry.get("line_width", 1), include_fill=False,
        )
        options.append("line cap=round")
        return options

    def _compiled_points(self, strand: Mapping[str, object]) -> list[tuple[float, float]]:
        source_raw = strand.get("source", {})
        target_raw = strand.get("target", {})
        if not isinstance(source_raw, Mapping) or not isinstance(target_raw, Mapping):
            return []
        source = self._display_endpoint(source_raw)
        target = self._display_endpoint(target_raw)
        start = self._coordinate(source)
        end = self._coordinate(target)
        if source.kind == "port":
            start = (start[0] + (self._node_width() * .025 if source.side == "output" else -self._node_width() * .025), start[1])
        if target.kind == "port":
            end = (end[0] + (self._node_width() * .025 if target.side == "input" else -self._node_width() * .025), end[1])
        source_column = len(self.columns) if source.kind == "right-anchor" else self._display_column(source.node or 0)
        target_column = -1 if target.kind == "left-anchor" else self._display_column(target.node or 0)
        points = [start]
        label = strand.get("strand_label")
        for column in range(source_column - 1, target_column, -1):
            node_indices = self.columns[column]
            if not node_indices:
                continue
            node = self.nodes[node_indices[0]]
            layer = int(node.get("layer", 0))
            assignments = self.free_levels.get(str(layer), {})
            assigned = assignments.get(str(label)) if isinstance(assignments, Mapping) else None
            fraction = (source_column - column) / (source_column - target_column)
            requested = round((start[1] + (end[1] - start[1]) * fraction - self._geometry("top_margin", 0)) / self._geometry("level_spacing", 1)) if assigned is None else int(assigned)
            occupied = {
                int(self.nodes[index].get("level", 0)) + offset
                for index in node_indices
                for offset in range(len(self.nodes[index].get("labels", [])))
            }
            level = requested
            if level in occupied:
                for distance in range(1, self._level_count()):
                    if requested + distance < self._level_count() and requested + distance not in occupied:
                        level = requested + distance
                        break
                    if requested - distance >= 0 and requested - distance not in occupied:
                        level = requested - distance
                        break
            x = self._x_for_node(node)
            y = self._y(level)
            points.extend(((x + self._node_width() / 2, y), (x - self._node_width() / 2, y)))
        points.append(end)
        return points

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

    def _arrow(self, start: tuple[float, float], end: tuple[float, float], options: list[str]) -> str:
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        if length == 0:
            return ""
        tx, ty = dx / length, dy / length
        px, py = -ty, tx
        x, y = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
        size = min(self._node_width(), self._geometry("level_spacing", 1)) * .10
        direction = -1 if self.graph.get("in_direction") == "left" else 1
        tip = (x + direction * tx * size, y + direction * ty * size)
        back = (x - direction * tx * size * .8, y - direction * ty * size * .8)
        spread = size * .7
        return (
            rf"\draw[{', '.join(options)}] "
            rf"({_fmt(back[0] + px * spread)},{_fmt(back[1] + py * spread)}) -- "
            rf"({_fmt(tip[0])},{_fmt(tip[1])}) -- "
            rf"({_fmt(back[0] - px * spread)},{_fmt(back[1] - py * spread)});"
        )

    def _arrow_options(self) -> list[str]:
        return [
            f"draw={self.colors.use('black')}",
            f"line width={_length_option(self.geometry.get('line_width', 1))}",
            "line cap=round",
            "line join=round",
        ]

    def render(self) -> str:
        body: list[str] = []
        direction = self.graph.get("in_direction")
        arrows = direction in {"left", "right"}
        if self.compiled:
            display = self.graph.get("display", {})
            strands = display.get("strands", []) if isinstance(display, Mapping) else []
            if isinstance(strands, list):
                for strand in strands:
                    if not isinstance(strand, Mapping):
                        continue
                    source_raw, target_raw = strand.get("source", {}), strand.get("target", {})
                    if not isinstance(source_raw, Mapping) or not isinstance(target_raw, Mapping):
                        continue
                    source, target = self._display_endpoint(source_raw), self._display_endpoint(target_raw)
                    key = f"{self._endpoint_key(source)}->{self._endpoint_key(target)}"
                    legacy = f"strand:{strand.get('strand_label')}"
                    options = self._line_options(key, legacy)
                    points = self._compiled_points(strand)
                    if points:
                        body.append(rf"\draw[{', '.join(options)}] {_tikz_path(points)};")
                        if arrows and source.kind == "right-anchor" and len(points) > 1:
                            body.append(self._arrow(points[0], points[1], self._arrow_options()))
                        if arrows and target.kind == "left-anchor" and len(points) > 1:
                            body.append(self._arrow(points[-2], points[-1], self._arrow_options()))
        else:
            for source, target, label in self._connections():
                key = f"{self._endpoint_key(source)}->{self._endpoint_key(target)}"
                legacy = f"strand:{label}" if label is not None else None
                options = self._line_options(key, legacy)
                points = self._route_points(source, target, label)
                body.append(rf"\draw[{', '.join(options)}] {_tikz_path(points)};")
                if arrows and source.kind == "right-anchor" and len(points) > 1:
                    body.append(self._arrow(points[0], points[1], self._arrow_options()))
                if arrows and target.kind == "left-anchor" and len(points) > 1:
                    body.append(self._arrow(points[-2], points[-1], self._arrow_options()))

        visible = set(index for column in self.columns for index in column) if self.compiled else set(self.nodes)
        line_color = self.colors.use(self.geometry.get("line_color", "black"))
        for index, node in self.nodes.items():
            if index not in visible:
                continue
            centre = self._x_for_node(node)
            width = self._node_width()
            labels = list(node.get("labels", []))
            top = self._y(int(node.get("level", 0))) - self._geometry("operator_padding", .45)
            height = max(1, len(labels) - 1) * self._geometry("level_spacing", 1) + 2 * self._geometry("operator_padding", .45)
            if node.get("kind") == "permutation" and node.get("mapping"):
                input_order, output_order = node["input_order"], node["output_order"]
                for mapping in node["mapping"]:
                    if not isinstance(mapping, list) or len(mapping) != 2:
                        continue
                    start = (centre + width / 2, self._y(int(node["level"]) + list(input_order).index(mapping[0])))
                    end = (centre - width / 2, self._y(int(node["level"]) + list(output_order).index(mapping[1])))
                    middle = (start[0] + end[0]) / 2
                    body.append(
                        rf"\draw[draw={line_color},line width={_length_option(self.geometry.get('line_width', 1))},line cap=round] "
                        rf"({_fmt(start[0])},{_fmt(start[1])}) .. controls "
                        rf"({_fmt(middle)},{_fmt(start[1])}) and ({_fmt(middle)},{_fmt(end[1])}) .. "
                        rf"({_fmt(end[0])},{_fmt(end[1])});"
                    )
                continue
            kind = node.get("kind")
            fill = self.geometry.get("antisymmetriser_color", "black") if kind == "antisymmetriser" else self.geometry.get("symmetriser_color", "white")
            body.append(
                rf"\path[fill={self.colors.use(fill)},draw={line_color},line width={_length_option(self.geometry.get('operator_line_width', 1))}] "
                rf"({_fmt(centre - width / 2)},{_fmt(top)}) rectangle "
                rf"({_fmt(centre + width / 2)},{_fmt(top + height)});"
            )
        return _picture(body, scale="1em")


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
    colors = _ColorRegistry()
    rendered_blocks: list[str] = []

    for block in blocks:
        if not isinstance(block, Mapping):
            continue
        source = str(block.get("source", ""))
        block_id = str(block.get("id", ""))
        calculation_svg = block.get("calculation_svg")
        if isinstance(calculation_svg, str) and calculation_svg:
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
            replacements.append((start, match.end(), _pair_latex(child, colors, styles)))
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
            output.append(source[position:start])
            output.append(replacement)
            position = end
        output.append(source[position:])
        rendered_blocks.append("".join(output))

    body = "\n".join(rendered_blocks)
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
