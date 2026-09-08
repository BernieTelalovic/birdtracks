"""Single-step reference simplification of projector diagrams."""

from __future__ import annotations

from fractions import Fraction

from birdtracks.permutations import Permutation

from .permutation_node import PermutationNode
from .projector import Connection, NodePort, Projector
from .projector_sum import ProjectorSum
from .symmetrisers import Antisymmetriser, Symmetriser


def expand_node(projector: Projector, node_index: int) -> ProjectorSum:
    """Expand one S/A, absorb redundancies, and collect alike topologies."""
    terms = _full_node_expansion_terms(projector, node_index)
    absorbed = _absorb_same_type_terms(ProjectorSum(terms))
    # Detangling can give separately generated terms different embeddings.
    # Reconstructing the ProjectorSum here deliberately canonicalizes topology,
    # adds exact prefactors, and removes any resulting zero coefficient.
    return ProjectorSum(
        (_replace_trivial_sa_nodes(term).detangle(), coefficient)
        for term, coefficient in absorbed
    )


def _full_node_expansion_terms(
    projector: Projector, node_index: int
) -> list[tuple[Projector, Fraction]]:
    """Return raw full-expansion components before collection and cleanup."""
    if isinstance(node_index, bool) or not isinstance(node_index, int):
        raise TypeError("node_index must be an integer")
    if node_index < 0 or node_index >= len(projector.nodes):
        raise IndexError("node_index is outside the projector")
    node = projector.nodes[node_index]
    if not isinstance(node, (Symmetriser, Antisymmetriser)):
        raise TypeError("only a Symmetriser or Antisymmetriser can be expanded")

    terms = []
    for permutation, local_coefficient in node.collapse().items():
        nodes = list(projector.nodes)
        nodes[node_index] = PermutationNode(permutation, support=node.labels)
        unit = Projector(
            nodes,
            projector.connections,
            input_boundary=projector.input_boundary,
            output_boundary=projector.output_boundary,
            port_orders=projector.port_orders,
        )
        coefficient = (
            projector.canonical_coefficient
            * local_coefficient
            / unit.canonical_coefficient
        )
        # The canvas draws a permutation-only layer as rewired strands.  Do
        # the same exact rewrite before ProjectorSum canonicalization, or
        # terms which only differ by that hidden permutation cannot collect.
        terms.append((_contract_removable_permutation_nodes(unit), coefficient))
    return terms


def permute_node_ports(
    projector: Projector,
    node_index: int,
    side: str,
    index: int,
    destination: int,
) -> Projector:
    """Move one S/A port to another slot without changing the operator."""
    if side not in {"input", "output"}:
        raise ValueError("side must be 'input' or 'output'")
    if node_index < 0 or node_index >= len(projector.nodes):
        raise IndexError("node_index is outside the projector")
    node = projector.nodes[node_index]
    if not isinstance(node, (Symmetriser, Antisymmetriser)):
        raise TypeError("only S/A node ports can be permuted")
    order = list(projector.port_orders[node_index][side])
    if index < 0 or index >= len(order) or destination < 0 or destination >= len(order):
        raise IndexError("port position is outside the node support")
    if index == destination:
        return projector
    moved = order.pop(index)
    order.insert(destination, moved)
    orders = {
        current: {
            "input": values["input"],
            "output": values["output"],
        }
        for current, values in projector.port_orders.items()
    }
    orders[node_index][side] = tuple(order)
    unit = Projector(
        projector.nodes,
        projector.connections,
        input_boundary=projector.input_boundary,
        output_boundary=projector.output_boundary,
        port_orders=orders,
    )
    result = unit * (
        projector.canonical_coefficient / unit.canonical_coefficient
    )
    if result != projector:
        raise AssertionError("port permutation changed projector topology")
    return result


