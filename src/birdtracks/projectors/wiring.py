"""Bounded algebraic comparison of permutation wiring, independent of drawing."""

from .permutation_node import PermutationNode
from .projector import Connection, NodePort, Projector
from birdtracks.permutations import Permutation


def permutation_wiring_normal_form(projector: Projector) -> Projector:
    """Trace permutation corridors into operator ports and fixed boundaries.

    This lossless comparison projection never expands an S/A. Port orientation
    remains in the exact scalar, and graph canonicalization accounts for the
    resulting antisymmetric wiring parity. It is not an editor replacement:
    IDs, manual placement, and the first representative's drawing remain owned
    by the caller. Closed permutation-only loops conservatively retain their
    original graph, since they carry dimension factors.
    """
    if not isinstance(projector, Projector):
        raise TypeError("permutation wiring requires a Projector")
    permutations = {i for i, n in enumerate(projector.nodes) if isinstance(n, PermutationNode)}
    if not permutations:
        return projector
    kept = [i for i in range(len(projector.nodes)) if i not in permutations]
    remap = {old: new for new, old in enumerate(kept)}
    next_port = {c.source: c.target for c in projector.connections}
    output_labels = {port: label for label, port in projector.output_boundary.items()}
    visited: set[NodePort] = set()

    def trace(start: NodePort) -> NodePort | int | None:
        current = start
        path: set[NodePort] = set()
        while current.node in permutations:
            if current in path:
                return None
            path.add(current)
            visited.add(current)
            node = projector.nodes[current.node]
            output = NodePort(current.node, node.permutation(current.label))
            target = next_port.get(output)
            if target is None:
                return output_labels[output]
            current = target
        return NodePort(remap[current.node], current.label)

    connections: list[Connection] = []
    inputs: dict[int, NodePort] = {}
    outputs: dict[int, NodePort] = {}
    free: dict[int, int] = {}
    for label, port in projector.input_boundary.items():
        target = trace(port)
        if target is None:
            return projector
        if isinstance(target, NodePort):
            inputs[label] = target
        else:
            free[label] = target
    for index in kept:
        for label in projector.nodes[index].support:
            old = NodePort(index, label)
            source = NodePort(remap[index], label)
            if old not in next_port:
                outputs[output_labels[old]] = source
                continue
            target = trace(next_port[old])
            if target is None:
                return projector
            if isinstance(target, NodePort):
                connections.append(Connection(source, target))
            else:
                outputs[target] = source
    if visited != {NodePort(i, label) for i in permutations for label in projector.nodes[i].support}:
        return projector  # A detached permutation trace was not traversed.
    nodes = [projector.nodes[i] for i in kept]
    orders = {remap[i]: dict(projector.port_orders[i]) for i in kept}
    if free:
        index = len(nodes)
        nodes.append(PermutationNode(Permutation.identity(), support=sorted(free)))
        orders[index] = {side: tuple(sorted(free)) for side in ("input", "output")}
        for label, target in free.items():
            inputs[label] = NodePort(index, label)
            outputs[target] = NodePort(index, label)
    unit = Projector(nodes, connections, input_boundary=inputs, output_boundary=outputs,
                     port_orders=orders, in_direction=projector.in_direction,
                     out_direction=projector.out_direction)
    return unit * (projector.canonical_coefficient / unit.canonical_coefficient)
