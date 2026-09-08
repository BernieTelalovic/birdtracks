"""Immutable directed connection graphs of symbolic projector nodes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from fractions import Fraction
from os import PathLike
from types import MappingProxyType

from birdtracks.linear_combinations.coefficients import require_coefficient
from birdtracks.linear_combinations import PermutationSum, PolynomialPermutationSum
from birdtracks.permutations import Permutation

from .permutation_node import PermutationNode
from .symmetrisers import Antisymmetriser, Symmetriser

ProjectorNode = Symmetriser | Antisymmetriser | PermutationNode


@dataclass(frozen=True, order=True)
class NodePort:
    """A labelled port on a node identified by its sequence position."""

    node: int
    label: int

    def __post_init__(self) -> None:
        if isinstance(self.node, bool) or not isinstance(self.node, int):
            raise TypeError("a port node index must be an integer")
        if self.node < 0:
            raise ValueError("a port node index cannot be negative")
        if isinstance(self.label, bool) or not isinstance(self.label, int):
            raise TypeError("a port line label must be an integer")


@dataclass(frozen=True, order=True)
class Connection:
    """A right-to-left line from a source output to a target input."""

    source: NodePort
    target: NodePort


class Projector:
    """A directed graph of symmetrisers and antisymmetrisers.

    Nodes retain their supplied left-to-right order. By default, consecutive
    occurrences of every line label are connected from right to left. Explicit
    connections may instead describe arbitrary topology, including traces.
    """

    __slots__ = (
        "_nodes",
        "_layers",
        "_connections",
        "_input_boundary",
        "_output_boundary",
        "_port_orders",
        "_port_orders_explicit",
        "_coefficient",
        "_canonical_coefficient",
        "_canonical_value_coefficient",
        "_canonical_topology",
        "_hash",
    )

    def __init__(
        self,
        nodes: Iterable[ProjectorNode],
        connections: Iterable[Connection] | None = None,
        *,
        coefficient: int | float | Fraction = 1,
        input_boundary: Mapping[int, NodePort] | None = None,
        output_boundary: Mapping[int, NodePort] | None = None,
        port_orders: Mapping[int, Mapping[str, Iterable[int]]] | None = None,
    ) -> None:
        try:
            canonical_nodes = tuple(nodes)
        except TypeError as exc:
            raise TypeError("nodes must be a collection of projector nodes") from exc
        if not all(
            isinstance(node, (Symmetriser, Antisymmetriser, PermutationNode))
            for node in canonical_nodes
        ):
            raise TypeError(
                "nodes must be Symmetriser, Antisymmetriser, or "
                "PermutationNode objects"
            )

        self._nodes = canonical_nodes
        self._layers = _make_layers(canonical_nodes)
        supplied = (
            _automatic_connections(canonical_nodes)
            if connections is None
            else tuple(connections)
        )
        self._connections = _validated_connections(canonical_nodes, supplied)
        required_inputs: frozenset[NodePort] | None = None
        required_outputs: frozenset[NodePort] | None = None
        if input_boundary is not None and output_boundary is not None:
            all_ports = frozenset(
                NodePort(index, label)
                for index, node in enumerate(canonical_nodes)
                for label in node.support
            )
            required_inputs = all_ports - {
                connection.target for connection in self._connections
            }
            required_outputs = all_ports - {
                connection.source for connection in self._connections
            }
            default_inputs, default_outputs = {}, {}
        else:
            default_inputs, default_outputs = _default_boundaries(
                canonical_nodes, self._connections
            )
        self._input_boundary = _validated_boundary(
            "input", input_boundary, default_inputs, required_inputs
        )
        self._output_boundary = _validated_boundary(
            "output", output_boundary, default_outputs, required_outputs
        )
        if self._input_boundary.keys() != self._output_boundary.keys():
            raise ValueError("input and output boundary labels must match")
        self._port_orders = _validated_port_orders(canonical_nodes, port_orders)
        self._port_orders_explicit = port_orders is not None
        self._coefficient = require_coefficient(coefficient)
        self._canonical_coefficient = (
            self._coefficient
            * _port_order_sign(canonical_nodes, self._port_orders)
        )
        from .canonical import canonical_graph_key

        self._canonical_topology, orientation_sign = canonical_graph_key(
            canonical_nodes,
            self._connections,
            self._input_boundary,
            self._output_boundary,
        )
        self._canonical_value_coefficient = (
            self._canonical_coefficient * orientation_sign
        )
        self._hash = hash(
            (self._canonical_value_coefficient, self._canonical_topology)
        )

    @property
    def coefficient(self) -> Fraction:
        """The exact scalar displayed with this ordered projector diagram."""
        return self._coefficient

    @property
    def canonical_coefficient(self) -> Fraction:
        """Coefficient after absorbing antisymmetric port-order parity."""
        return self._canonical_coefficient

    @property
    def canonical_value_coefficient(self) -> Fraction:
        """Coefficient relative to canonical internal strand ordering."""
        return self._canonical_value_coefficient

    @property
    def nodes(self) -> tuple[ProjectorNode, ...]:
        return self._nodes

    @property
    def layers(self) -> tuple[tuple[int, ...], ...]:
        """Node indices grouped into maximal consecutive disjoint-support layers."""
        return self._layers

    @property
    def connections(self) -> tuple[Connection, ...]:
        return self._connections

    @property
    def support(self) -> frozenset[int]:
        """The union of labels carried by this projector's boundary."""
        return frozenset(self._input_boundary)

    @property
    def external_inputs(self) -> frozenset[NodePort]:
        """Unconnected input ports on the right side of their nodes."""
        connected = {connection.target for connection in self._connections}
        return self._all_ports() - connected

    @property
    def external_outputs(self) -> frozenset[NodePort]:
        """Unconnected output ports on the left side of their nodes."""
        connected = {connection.source for connection in self._connections}
        return self._all_ports() - connected

    @property
    def input_boundary(self) -> Mapping[int, NodePort]:
        """Map fixed right-boundary labels to external input ports."""
        return self._input_boundary

    @property
    def output_boundary(self) -> Mapping[int, NodePort]:
        """Map fixed left-boundary labels to external output ports."""
        return self._output_boundary

    @property
    def port_orders(self) -> Mapping[int, Mapping[str, tuple[int, ...]]]:
        """Ordered input and output ports for every S/A node."""
        return self._port_orders

    @property
    def port_orders_are_explicit(self) -> bool:
        """Whether port ordering was pinned rather than left to layout."""
        return self._port_orders_explicit

    def _all_ports(self) -> frozenset[NodePort]:
        return frozenset(
            NodePort(index, label)
            for index, node in enumerate(self._nodes)
            for label in node.support
        )

    def evaluate(
        self,
        positions: Mapping[
            int | str, tuple[float, float] | Mapping[str, float]
        ] | None = None,
        *,
        style: str | PathLike[str] | None = None,
        session: str | PathLike[str] | None = None,
        detangler: str | PathLike[str] | object | None = None,
        debug: bool = False,
    ) -> object:
        """Open this projector in an interactive evaluation canvas."""
        if session is not None:
            from .canvas_session import (
                ProjectorCanvasSession,
                _resolve_canvas_session_path,
            )

            if _resolve_canvas_session_path(session).exists():
                return ProjectorCanvasSession.load(session).open(
                    style=style, detangler=detangler, debug=debug
                )
        from .projector_sum import ProjectorSum
        from .widget import projector_sum_widget, projector_widget

        editor = projector_widget(
            self, positions, style, mode="evaluate", debug=debug
        )
        return projector_sum_widget(
            ProjectorSum((self,)),
            style=style,
            initial_editor=editor,
            session=session,
            detangler=detangler,
            debug=debug,
        )

    @classmethod
    def create(
        cls,
        *,
        style: str | PathLike[str] | None = None,
        session: str | PathLike[str] | None = None,
        detangler: str | PathLike[str] | object | None = None,
        debug: bool = False,
    ) -> object:
        """Compatibility alias for :func:`birdtracks.create`."""
        from .canvas import create

        return create(
            style=style, session=session, detangler=detangler, debug=debug
        )

    def collapse(
        self, *, dimension: int | float | Fraction | None = None
    ) -> PermutationSum | PolynomialPermutationSum:
        """Expand this graph into an exact permutation sum.

        A traced term contributes one power of the symbolic dimension ``N``
        per closed loop. Supplying ``dimension`` evaluates ``N`` exactly.
        """
        from .collapse import collapse_projector

        exact_dimension = (
            None if dimension is None else require_coefficient(dimension)
        )
        return collapse_projector(self, dimension=exact_dimension)

    def simplify(self) -> ProjectorSum:
        """Return a simplified equivalent operator.

        A symmetriser and antisymmetriser joined directly by two or more
        strands annihilate the complete diagram.
        """
        from .identities import IDENTITIES
        from .projector_sum import ProjectorSum

        for identity in IDENTITIES.values():
            if not identity.automatic:
                continue
            rewritten = identity.apply(self)
            if rewritten is not None:
                return rewritten
        return ProjectorSum((self,))

    def simplify_step(self) -> ProjectorSum:
        """Apply one deterministic simplification or full-node expansion."""
        from .simplification import simplify_step

        return simplify_step(self)

    def detangle(self) -> Projector:
        """Return an equal diagram with its internal line levels optimized."""
        from .layout import detangle

        return detangle(self)

    def quasi_idempotent(self) -> bool:
        """Return whether the complete diagram is horizontally mirror-symmetric."""
        return _structurally_equal(self, _horizontal_reflection(self))

    def normalise(self) -> Projector:
        """Return ``P / lambda`` when exact collapse proves ``P² = lambda P``.

        The graph is retained and only its exact prefactor changes.  A new
        immutable value is returned so existing hashes remain valid.
        """
        collapsed = self.collapse()
        squared = (self * self).collapse()
        factor = _constant_proportionality(collapsed, squared)
        if factor is None or not factor:
            raise ValueError(
                "projector cannot be normalised: P * P is not a nonzero "
                "constant multiple of P"
            )
        return self / factor

    def trace(self) -> Projector:
        """Identify equally labelled left and right boundary strands."""
        if not self._input_boundary:
            return self
        closures = tuple(
            Connection(self._output_boundary[label], input_port)
            for label, input_port in self._input_boundary.items()
        )
        return Projector(
            self._nodes,
            self._connections + closures,
            coefficient=self._coefficient,
            port_orders=(
                self._port_orders if self._port_orders_explicit else None
            ),
        )

    def __mul__(self, other: object) -> Projector:
        if isinstance(other, Projector):
            return _compose_projectors(self, other)
        if isinstance(other, Permutation):
            return _compose_projectors(self, _projector_from_permutation(other))
        if _is_coefficient(other):
            exact = require_coefficient(other)
            return Projector(
                self._nodes,
                self._connections,
                coefficient=self._coefficient * exact,
                input_boundary=self._input_boundary,
                output_boundary=self._output_boundary,
                port_orders=self._port_orders if self._port_orders_explicit else None,
            )
        return NotImplemented

    def __rmul__(self, other: object) -> Projector:
        if isinstance(other, Permutation):
            return _compose_projectors(_projector_from_permutation(other), self)
        if _is_coefficient(other):
            return self.__mul__(other)
        return NotImplemented

    def __neg__(self) -> Projector:
        return self * -1

    def __add__(self, other: object) -> object:
        from .projector_sum import ProjectorSum

        if isinstance(other, (Projector, ProjectorSum)):
            return ProjectorSum((self,)) + other
        return NotImplemented

    def __radd__(self, other: object) -> object:
        if other == 0 and type(other) is int:
            from .projector_sum import ProjectorSum

            return ProjectorSum((self,))
        return self.__add__(other)

    def __sub__(self, other: object) -> object:
        from .projector_sum import ProjectorSum

        if isinstance(other, (Projector, ProjectorSum)):
            return ProjectorSum((self,)) - other
        return NotImplemented

    def __rsub__(self, other: object) -> object:
        from .projector_sum import ProjectorSum

        if isinstance(other, (Projector, ProjectorSum)):
            return ProjectorSum((self,)).__rsub__(other)
        return NotImplemented

    def __truediv__(self, scalar: object) -> Projector:
        exact = require_coefficient(scalar)
        if not exact:
            raise ZeroDivisionError("cannot divide a projector by zero")
        return self * (1 / exact)

    def __mod__(self, other: object) -> bool:
        """Return whether ``self = k * other`` for some nonzero scalar ``k``."""
        if not isinstance(other, Projector):
            return NotImplemented
        if not self._canonical_value_coefficient:
            return not other._canonical_value_coefficient
        if not other._canonical_value_coefficient:
            return False
        return self._canonical_topology == other._canonical_topology

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Projector)
            and self._canonical_value_coefficient
            == other._canonical_value_coefficient
            and self._canonical_topology == other._canonical_topology
        )

    def __hash__(self) -> int:
        return self._hash

    def __repr__(self) -> str:
        coefficient = (
            "" if self._coefficient == 1 else f", coefficient={self._coefficient!r}"
        )
        port_orders = (
            f", port_orders={{{', '.join(f'{index}: {dict(orders)!r}' for index, orders in self._port_orders.items())}}}"
            if self._port_orders_explicit
            else ""
        )
        return (
            f"Projector({list(self._nodes)!r}, "
            f"connections={list(self._connections)!r}{coefficient}, "
            f"input_boundary={dict(self._input_boundary)!r}, "
            f"output_boundary={dict(self._output_boundary)!r}{port_orders})"
        )


