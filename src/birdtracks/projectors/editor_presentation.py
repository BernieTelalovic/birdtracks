"""Presentation transfer for explicit editor provenance; no algebra rewrites."""

from collections.abc import Mapping, Sequence

from .display_graph import compile_display_graph
from .editor import EditorState
from .editor_rewrites import edges
from .layout import _node_layers, _strand_side_labels, _column_free_levels
from .projector import Projector


def replacement_positions(before: EditorState, projector: Projector, node_ids: Sequence[str],
                          geometry: Mapping[str, float] | None = None) -> dict[str, dict[str, float]]:
    """Place new objects locally and close changed automatic-column gaps.

    A new operator may share a dependency column with a surviving disjoint
    operator. Reuse that column's actual x instead of squeezing it around the
    removed node. Hidden wiring nodes do not consume visible horizontal space.
    """
    geometry = geometry or {}
    old_indices = {identity:i for i,identity in enumerate(before.node_ids)}
    old = before.presentation.get("positions", {})
    positions = {str(i):old[str(old_indices[identity])] for i,identity in enumerate(node_ids)
                 if identity in old_indices and str(old_indices[identity]) in old}
    removed = [i for i,identity in enumerate(before.node_ids) if identity not in node_ids]
    anchor = old.get(str(removed[0]), {"x":0,"y":0}) if removed else {"x":0,"y":0}
    width = float(geometry.get("node_width", 1))
    gap = float(geometry.get("step", 1))
    stride = max(float(geometry.get("layer_step", 2)), width + gap)
    spacing = float(geometry.get("level_spacing", 1))
    introduced = [i for i,identity in enumerate(node_ids) if identity not in old_indices]
    columns = compile_display_graph(projector).operator_columns
    visible = {i for members in columns for i in members}
    local = [c for c,members in enumerate(columns) if set(members) & set(introduced)]
    fixed = {c:min((positions[str(i)]["x"] for i in members if str(i) in positions),
                   key=lambda x:(abs(x-anchor["x"]),x))
             for c,members in enumerate(columns) if any(str(i) in positions for i in members)}
    xs = {}
    for c in local:
        left = max((other for other in fixed if other < c),default=None)
        right = min((other for other in fixed if other > c),default=None)
        if c in fixed:
            xs[c] = fixed[c]
        elif left is not None and right is not None and (fixed[right]-fixed[left])/(right-left) > width+gap*0.1:
            # Fit between fixed neighbours only when the BOXES also fit.
            xs[c] = fixed[left]+(fixed[right]-fixed[left])*(c-left)/(right-left)
        elif fixed:
            nearest = min(fixed,key=lambda other:(abs(c-other),other))
            xs[c] = fixed[nearest] + (c-nearest)*stride
        else:
            xs[c] = anchor["x"] + (local.index(c)-(len(local)-1)/2)*stride
    if local and not fixed:
        shift = max(0, float(geometry.get("left_boundary",0))+width/2+gap-min(xs.values()))
        xs = {c:x+shift for c,x in xs.items()}
    for i in introduced:
        column = next((c for c,members in enumerate(columns) if i in members),None)
        y = anchor["y"]
        if removed:
            order = before.projector.port_orders[removed[0]]["input"]
            ranks = [order.index(label) for label in projector.nodes[i].support if label in order]
            if ranks:
                y += (min(ranks)+(len(projector.nodes[i].support)-len(order))/2)*spacing
        x = xs.get(column,anchor["x"])
        if column is not None:
            padding = float(geometry.get("operator_padding",0.45))
            height = (len(projector.nodes[i].support)-1)*spacing/2+padding
            obstacles = [(p["x"],p["y"],(len(projector.nodes[int(j)].support)-1)*spacing/2+padding)
                         for j,p in positions.items() if int(j) in visible]
            def clear(candidate: float) -> bool:
                return all(abs(candidate-ox) >= width+gap*0.1 or abs(y-oy) >= height+oh
                           for ox,oy,oh in obstacles)
            if not clear(x):
                candidates = [ox+direction*stride for ox,_,_ in obstacles for direction in (-1,1)]
                candidates.append(max(float(geometry.get("left_boundary",0))+width/2+gap,
                                      max((ox for ox,_,_ in obstacles),default=x)+stride))
                x = min((candidate for candidate in candidates
                         if candidate >= float(geometry.get("left_boundary",0))+width/2+gap and clear(candidate)),
                        key=lambda candidate:(abs(candidate-x),candidate))
        positions[str(i)] = {"x":x,"y":y}
    return _compact_automatic_columns(before, projector, node_ids, positions, geometry)


