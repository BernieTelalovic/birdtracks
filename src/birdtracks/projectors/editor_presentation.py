"""Presentation transfer for explicit editor provenance; no algebra rewrites."""

from .display_graph import compile_display_graph
from .editor import EditorState
from .editor_rewrites import edges
from .layout import _node_layers, _strand_side_labels, _column_free_levels


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