def _make_layers(nodes: tuple[ProjectorNode, ...]) -> tuple[tuple[int, ...], ...]:
    layers: list[tuple[int, ...]] = []
    current: list[int] = []
    occupied: set[int] = set()
    for index, node in enumerate(nodes):
        if occupied & node.support:
            layers.append(tuple(current))
            current = []
            occupied = set()
        current.append(index)
        occupied.update(node.support)
    if current:
        layers.append(tuple(current))
    return tuple(layers)


def _structurally_equal(left: Projector, right: Projector) -> bool:
    return (
        left.canonical_coefficient == right.canonical_coefficient
        and left.nodes == right.nodes
        and left.connections == right.connections
        and left.input_boundary == right.input_boundary
        and left.output_boundary == right.output_boundary
    )


def _compose_projectors(left: Projector, right: Projector) -> Projector:
    """Join ``left`` to ``right``; absent labels pass through unchanged."""
    offset = len(left.nodes)

    def shifted(port: NodePort) -> NodePort:
        return NodePort(port.node + offset, port.label)

    connections = list(left.connections)
    connections.extend(
        Connection(shifted(connection.source), shifted(connection.target))
        for connection in right.connections
    )
    shared = left.input_boundary.keys() & right.input_boundary.keys()
    connections.extend(
        Connection(shifted(right.output_boundary[label]), left.input_boundary[label])
        for label in sorted(shared)
    )

    support = sorted(left.input_boundary.keys() | right.input_boundary.keys())
    input_boundary = {
        label: (
            shifted(right.input_boundary[label])
            if label in right.input_boundary
            else left.input_boundary[label]
        )
        for label in support
    }
    output_boundary = {
        label: (
            left.output_boundary[label]
            if label in left.output_boundary
            else shifted(right.output_boundary[label])
        )
        for label in support
    }
    port_orders = {
        **{
            index: dict(orders)
            for index, orders in left.port_orders.items()
        },
        **{
            index + offset: dict(orders)
            for index, orders in right.port_orders.items()
        },
    }
    return Projector(
        left.nodes + right.nodes,
        connections,
        coefficient=left.coefficient * right.coefficient,
        input_boundary=input_boundary,
        output_boundary=output_boundary,
        port_orders=(
            port_orders
            if left.port_orders_are_explicit or right.port_orders_are_explicit
            else None
        ),
    )


