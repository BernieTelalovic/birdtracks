"""Local, exact editor rewrites and explicit provenance (no solver or layout).

Object identity is scoped by occurrence: (term_id, object_id). A branching
rewrite copies survivor IDs into each new occurrence, not canonical graph IDs.
"""

from __future__ import annotations

from dataclasses import replace
from collections.abc import Iterable, Mapping, Sequence
from fractions import Fraction
from uuid import uuid4

from .editor import EditorState, _presentation
from .projector import Connection, NodePort, Projector

Edge = tuple[str, NodePort | int, NodePort]


def boundary_permutation(projector: Projector):
    """Linear graph traversal of a completely expanded term, never expansion."""
    from .permutation_node import PermutationNode
    from .collapse import _term_topology
    from birdtracks.permutations import Permutation

    if not projector.nodes or not all(isinstance(n,PermutationNode) for n in projector.nodes):
        return None
    mapping,loops = _term_topology(projector,tuple(n.permutation for n in projector.nodes),
                                   {c.source:c.target for c in projector.connections},
                                   {p:label for label,p in projector.output_boundary.items()})
    return None if loops else (Permutation(mapping),projector.canonical_coefficient)


def expression_value(projectors: Iterable[Projector]):
    """Derive a canonical rational aggregate without altering editor drawings.

    Only fully expanded, loop-free wiring is reduced to its boundary
    permutation. Mixed/unexpanded operators never enter a collapse fallback.
    """
    from .permutation_node import PermutationNode
    from .projector_sum import ProjectorSum

    terms = []
    for p in projectors:
        boundary = boundary_permutation(p)
        if boundary is None:
            terms.append(p)
        else:
            permutation,scalar = boundary
            terms.append(Projector([PermutationNode(permutation,support=p.support)],coefficient=scalar,
                                   in_direction=p.in_direction,out_direction=p.out_direction))
    return ProjectorSum(terms)


def edges(projector: Projector) -> tuple[Edge, ...]:
    """Persistence order for concrete strands, independent of display corridors."""
    return (
        *(("connection", c.source, c.target) for c in projector.connections),
        *(("input", label, port) for label, port in sorted(projector.input_boundary.items())),
        *(("output", label, port) for label, port in sorted(projector.output_boundary.items())),
    )


def _port_key(port: NodePort, node_ids: Sequence[str]) -> tuple[str, int]:
    return (node_ids[port.node], port.label)


def edge_key(edge: Edge, node_ids: Sequence[str]) -> tuple[object, ...]:
    kind, source, target = edge
    if kind == "connection":
        return kind, _port_key(source, node_ids), _port_key(target, node_ids)
    return kind, source, _port_key(target, node_ids)


def transition(before: EditorState, projector: Projector, node_ids: Sequence[str], *,
               port_map: Mapping[tuple[str, NodePort], NodePort] | None = None, branch: bool = False,
               geometry: Mapping[str, float] | None = None, strand_ids: Sequence[str] | None = None) -> EditorState:
    """Transfer survivors and manual anchors; place changed automatic columns.

    port_map maps removed old ports to replacement boundary ports. It is known
    by the splice, never inferred by matching equal/canonicalized operators.
    """
    port_map = port_map or {}
    new_indices = {identity: i for i, identity in enumerate(node_ids)}
    def mapped(port, side):
        if (side, port) in port_map:
            return port_map[side, port]
        identity = before.node_ids[port.node]
        return NodePort(new_indices[identity], port.label) if identity in new_indices else None
    inherited = {}
    for edge, identity in zip(edges(before.projector), before.strand_ids, strict=True):
        kind, a, b = edge
        if kind == "connection":
            a, b = mapped(a, "output"), mapped(b, "input")
        else:
            b = mapped(b, kind)
        if a is not None and b is not None:
            inherited[edge_key((kind, a, b), node_ids)] = identity
    strand_ids = strand_ids or tuple(inherited.get(edge_key(edge, node_ids), uuid4().hex)
                                    for edge in edges(projector))
    presentation = before.presentation
    from .editor_presentation import replacement_positions

    presentation["positions"] = replacement_positions(before,projector,node_ids,geometry)
    old_automatic = before.presentation.get("automatic_positions", {})
    old_positions = before.presentation.get("positions", {})
    old_indices = {identity: i for i, identity in enumerate(before.node_ids)}
    presentation["automatic_positions"] = {
        str(i): presentation["positions"][str(i)] for i, identity in enumerate(node_ids)
        if identity not in old_indices or (str(old_indices[identity]) in old_automatic
            and old_automatic[str(old_indices[identity])] == old_positions.get(str(old_indices[identity])))
    }
    candidate = replace(before, projector=projector, node_ids=tuple(node_ids), strand_ids=strand_ids,
                   term_id=uuid4().hex if branch else before.term_id,
                   presentation_json=_presentation(projector, presentation),
                   selection=tuple(i for i in before.selection if i in (*node_ids, *strand_ids)),
                   revision=0 if branch else before.revision)
    from .editor_presentation import rewrite_colors, rewrite_routes

    presentation["line_colors"] = rewrite_colors(before, candidate)
    presentation["strand_routes"] = rewrite_routes(before, candidate, geometry)
    return replace(candidate, presentation_json=_presentation(projector, presentation))


