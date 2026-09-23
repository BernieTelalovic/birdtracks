"""Canonical algebra-only serialization for projector values."""

from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction

from birdtracks.permutations import Permutation

from ..projector import Connection, NodePort, Projector
from ..projector_sum import ProjectorSum
from ..permutation_node import PermutationNode
from ..symmetrisers import Antisymmetriser, Symmetriser
from ...symbolic import SymbolicCoefficient, parse_symbolic


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be a JSON object")
    return value


def _list(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be a JSON array")
    return value


def _integer(value: object, context: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{context} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"{context} must be an integer") from exc
    raise ValueError(f"{context} must be an integer")


def _labels(value: object, context: str) -> tuple[int, ...]:
    return tuple(_integer(item, f"{context} item") for item in _list(value, context))


def _direction(value: object, context: str) -> str:
    if value not in {"left", "right", "neutral"}:
        raise ValueError(f"{context} must be a valid projector direction")
    return str(value)


def _port(value: NodePort) -> dict[str, int]:
    return {"node": value.node, "label": value.label}


def _decode_port(value: object, context: str) -> NodePort:
    data = _mapping(value, context)
    return NodePort(
        _integer(data.get("node"), f"{context}.node"),
        _integer(data.get("label"), f"{context}.label"),
    )


class ProjectorValueCodec:
    """Encode projectors using only exact topology and algebraic metadata."""

    name = "projector-v1"

    def encode(self, value: Projector | ProjectorSum | SymbolicCoefficient) -> Mapping[str, object]:
        if isinstance(value, SymbolicCoefficient):
            return {"type": "symbolic_scalar", "source": value.latex()}
        if isinstance(value, ProjectorSum):
            return {
                "type": "projector_sum",
                "terms": [
                    {
                        "coefficient": {
                            "numerator": str(coefficient.numerator),
                            "denominator": str(coefficient.denominator),
                        },
                        "projector": self.encode(projector),
                    }
                    for projector, coefficient in value.items()
                ],
            }
        if not isinstance(value, Projector):
            raise TypeError("projector codec expects a Projector or ProjectorSum value")
        nodes: list[dict[str, object]] = []
        for node in value.nodes:
            if isinstance(node, Symmetriser):
                nodes.append({"kind": "symmetriser", "labels": list(node.labels)})
            elif isinstance(node, Antisymmetriser):
                nodes.append(
                    {"kind": "antisymmetriser", "labels": list(node.labels)}
                )
            elif isinstance(node, PermutationNode):
                nodes.append(
                    {
                        "kind": "permutation",
                        "mapping": [list(pair) for pair in node.permutation.mapping.items()],
                        "labels": sorted(node.support),
                        "in_direction": node.in_direction,
                        "out_direction": node.out_direction,
                    }
                )
            else:
                raise TypeError(f"unsupported projector node: {type(node).__name__}")

        payload: dict[str, object] = {
            "type": "projector",
            "coefficient": {
                "numerator": str(value.coefficient.numerator),
                "denominator": str(value.coefficient.denominator),
            },
            "in_direction": value.in_direction,
            "out_direction": value.out_direction,
            "nodes": nodes,
            "connections": [
                {"source": _port(connection.source), "target": _port(connection.target)}
                for connection in value.connections
            ],
            "input_boundary": [
                {"label": label, "port": _port(port)}
                for label, port in sorted(value.input_boundary.items())
            ],
            "output_boundary": [
                {"label": label, "port": _port(port)}
                for label, port in sorted(value.output_boundary.items())
            ],
        }
        if value.port_orders_are_explicit:
            payload["port_orders"] = [
                {
                    "node": node,
                    "input": list(orders["input"]),
                    "output": list(orders["output"]),
                }
                for node, orders in sorted(value.port_orders.items())
            ]
        return payload

    def decode(self, payload: object) -> Projector | ProjectorSum | SymbolicCoefficient:
        data = _mapping(payload, "projector value")
        if data.get("type") == "symbolic_scalar":
            source = data.get("source")
            if not isinstance(source, str):
                raise ValueError("symbolic scalar source must be a string")
            return parse_symbolic(source)
        if data.get("type") == "projector_sum":
            terms = []
            for index, item in enumerate(_list(data.get("terms"), "terms")):
                term = _mapping(item, f"terms[{index}]")
                coefficient_data = _mapping(
                    term.get("coefficient"), f"terms[{index}].coefficient"
                )
                coefficient = Fraction(
                    _integer(
                        coefficient_data.get("numerator"),
                        f"terms[{index}].coefficient.numerator",
                    ),
                    _integer(
                        coefficient_data.get("denominator"),
                        f"terms[{index}].coefficient.denominator",
                    ),
                )
                terms.append((self.decode(term.get("projector")), coefficient))
            return ProjectorSum(terms)  # type: ignore[return-value]
        if data.get("type") != "projector":
            raise ValueError("projector value has an invalid type")

        coefficient_data = _mapping(data.get("coefficient"), "coefficient")
        coefficient = Fraction(
            _integer(coefficient_data.get("numerator"), "coefficient.numerator"),
            _integer(coefficient_data.get("denominator"), "coefficient.denominator"),
        )
        nodes = tuple(self._decode_node(item, index) for index, item in enumerate(_list(data.get("nodes"), "nodes")))
        connections = tuple(
            Connection(
                _decode_port(_mapping(item, "connection").get("source"), "connection.source"),
                _decode_port(_mapping(item, "connection").get("target"), "connection.target"),
            )
            for item in _list(data.get("connections"), "connections")
        )
        input_boundary = self._decode_boundary(data.get("input_boundary"), "input_boundary")
        output_boundary = self._decode_boundary(data.get("output_boundary"), "output_boundary")
        port_orders = self._decode_port_orders(data.get("port_orders")) if "port_orders" in data else None
        return Projector(
            nodes,
            connections,
            coefficient=coefficient,
            input_boundary=input_boundary,
            output_boundary=output_boundary,
            port_orders=port_orders,
            in_direction=_direction(data.get("in_direction"), "in_direction"),
            out_direction=_direction(data.get("out_direction"), "out_direction"),
        )

    def _decode_node(self, value: object, index: int) -> object:
        data = _mapping(value, f"nodes[{index}]")
        kind = data.get("kind")
        labels = _labels(data.get("labels"), f"nodes[{index}].labels")
        if kind == "symmetriser":
            return Symmetriser(labels)
        if kind == "antisymmetriser":
            return Antisymmetriser(labels)
        if kind == "permutation":
            mapping = []
            for pair_index, pair in enumerate(_list(data.get("mapping"), f"nodes[{index}].mapping")):
                values = _list(pair, f"nodes[{index}].mapping[{pair_index}]")
                if len(values) != 2:
                    raise ValueError("permutation mapping pairs must contain two labels")
                mapping.append(
                    (
                        _integer(values[0], "permutation source"),
                        _integer(values[1], "permutation target"),
                    )
                )
            return PermutationNode(
                Permutation(mapping),
                support=labels,
                in_direction=_direction(
                    data.get("in_direction", "neutral"),
                    f"nodes[{index}].in_direction",
                ),
                out_direction=_direction(
                    data.get("out_direction", "neutral"),
                    f"nodes[{index}].out_direction",
                ),
            )
        raise ValueError(f"nodes[{index}] has an unsupported kind")

    @staticmethod
    def _decode_boundary(value: object, context: str) -> dict[int, NodePort]:
        result: dict[int, NodePort] = {}
        for index, item in enumerate(_list(value, context)):
            data = _mapping(item, f"{context}[{index}]")
            label = _integer(data.get("label"), f"{context}[{index}].label")
            if label in result:
                raise ValueError(f"{context} contains duplicate label {label}")
            result[label] = _decode_port(data.get("port"), f"{context}[{index}].port")
        return result

    @staticmethod
    def _decode_port_orders(value: object) -> dict[int, dict[str, tuple[int, ...]]]:
        result: dict[int, dict[str, tuple[int, ...]]] = {}
        for index, item in enumerate(_list(value, "port_orders")):
            data = _mapping(item, f"port_orders[{index}]")
            node = _integer(data.get("node"), f"port_orders[{index}].node")
            if node in result:
                raise ValueError(f"port_orders contains duplicate node {node}")
            result[node] = {
                "input": _labels(data.get("input"), f"port_orders[{index}].input"),
                "output": _labels(data.get("output"), f"port_orders[{index}].output"),
            }
        return result


projector_codec = ProjectorValueCodec()


__all__ = ["ProjectorValueCodec", "projector_codec"]