def _projector_from_permutation(permutation: Permutation) -> Projector:
    return Projector([] if not permutation else [PermutationNode(permutation)])


def _horizontal_reflection(projector: Projector) -> Projector:
    last = len(projector.nodes) - 1

    def reflected_port(port: NodePort) -> NodePort:
        return NodePort(last - port.node, port.label)

    nodes = tuple(
        PermutationNode(node.permutation.inverse())
        if isinstance(node, PermutationNode)
        else node
        for node in reversed(projector.nodes)
    )
    connections = tuple(
        Connection(
            reflected_port(connection.target),
            reflected_port(connection.source),
        )
        for connection in projector.connections
    )
    port_orders = {
        last - index: {
            "input": orders["output"],
            "output": orders["input"],
        }
        for index, orders in projector.port_orders.items()
    }
    return Projector(
        nodes,
        connections,
        coefficient=projector.coefficient,
        input_boundary={
            label: reflected_port(port)
            for label, port in projector.output_boundary.items()
        },
        output_boundary={
            label: reflected_port(port)
            for label, port in projector.input_boundary.items()
        },
        port_orders=port_orders if projector.port_orders_are_explicit else None,
    )


def _constant_proportionality(
    value: PermutationSum | PolynomialPermutationSum,
    multiple: PermutationSum | PolynomialPermutationSum,
) -> Fraction | None:
    value_terms = _polynomial_coefficients(value)
    multiple_terms = _polynomial_coefficients(multiple)
    if not value_terms:
        return None
    key = min(value_terms, key=lambda item: (tuple(item[0]), item[1]))
    factor = multiple_terms.get(key, Fraction()) / value_terms[key]
    keys = value_terms.keys() | multiple_terms.keys()
    if all(
        multiple_terms.get(term, Fraction())
        == factor * value_terms.get(term, Fraction())
        for term in keys
    ):
        return factor
    return None