def replace_node(before: EditorState, node_id: str, replacement: Projector, *,
                 geometry: Mapping[str, float] | None = None, branch: bool = False) -> EditorState:
    """Splice an exact same-boundary subgraph for one selected operator.

    The replacement is interpreted in the selected operator's canonical local
    label convention. Outer scalar and removed orientation are absorbed once.
    """
    from .simplification import _substitute_node
    if node_id not in before.node_ids:
        raise ValueError("replacement references an unknown node")
    index = before.node_ids.index(node_id)
    if not isinstance(replacement, Projector) or not replacement.nodes:
        raise ValueError("replacement must be a nonempty Projector")
    unit = _substitute_node(before.projector, index, replacement)
    coefficient = (before.projector.canonical_coefficient * replacement.canonical_coefficient
                   / unit.canonical_coefficient)
    value = unit * coefficient
    count = len(replacement.nodes)
    node_ids = (*before.node_ids[:index], *(uuid4().hex for _ in range(count)), *before.node_ids[index+1:])
    ports = {(side, NodePort(index, label)): NodePort(index + port.node, port.label)
             for side, boundary in (("input", replacement.input_boundary), ("output", replacement.output_boundary))
             for label, port in boundary.items()}
    return transition(before, value, node_ids, port_map=ports, branch=branch, geometry=geometry)


def replace_subgraph(before: EditorState, node_ids: Sequence[str], replacement: Projector, *,
                     input_ports: Mapping[int, tuple[str, int]], output_ports: Mapping[int, tuple[str, int]],
                     geometry: Mapping[str, float] | None = None) -> EditorState:
    """Splice a selected subgraph through an explicit, bijective boundary map.

    Inputs/outputs map each replacement boundary label to (old node ID, label).
    The caller supplies the identity; validation checks its graph/domain, not a
    factorial proof of equivalence. Small collapse oracles belong in tests.
    """
    if not node_ids or len(set(node_ids)) != len(node_ids) or not set(node_ids) <= set(before.node_ids):
        raise ValueError("replacement requires distinct known node IDs")
    if not isinstance(replacement, Projector) or not replacement.nodes:
        raise ValueError("replacement requires a nonempty exact subgraph")
    selected = {before.node_ids.index(identity) for identity in node_ids}
    p = before.projector
    def cut_ports(mapping):
        if set(mapping) != replacement.support:
            raise ValueError("replacement cut labels must equal its boundary support")
        result = {}
        for label, (identity, port_label) in mapping.items():
            if identity not in node_ids:
                raise ValueError("a cut port must belong to the selected subgraph")
            port = NodePort(before.node_ids.index(identity), port_label)
            if port.label not in p.nodes[port.node].support:
                raise ValueError("unknown selected cut port")
            result[label] = port
        if len(set(result.values())) != len(result):
            raise ValueError("replacement boundary map must be bijective")
        return result
    inputs, outputs = cut_ports(input_ports), cut_ports(output_ports)
    all_ports = {NodePort(i,label) for i in selected for label in p.nodes[i].support}
    internal = [c for c in p.connections if c.source.node in selected and c.target.node in selected]
    if set(inputs.values()) != all_ports - {c.target for c in internal} or set(outputs.values()) != all_ports - {c.source for c in internal}:
        raise ValueError("replacement must cover every open cut port exactly once")
    insertion = min(selected)
    kept = [i for i in range(len(p.nodes)) if i not in selected]
    left = [i for i in kept if i < insertion]
    right = [i for i in kept if i >= insertion]
    count = len(replacement.nodes)
    remap = {old:new for new,old in enumerate(left)}
    remap.update({old:len(left)+count+i for i,old in enumerate(right)})
    def local(port):
        return NodePort(len(left)+port.node,port.label)
    port_map = {(side,old):local(boundary[label])
                for side,cuts,boundary in (("input",inputs,replacement.input_boundary),("output",outputs,replacement.output_boundary))
                for label,old in cuts.items()}
    def outer(port, side):
        return port_map[side,port] if port.node in selected else NodePort(remap[port.node],port.label)
    connections = [Connection(outer(c.source,"output"),outer(c.target,"input")) for c in p.connections if c not in internal]
    connections.extend(Connection(local(c.source),local(c.target)) for c in replacement.connections)
    orders = {remap[i]:dict(p.port_orders[i]) for i in kept}
    orders.update({len(left)+i:dict(sides) for i,sides in replacement.port_orders.items()})
    unit = Projector((*[p.nodes[i] for i in left],*replacement.nodes,*[p.nodes[i] for i in right]),connections,
                     input_boundary={label:outer(port,"input") for label,port in p.input_boundary.items()},
                     output_boundary={label:outer(port,"output") for label,port in p.output_boundary.items()},
                     port_orders=orders,in_direction=p.in_direction,out_direction=p.out_direction)
    value = unit * (p.canonical_coefficient * replacement.canonical_coefficient / unit.canonical_coefficient)
    ids = (*[before.node_ids[i] for i in left],*(uuid4().hex for _ in replacement.nodes),*[before.node_ids[i] for i in right])
    return transition(before,value,ids,port_map=port_map,geometry=geometry)