def _compact_automatic_columns(before: EditorState, projector: Projector, node_ids: Sequence[str],
                               positions: dict[str, dict[str, float]], geometry: Mapping[str, float]) -> dict[str, dict[str, float]]:
    """Close only changed automatic columns; manual anchors and y stay fixed.

    Automatic placement is explicit persisted metadata, not an inference from
    algebraic equality. Unknown/legacy coordinates are conservatively pinned.
    """
    old_indices = {identity: i for i, identity in enumerate(before.node_ids)}
    automatic = before.presentation.get("automatic_positions", {})
    old_positions = before.presentation.get("positions", {})
    old_columns = compile_display_graph(before.projector).operator_columns
    columns = compile_display_graph(projector).operator_columns
    if (any(str(i) not in old_positions for members in old_columns for i in members)
            or any(str(i) not in positions for members in columns for i in members)):
        return positions
    old_xs = [max(old_positions[str(i)]["x"] for i in members) for members in old_columns]
    if any(right <= left for left, right in zip(old_xs, old_xs[1:])):
        # Manually staggered/reversed columns are not a request to Tidy. Keep
        # that drawing and the collision-aware local placement intact.
        return positions
    old_members = {before.node_ids[i]: (column, frozenset(before.node_ids[j] for j in members))
                   for column, members in enumerate(old_columns) for i in members}
    width = float(geometry.get("node_width", geometry.get("operator_width", 1)))
    gap = float(geometry.get("step", 1))
    previous = float(geometry.get("left_boundary", 0)) - width / 2
    def is_automatic(i: int) -> bool:
        identity = node_ids[i]
        return (identity not in old_indices or
                str(old_indices[identity]) in automatic and
                automatic[str(old_indices[identity])] == old_positions.get(str(old_indices[identity])))
    for column, members in enumerate(columns):
        identities = frozenset(node_ids[i] for i in members)
        changed = any(old_members.get(node_ids[i]) != (column, identities) for i in members)
        movable = [i for i in members if is_automatic(i)]
        pinned = [i for i in members if i not in movable]
        if changed and movable:
            x = min(positions[str(i)]["x"] for i in pinned) if pinned else previous + width + gap
            # Logical disjointness does not imply physical separation after a
            # manual vertical move. Do not undo the collision-aware placement.
            padding = float(geometry.get("operator_padding", 0.45))
            spacing = float(geometry.get("level_spacing", 1))
            def height(i):
                return (len(projector.nodes[i].support) - 1) * spacing / 2 + padding
            if any(abs(x - (x if j in movable else positions[str(j)]["x"])) < width
                   and abs(positions[str(i)]["y"] - positions[str(j)]["y"]) < height(i) + height(j)
                   for i in movable for j in members if i != j):
                previous = max(positions[str(i)]["x"] for i in members)
                continue
            # Do not force standard spacing through an existing manual anchor.
            # The local placement above already fitted boxes between pins.
            right_pin = next(((c, min(positions[str(i)]["x"] for i in group if not is_automatic(i)))
                              for c, group in enumerate(columns) if c > column
                              and any(not is_automatic(i) for i in group)), None)
            if not pinned and right_pin is not None and right_pin[1] < x + (right_pin[0] - column) * (width + gap):
                previous = max(positions[str(i)]["x"] for i in members)
                continue
            for i in movable:
                positions[str(i)] = {**positions[str(i)], "x": x}
        previous = max(positions[str(i)]["x"] for i in members)
    return positions