def _polynomial_coefficients(
    value: PermutationSum | PolynomialPermutationSum,
) -> dict[tuple[Permutation, int], Fraction]:
    if isinstance(value, PermutationSum):
        return {
            (permutation, 0): coefficient
            for permutation, coefficient in value.items()
        }
    return {
        (permutation, power): coefficient
        for permutation, polynomial in value.items()
        for power, coefficient in polynomial
    }


def _automatic_connections(
    nodes: tuple[ProjectorNode, ...],
) -> tuple[Connection, ...]:
    last_node: dict[int, int] = {}
    result: list[Connection] = []
    for index, node in enumerate(nodes):
        for label in sorted(node.support):
            if label in last_node:
                result.append(
                    Connection(NodePort(index, label), NodePort(last_node[label], label))
                )
            last_node[label] = index
    return tuple(result)


def _validated_connections(
    nodes: tuple[ProjectorNode, ...],
    connections: Iterable[Connection],
) -> tuple[Connection, ...]:
    checked: list[Connection] = []
    used_sources: set[NodePort] = set()
    used_targets: set[NodePort] = set()
    for connection in connections:
        if not isinstance(connection, Connection):
            raise TypeError("connections must contain Connection objects")
        for port in (connection.source, connection.target):
            if port.node >= len(nodes):
                raise ValueError(f"connection references unknown node {port.node!r}")
            if port.label not in nodes[port.node].support:
                raise ValueError(
                    f"line {port.label!r} is not supported by node {port.node}"
                )
        if connection.source in used_sources:
            raise ValueError("an output port cannot have multiple outgoing lines")
        if connection.target in used_targets:
            raise ValueError("an input port cannot have multiple incoming lines")
        used_sources.add(connection.source)
        used_targets.add(connection.target)
        checked.append(connection)
    return tuple(sorted(checked))