def recursive_expand_node(
    projector: Projector,
    node_index: int,
    *,
    side: str = "input",
    edge: str = "bottom",
) -> ProjectorSum:
    """Apply the top- or bottom-line recursive S/A identity."""
    if side not in {"input", "output"}:
        raise ValueError("side must be 'input' or 'output'")
    if edge not in {"top", "bottom"}:
        raise ValueError("edge must be 'top' or 'bottom'")
    if node_index < 0 or node_index >= len(projector.nodes):
        raise IndexError("node_index is outside the projector")
    node = projector.nodes[node_index]
    if not isinstance(node, (Symmetriser, Antisymmetriser)):
        raise TypeError("only a Symmetriser or Antisymmetriser can be expanded")
    labels = tuple(projector.port_orders[node_index][side])
    if len(labels) < 2:
        return ProjectorSum((projector,))
    if len(labels) == 2:
        # There is no smaller non-trivial S/A to preserve in this case.
        # Treat both recursive edge gestures exactly like the ordinary full
        # expansion, then apply the same contextual zero cleanup used by the
        # general recursive path.
        return remove_multiply_connected_s_a_terms(
            expand_node(projector, node_index)
        )

    terms = _recursive_node_expansion_terms(
        projector, node_index, side=side, edge=edge
    )
    expanded = remove_multiply_connected_s_a_terms(
        _absorb_same_type_terms(
            ProjectorSum(
                (_replace_trivial_sa_nodes(term), coefficient)
                for term, coefficient in terms
            )
        )
    )
    return ProjectorSum(
        (term.detangle(), coefficient) for term, coefficient in expanded
    )


def _recursive_node_expansion_terms(
    projector: Projector,
    node_index: int,
    *,
    side: str,
    edge: str,
) -> list[tuple[Projector, Fraction]]:
    """Return the two contextual recursion branches before cleanup."""
    if side not in {"input", "output"}:
        raise ValueError("side must be 'input' or 'output'")
    if edge not in {"top", "bottom"}:
        raise ValueError("edge must be 'top' or 'bottom'")
    node = projector.nodes[node_index]
    if not isinstance(node, (Symmetriser, Antisymmetriser)):
        raise TypeError("only a Symmetriser or Antisymmetriser can be expanded")
    labels = tuple(projector.port_orders[node_index][side])
    if edge == "top":
        labels = (*labels[1:], labels[0])
    node_type = type(node)
    identity_line = PermutationNode(
        Permutation.identity(), support=(labels[-1],)
    )
    smaller_operator = (
        node_type(labels[:-1])
        if len(labels) > 2
        else PermutationNode(Permutation.identity(), support=labels[:-1])
    )
    prefix = Projector([smaller_operator, identity_line])
    transposition = Projector(
        [
            PermutationNode(
                Permutation.from_cycle(
                    labels[0] if edge == "top" else labels[-2],
                    labels[-1],
                ),
                support=labels,
            )
        ]
    )
    sandwiched = prefix * transposition * prefix
    sign = -1 if isinstance(node, Antisymmetriser) else 1
    k = len(labels)
    local_terms = (
        (prefix, Fraction(1, k)),
        (sandwiched, Fraction(sign * (k - 1), k)),
    )
    terms = []
    for replacement, local_coefficient in local_terms:
        unit = _substitute_node(projector, node_index, replacement)
        coefficient = (
            projector.canonical_coefficient
            * replacement.canonical_coefficient
            * local_coefficient
            / unit.canonical_coefficient
        )
        terms.append((unit, coefficient))
    return terms


def _replace_trivial_sa_nodes(projector: Projector) -> Projector:
    """Represent every one-line S/A as an explicit free identity strand."""
    nodes = tuple(
        PermutationNode(Permutation.identity(), support=node.labels)
        if isinstance(node, (Symmetriser, Antisymmetriser))
        and len(node.support) == 1
        else node
        for node in projector.nodes
    )
    if nodes == projector.nodes:
        return projector
    unit = Projector(
        nodes,
        projector.connections,
        input_boundary=projector.input_boundary,
        output_boundary=projector.output_boundary,
        port_orders=projector.port_orders,
    )
    return unit * (
        projector.canonical_coefficient / unit.canonical_coefficient
    )