def rewrite_colors(before: EditorState, after: EditorState) -> dict[str, str]:
    """Carry visible paint by surviving stable endpoints, including hidden wires."""
    def key(endpoint, state):
        if endpoint.node is None:
            side = "right" if endpoint.kind == "right_boundary" else "left"
            order = state.presentation.get("boundary_orders",{}).get("input" if side == "right" else "output",sorted(state.projector.support))
            return f"{side}-anchor:{order.index(endpoint.label)}"
        side = "input" if endpoint.kind == "operator_input" else "output"
        return f"{side}:{endpoint.node}:{endpoint.label}"
    def identity(endpoint, state):
        return (endpoint.kind, state.node_ids[endpoint.node] if endpoint.node is not None else None, endpoint.label)
    old = compile_display_graph(before.projector)
    new = compile_display_graph(after.projector)
    survivors = set(before.node_ids) & set(after.node_ids)
    colors = before.presentation.get("line_colors", {})
    result = {}
    for strand in old.strands:
        color = colors.get(f"{key(strand.source,before)}->{key(strand.target,before)}", colors.get(f"strand:{strand.strand_label}"))
        if not color:
            continue
        anchors = [(side, identity(endpoint,before)) for side, endpoint in
                   (("source",strand.source),("target",strand.target))
                   if endpoint.node is None or before.node_ids[endpoint.node] in survivors]
        for descendant in new.strands:
            if anchors and all(identity(getattr(descendant,side),after) == anchor for side, anchor in anchors):
                result[f"{key(descendant.source,after)}->{key(descendant.target,after)}"] = color
    # Reconnection preserves concrete wire identity even when BOTH visible
    # endpoints no longer match. Do not infer identity from their new order.
    def concrete(edge, state):
        kind,a,b = edge
        def port(p, side):
            return f"{side}:{p.node}:{p.label}"
        if kind == "connection":
            return f"{port(a,'output')}->{port(b,'input')}"
        order = state.presentation.get("boundary_orders",{}).get(kind,sorted(state.projector.support))
        return (f"right-anchor:{order.index(a)}->{port(b,'input')}" if kind == "input"
                else f"{port(b,'output')}->left-anchor:{order.index(a)}")
    old_visible = {f"{key(s.source,before)}->{key(s.target,before)}" for s in old.strands}
    new_visible = {f"{key(s.source,after)}->{key(s.target,after)}" for s in new.strands}
    inherited = {identity:(concrete(edge,before),colors.get(concrete(edge,before)))
                 for identity,edge in zip(before.strand_ids,edges(before.projector),strict=True)}
    for identity,edge in zip(after.strand_ids,edges(after.projector),strict=True):
        previous,color = inherited.get(identity,(None,None))
        new_key = concrete(edge,after)
        if color and (new_key in new_visible or previous not in old_visible):
            result[new_key] = color
    return result


def rewrite_routes(before: EditorState, after: EditorState, geometry=None) -> dict[str, dict[str, float]]:
    """Retain valid concrete controls; discard only segments outside new spans."""
    p = before.projector
    input_strands, output_strands = _strand_side_labels(p, tuple(sorted(p.input_boundary.items())))
    legacy = before.presentation.get("free_levels", {})
    routes = dict(before.presentation.get("strand_routes", {}))
    for identity, edge in zip(before.strand_ids, edges(p), strict=True):
        kind,a,b = edge
        label = output_strands.get(a, a.label) if kind == "connection" else a
        routes.setdefault(identity, {layer:levels[str(label)] for layer,levels in legacy.items() if str(label) in levels})
    layers = _node_layers(after.projector)
    columns = compile_display_graph(after.projector).operator_columns
    after_strands,_ = _strand_side_labels(after.projector,tuple(sorted(after.projector.input_boundary.items())))
    defaults = (_column_free_levels(after.projector,after.presentation["positions"],after_strands,
                                   sorted(after.projector.support),geometry) if geometry else {})
    blocked = {}
    if geometry:
        for column,members in enumerate(columns):
            occupied = set()
            for i in members:
                count = len(after.projector.nodes[i].support)
                start = round((after.presentation["positions"][str(i)]["y"]-geometry["top_line_level"])/geometry["level_spacing"]-(count-1)/2)
                occupied.update(range(start,start+count))
            for i in members:
                blocked[str(layers[i])] = (column,occupied)
    result = {}
    for identity, (kind,a,b) in zip(after.strand_ids, edges(after.projector), strict=True):
        if identity not in routes:
            continue
        source = len(after.projector.layers) if kind == "input" else layers[a.node] if kind == "connection" else layers[b.node]
        target = -1 if kind == "output" else layers[b.node]
        controls = {layer:level for layer,level in routes[identity].items() if target < int(layer) < source}
        for layer,level in controls.items():
            if layer in blocked and level in blocked[layer][1]:
                column,occupied = blocked[layer]
                available = set(defaults[str(column)].values()) - occupied
                if available:
                    controls[layer] = min(available,key=lambda v:(abs(v-level),v))
        result[identity] = controls
    return result


def column_routes(state: EditorState, geometry) -> dict[str, dict[str, float]]:
    """Project default corridors against committed positions, not fresh layout."""
    strands,_ = _strand_side_labels(state.projector,tuple(sorted(state.projector.input_boundary.items())))
    drawing = state.presentation
    result = _column_free_levels(state.projector,drawing["positions"],strands,
                                sorted(state.projector.support),geometry)
    layers = _node_layers(state.projector)
    for column,members in enumerate(compile_display_graph(state.projector).operator_columns):
        occupied = set()
        for i in members:
            count = len(state.projector.nodes[i].support)
            start = round((drawing["positions"][str(i)]["y"]-geometry["top_line_level"])/geometry["level_spacing"]-(count-1)/2)
            occupied.update(range(start,start+count))
        previous = drawing.get("free_levels",{}).get(str(layers[members[0]]),{})
        for label in result[str(column)]:
            if label in previous and previous[label] not in occupied:
                result[str(column)][label] = previous[label]
    return result