def _default_boundaries(
    nodes: tuple[ProjectorNode, ...],
    connections: tuple[Connection, ...],
) -> tuple[dict[int, NodePort], dict[int, NodePort]]:
    all_ports = frozenset(
        NodePort(index, label)
        for index, node in enumerate(nodes)
        for label in node.support
    )
    connected_inputs = {connection.target for connection in connections}
    connected_outputs = {connection.source for connection in connections}
    external_inputs = all_ports - connected_inputs
    external_outputs = all_ports - connected_outputs
    next_port = {connection.source: connection.target for connection in connections}
    inputs: dict[int, NodePort] = {}
    outputs: dict[int, NodePort] = {}
    for start in sorted(external_inputs):
        if start.label in inputs:
            raise ValueError("default boundary labels are not unique")
        inputs[start.label] = start
        current = start
        visited: set[NodePort] = set()
        while current in next_port:
            if current in visited:
                raise ValueError("an external strand cannot enter a connection cycle")
            visited.add(current)
            current = next_port[current]
        outputs[start.label] = current
    if set(outputs.values()) != set(external_outputs):
        raise ValueError("connections do not form complete external strands")
    return inputs, outputs


def _validated_boundary(
    side: str,
    supplied: Mapping[int, NodePort] | None,
    default: dict[int, NodePort],
    required_ports: frozenset[NodePort] | None = None,
) -> Mapping[int, NodePort]:
    values = default if supplied is None else dict(supplied)
    if any(isinstance(label, bool) or not isinstance(label, int) for label in values):
        raise TypeError(f"{side} boundary labels must be integers")
    if any(not isinstance(port, NodePort) for port in values.values()):
        raise TypeError(f"{side} boundary values must be NodePort objects")
    if len(set(values.values())) != len(values):
        raise ValueError(f"{side} boundary ports must be unique")
    expected = set(default.values()) if required_ports is None else set(required_ports)
    if set(values.values()) != expected:
        raise ValueError(f"{side} boundary must cover every external {side} port")
    return MappingProxyType(dict(sorted(values.items())))