def recursive_branches(before: EditorState, node_id: str, *, side: str = "input", edge: str = "bottom",
                       geometry: Mapping[str, float] | None = None) -> tuple[EditorState, ...]:
    """Two normalized, locally absorbed branches; no collection or detangling."""
    from .simplification import _recursive_node_expansion_terms
    if node_id not in before.node_ids:
        raise ValueError("expansion references an unknown node")
    index = before.node_ids.index(node_id)
    if len(before.projector.nodes[index].support) < 2:
        raise ValueError("recursive expansion requires at least two ports")
    # This helper does not collapse even for two ports (the public solver does).
    terms = _recursive_node_expansion_terms(before.projector, index, side=side, edge=edge)
    result = []
    for unit, coefficient in terms:
        count = len(unit.nodes) - len(before.projector.nodes) + 1
        ids = (*before.node_ids[:index], *(uuid4().hex for _ in range(count)), *before.node_ids[index+1:])
        # The contextual helper exposes the inserted contiguous range. Its
        # external cut ports can be recovered from the known splice, not equality.
        incoming = {c.target.label: c.target for c in unit.connections
                    if index <= c.target.node < index + count
                    and not index <= c.source.node < index + count}
        outgoing = {c.source.label: c.source for c in unit.connections
                    if index <= c.source.node < index + count
                    and not index <= c.target.node < index + count}
        ports = {}
        for label in before.projector.nodes[index].support:
            old_port = NodePort(index, label)
            for side_name, boundary, cuts in (("input", unit.input_boundary, incoming), ("output", unit.output_boundary, outgoing)):
                candidate = cuts.get(label)
                if candidate is None:
                    old_boundary = before.projector.input_boundary if side_name == "input" else before.projector.output_boundary
                    boundary_label = next((k for k, p in old_boundary.items() if p == old_port), None)
                    candidate = boundary.get(boundary_label)
                if candidate is not None and index <= candidate.node < index + count:
                    ports[side_name, old_port] = candidate
        branch = transition(before, unit * coefficient, ids, port_map=ports, branch=True, geometry=geometry)
        result.append(absorb_nested(branch, geometry=geometry))
    return tuple(result)


def absorb_nested(before: EditorState, *, geometry: Mapping[str, float] | None = None) -> EditorState:
    """Bounded normalized P Q = P rewrites, with explicit survivor provenance.

    Each step removes one node. No collapse, detangling, or sum collection is
    involved; ordered scalar compensation stays in the algebra identity.
    """
    from birdtracks.settings import simplification_rule_enabled
    from .identities import _nested_same_type_absorption_index, _remove_operator

    if not simplification_rule_enabled("same_type_nested_absorption"):
        return before
    state = before
    while (index := _nested_same_type_absorption_index(state.projector)) is not None:
        p = state.projector
        def shifted(port):
            return NodePort(port.node - (port.node > index), port.label)
        ports = {}
        for connection in p.connections:
            if connection.source.node == index:
                ports["input", NodePort(index, connection.source.label)] = shifted(connection.target)
            if connection.target.node == index:
                ports["output", NodePort(index, connection.target.label)] = shifted(connection.source)
        ids = (*state.node_ids[:index], *state.node_ids[index + 1:])
        state = transition(state, _remove_operator(p, index), ids, port_map=ports, geometry=geometry)
    return state


def calculate_full_expansion(before: EditorState, node_id: str, *, geometry=None) -> tuple[EditorState, ...]:
    """Explicit factorial calculation, deliberately outside command processing.

    Unlike the algebra solver's expansion pipeline, keep each occurrence and
    its provenance. Hosts may offer collection as a later explicit calculation.
    """
    from .permutation_node import PermutationNode
    from .symmetrisers import Antisymmetriser, Symmetriser

    index = before.node_ids.index(node_id)
    node = before.projector.nodes[index]
    if not isinstance(node, (Symmetriser, Antisymmetriser)):
        raise ValueError("only S/A operators can be expanded")
    return tuple(replace_node(before, node_id,
                 Projector([PermutationNode(permutation, support=node.support)], coefficient=coefficient),
                 geometry=geometry, branch=True)
                 for permutation, coefficient in node.collapse().items())