def _substitute_node(
    projector: Projector,
    node_index: int,
    replacement: Projector,
) -> Projector:
    """Splice a same-boundary local operator into one graph node."""
    old = projector.nodes[node_index]
    if replacement.support != old.support:
        raise ValueError("replacement support must equal the replaced support")
    added = len(replacement.nodes)
    shift = added - 1

    def outer_port(port: NodePort) -> NodePort:
        return NodePort(port.node + (shift if port.node > node_index else 0), port.label)

    def local_port(port: NodePort) -> NodePort:
        return NodePort(node_index + port.node, port.label)

    incoming = {
        connection.target.label: connection
        for connection in projector.connections
        if connection.target.node == node_index
    }
    outgoing = {
        connection.source.label: connection
        for connection in projector.connections
        if connection.source.node == node_index
    }
    old_inputs = {
        port.label: label
        for label, port in projector.input_boundary.items()
        if port.node == node_index
    }
    old_outputs = {
        port.label: label
        for label, port in projector.output_boundary.items()
        if port.node == node_index
    }
    connections = [
        Connection(outer_port(connection.source), outer_port(connection.target))
        for connection in projector.connections
        if connection.source.node != node_index
        and connection.target.node != node_index
    ]
    connections.extend(
        Connection(local_port(connection.source), local_port(connection.target))
        for connection in replacement.connections
    )
    input_boundary = {
        label: outer_port(port)
        for label, port in projector.input_boundary.items()
        if port.node != node_index
    }
    output_boundary = {
        label: outer_port(port)
        for label, port in projector.output_boundary.items()
        if port.node != node_index
    }
    for label in old.support:
        local_input = local_port(replacement.input_boundary[label])
        local_output = local_port(replacement.output_boundary[label])
        before = incoming.get(label)
        after = outgoing.get(label)
        if before is not None:
            connections.append(Connection(outer_port(before.source), local_input))
        else:
            input_boundary[old_inputs[label]] = local_input
        if after is not None:
            connections.append(Connection(local_output, outer_port(after.target)))
        else:
            output_boundary[old_outputs[label]] = local_output

    orders = {
        index + (shift if index > node_index else 0): {
            "input": values["input"],
            "output": values["output"],
        }
        for index, values in projector.port_orders.items()
        if index != node_index
    }
    orders.update(
        {
            node_index + index: {
                "input": values["input"],
                "output": values["output"],
            }
            for index, values in replacement.port_orders.items()
        }
    )
    return Projector(
        (
            *projector.nodes[:node_index],
            *replacement.nodes,
            *projector.nodes[node_index + 1 :],
        ),
        connections,
        input_boundary=input_boundary,
        output_boundary=output_boundary,
        port_orders=orders,
    )


def _contract_removable_permutation_nodes(projector: Projector) -> Projector:
    """Replace removable permutation nodes by their exact wiring.

    A permutation node is retained when one of its strands has no adjacent
    operator on either side: the current Projector representation needs that
    node to anchor such a boundary-to-boundary strand.  A wholly expanded
    standalone operator is therefore also left in its useful explicit form.
    """
    if not any(
        isinstance(node, (Symmetriser, Antisymmetriser))
        for node in projector.nodes
    ):
        return projector

    candidates = [
        index
        for index, node in enumerate(projector.nodes)
        if isinstance(node, PermutationNode)
    ]
    result = projector
    for index in reversed(candidates):
        contracted = _contract_permutation_node(result, index)
        if contracted is not None:
            result = contracted
    return result


def _contract_permutation_node(
    projector: Projector, node_index: int
) -> Projector | None:
    """Bypass one permutation node, returning ``None`` if it anchors a strand."""
    node = projector.nodes[node_index]
    if not isinstance(node, PermutationNode):
        return None

    incoming = {
        connection.target.label: connection
        for connection in projector.connections
        if connection.target.node == node_index
    }
    outgoing = {
        connection.source.label: connection
        for connection in projector.connections
        if connection.source.node == node_index
    }
    input_at = {
        port.label: boundary_label
        for boundary_label, port in projector.input_boundary.items()
        if port.node == node_index
    }
    output_at = {
        port.label: boundary_label
        for boundary_label, port in projector.output_boundary.items()
        if port.node == node_index
    }

    # A direct boundary-to-boundary strand has nowhere to live after this
    # node is removed, so retain the node rather than losing topology.
    for input_label in node.support:
        output_label = node.permutation(input_label)
        if input_label in input_at and output_label in output_at:
            return None

    connections = [
        connection
        for connection in projector.connections
        if connection.source.node != node_index
        and connection.target.node != node_index
    ]
    input_boundary = dict(projector.input_boundary)
    output_boundary = dict(projector.output_boundary)
    for input_label in node.support:
        output_label = node.permutation(input_label)
        before = incoming.get(input_label)
        after = outgoing.get(output_label)
        if before is not None and after is not None:
            connections.append(Connection(before.source, after.target))
        elif input_label in input_at and after is not None:
            input_boundary[input_at[input_label]] = after.target
        elif before is not None and output_label in output_at:
            output_boundary[output_at[output_label]] = before.source
        else:  # Invalid/incomplete wiring is better left untouched.
            return None

    def shifted(port: NodePort) -> NodePort:
        return NodePort(port.node - (port.node > node_index), port.label)

    remaining_nodes = tuple(
        value
        for index, value in enumerate(projector.nodes)
        if index != node_index
    )
    remaining_orders = {
        index - (index > node_index): {
            "input": orders["input"],
            "output": orders["output"],
        }
        for index, orders in projector.port_orders.items()
        if index != node_index
    }
    unit = Projector(
        remaining_nodes,
        (
            Connection(shifted(connection.source), shifted(connection.target))
            for connection in connections
        ),
        input_boundary={
            label: shifted(port) for label, port in input_boundary.items()
        },
        output_boundary={
            label: shifted(port) for label, port in output_boundary.items()
        },
        port_orders=remaining_orders,
    )
    return unit * (
        projector.canonical_coefficient / unit.canonical_coefficient
    )