def _validated_port_orders(
    nodes: tuple[ProjectorNode, ...],
    supplied: Mapping[int, Mapping[str, Iterable[int]]] | None,
) -> Mapping[int, Mapping[str, tuple[int, ...]]]:
    if supplied is None:
        values: Mapping[int, Mapping[str, Iterable[int]]] = {
            index: {
                "input": (
                    node.labels
                    if isinstance(node, (Symmetriser, Antisymmetriser))
                    else sorted(node.support)
                ),
                "output": (
                    node.labels
                    if isinstance(node, (Symmetriser, Antisymmetriser))
                    else sorted(node.support)
                ),
            }
            for index, node in enumerate(nodes)
        }
    else:
        values = supplied
    if set(values) != set(range(len(nodes))):
        raise ValueError("port orders must specify every projector node")
    result: dict[int, Mapping[str, tuple[int, ...]]] = {}
    for index, node in enumerate(nodes):
        sides = values[index]
        if set(sides) != {"input", "output"}:
            raise ValueError("each port order requires input and output sides")
        checked: dict[str, tuple[int, ...]] = {}
        for side in ("input", "output"):
            order = tuple(sides[side])
            if len(order) != len(node.support) or set(order) != node.support:
                raise ValueError(
                    f"node {index} {side} order must permute its support"
                )
            checked[side] = order
        result[index] = MappingProxyType(checked)
    return MappingProxyType(result)


def _port_order_sign(
    nodes: tuple[ProjectorNode, ...],
    orders: Mapping[int, Mapping[str, tuple[int, ...]]],
) -> int:
    sign = 1
    for index, node in enumerate(nodes):
        if not isinstance(node, Antisymmetriser):
            continue
        canonical = node.labels
        rank = {label: position for position, label in enumerate(canonical)}
        for side in ("input", "output"):
            values = [rank[label] for label in orders[index][side]]
            inversions = sum(
                left > right
                for position, left in enumerate(values)
                for right in values[position + 1 :]
            )
            if inversions % 2:
                sign = -sign
    return sign


def _is_coefficient(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float, Fraction))


__all__ = ["Connection", "NodePort", "Projector", "ProjectorNode"]