def cleanup_occurrences(states: tuple[EditorState, ...], *, geometry=None) -> tuple[EditorState, ...]:
    """Bounded line cleanup, preserving the first surviving occurrence's drawing.

    Apply nested absorption, discard known zeros, and collect using a lossless
    wiring comparison projection. Never install that projection over editor
    geometry or expand mixed terms for equality. Rational and symbolic outer
    factors participate exactly once in collection.
    """
    from .wiring import permutation_wiring_normal_form
    from birdtracks.symbolic import SymbolicCoefficient

    result = []
    groups = {}
    for state in states:
        state = absorb_nested(state, geometry=geometry)
        p = state.projector
        if not p.simplify() or not state.outer_factor:
            continue
        comparison = permutation_wiring_normal_form(p)
        scalar = comparison.canonical_value_coefficient
        if not scalar or not comparison.simplify():
            continue
        key = comparison / scalar
        total = scalar * state.outer_factor
        if key not in groups:
            groups[key] = (len(result), scalar, total, state)
            result.append(state)
        else:
            index, representative_scalar, previous, representative = groups[key]
            total += previous
            groups[key] = index, representative_scalar, total, representative
            if isinstance(total, SymbolicCoefficient):
                result[index] = replace(representative, outer_factor=total / representative_scalar)
            else:
                result[index] = replace(representative, projector=representative.projector *
                                        (total / representative_scalar), outer_factor=Fraction(1))
    return tuple(s for s in result if s.projector.coefficient and s.outer_factor)


def reconnect(before: EditorState, changes: Mapping[str, Mapping[str, Mapping[str, object]]]) -> EditorState:
    """Validate concrete strand endpoint edits in Python, with no sign redraw.

    Each endpoint is a stable node ID and label, or a fixed boundary label.
    Occupied endpoints must be swapped in one transaction; partial edits fail.
    """
    if not isinstance(changes, Mapping) or not changes:
        raise ValueError("reconnection requires strand changes")
    def endpoint(raw, side):
        if set(raw) == {"boundary"}:
            label = raw["boundary"]
            if isinstance(label, bool) or label not in before.projector.support:
                raise ValueError("unknown fixed boundary label")
            return label
        if set(raw) != {"node_id", "label"} or raw["node_id"] not in before.node_ids:
            raise ValueError("unknown strand endpoint")
        port = NodePort(before.node_ids.index(raw["node_id"]), raw["label"])
        if port.label not in before.projector.nodes[port.node].support:
            raise ValueError("unknown node port label")
        return port
    requested = dict(zip(before.strand_ids, edges(before.projector), strict=True))
    for identity, change in changes.items():
        if identity not in requested or set(change) != {"source", "target"}:
            raise ValueError("unknown strand or incomplete reconnection")
        a, b = endpoint(change["source"], "output"), endpoint(change["target"], "input")
        if isinstance(a, int) and isinstance(b, NodePort):
            requested[identity] = ("input", a, b)
        elif isinstance(a, NodePort) and isinstance(b, int):
            requested[identity] = ("output", b, a)
        elif isinstance(a, NodePort) and isinstance(b, NodePort):
            # Interactive operators form a DAG. Reject traces/back edges here,
            # even though the general algebra constructor can represent traces.
            if a.node <= b.node:
                raise ValueError("connections must run right-to-left")
            requested[identity] = ("connection", a, b)
        else:
            raise ValueError("a strand cannot directly join two boundaries")
    values = tuple(requested.values())
    inputs = [(a, b) for kind, a, b in values if kind == "input"]
    outputs = [(a, b) for kind, a, b in values if kind == "output"]
    if len(dict(inputs)) != len(inputs) or len(dict(outputs)) != len(outputs):
        raise ValueError("a boundary cannot have two strands")
    p = before.projector
    value = Projector(p.nodes, [Connection(a, b) for kind, a, b in values if kind == "connection"],
                      coefficient=p.coefficient, input_boundary=dict(inputs), output_boundary=dict(outputs),
                      port_orders=p.port_orders, in_direction=p.in_direction, out_direction=p.out_direction)
    identities = {edge_key(edge, before.node_ids): identity for identity, edge in requested.items()}
    return transition(before, value, before.node_ids,
                      strand_ids=tuple(identities[edge_key(e, before.node_ids)] for e in edges(value)))