def _absorb_same_type_terms(value: ProjectorSum) -> ProjectorSum:
    """Apply nested same-type absorption to every term until stable."""
    from .identities import SAME_TYPE_NESTED_ABSORPTION

    result = []
    for projector, coefficient in value:
        while True:
            rewritten = SAME_TYPE_NESTED_ABSORPTION.apply(projector)
            if rewritten is None:
                break
            if not rewritten:
                coefficient = 0
                break
            ((projector, factor),) = tuple(rewritten)
            coefficient *= factor
        if coefficient:
            result.append((projector, coefficient))
    return ProjectorSum(result)


def simplify_step(projector: Projector) -> ProjectorSum:
    """Apply one hard rule or fully expand one deterministically chosen S/A."""
    if not isinstance(projector, Projector):
        raise TypeError("simplify_step expects a Projector")

    automatic = projector.simplify()
    if len(automatic) != 1 or automatic.coefficient(projector) != 1:
        return automatic

    selected = _target_middle_node(projector)
    if selected is None:
        selected = _middle_layer_node(projector)
    if selected is None:
        return ProjectorSum((projector,))
    return remove_multiply_connected_s_a_terms(expand_node(projector, selected))


def remove_multiply_connected_s_a_terms(value: ProjectorSum) -> ProjectorSum:
    """Discard terms annihilated by a double S/A connection."""
    if not isinstance(value, ProjectorSum):
        raise TypeError("value must be a ProjectorSum")
    from .identities import MULTIPLY_CONNECTED_S_A_ANNIHILATION

    return ProjectorSum(
        (projector, coefficient)
        for projector, coefficient in value
        if MULTIPLY_CONNECTED_S_A_ANNIHILATION.apply(projector) is None
    )


def _target_middle_node(projector: Projector) -> int | None:
    layer_of = {
        node_index: layer_index
        for layer_index, layer in enumerate(projector.layers)
        for node_index in layer
    }
    direct_counts: dict[tuple[int, int], int] = {}
    for connection in projector.connections:
        pair = tuple(sorted((connection.source.node, connection.target.node)))
        left, right = (projector.nodes[index] for index in pair)
        if (
            isinstance(left, Symmetriser)
            and isinstance(right, Antisymmetriser)
        ) or (
            isinstance(left, Antisymmetriser)
            and isinstance(right, Symmetriser)
        ):
            direct_counts[pair] = direct_counts.get(pair, 0) + 1

    targets = []
    for pair, count in direct_counts.items():
        if count != 1:
            continue
        low, high = sorted((layer_of[pair[0]], layer_of[pair[1]]))
        middle = [
            index
            for index, node in enumerate(projector.nodes)
            if low < layer_of[index] < high
            and isinstance(node, (Symmetriser, Antisymmetriser))
        ]
        if middle:
            sizes = sorted(
                (len(projector.nodes[index].support) for index in pair),
                reverse=True,
            )
            targets.append(((-sizes[0], -sizes[1], pair), pair, middle))
    if not targets:
        return None

    _rank, pair, middle = min(targets)
    midpoint = (layer_of[pair[0]] + layer_of[pair[1]]) / 2
    return min(
        middle,
        key=lambda index: (
            -len(projector.nodes[index].support),
            abs(layer_of[index] - midpoint),
            layer_of[index],
            index,
        ),
    )


def _middle_layer_node(projector: Projector) -> int | None:
    count = len(projector.layers)
    if not count:
        return None
    middle_layers = (
        (count // 2,)
        if count % 2
        else (count // 2 - 1, count // 2)
    )
    candidates = [
        (layer_index, node_index)
        for layer_index in middle_layers
        for node_index in projector.layers[layer_index]
        if isinstance(
            projector.nodes[node_index], (Symmetriser, Antisymmetriser)
        )
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            -len(projector.nodes[item[1]].support),
            item[0],
            item[1],
        ),
    )[1]


__all__ = [
    "expand_node",
    "permute_node_ports",
    "recursive_expand_node",
    "remove_multiply_connected_s_a_terms",
    "simplify_step",
]
