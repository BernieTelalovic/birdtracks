"""Exact, representation-sensitive state for the first projector editor slice.

Redraw commands preserve connectivity and compensate relative A-port parity.
They never collapse, collect terms, or choose a new layout. A session represents
one term occurrence; its outer factor is independent of the diagram scalar.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
import json
import math
from uuid import uuid4

from birdtracks.symbolic import SymbolicCoefficient

from .projector import Projector
from .symmetrisers import Antisymmetriser, Symmetriser
from .whiteboard.projector_codec import projector_codec

Factor = Fraction | SymbolicCoefficient


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _rational(value: Fraction) -> dict[str, str]:
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def _factor_payload(value: Factor) -> dict[str, object]:
    if isinstance(value, SymbolicCoefficient):
        return dict(projector_codec.encode(value))
    return {"type": "rational", **_rational(value)}


def _factor(value: Mapping[str, object]) -> Factor:
    if value.get("type") == "rational":
        return Fraction(int(value["numerator"]), int(value["denominator"]))
    result = projector_codec.decode(value)
    if not isinstance(result, SymbolicCoefficient):
        raise ValueError("editor outer factor must be a rational or symbolic scalar")
    return result


def _presentation(projector: Projector, value: Mapping[str, object]) -> str:
    data = dict(value)
    if any(not isinstance(data.get(key, {}), Mapping)
           for key in ("positions", "free_levels", "boundary_orders", "line_colors")):
        raise ValueError("drawing fields must be mappings")
    for index, position in data.get("positions", {}).items():
        if not 0 <= int(index) < len(projector.nodes):
            raise ValueError("position references an unknown node")
        if set(position) != {"x", "y"} or any(
            isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n)
            for n in position.values()
        ):
            raise ValueError("positions require finite x/y coordinates")
    for side, labels in data.get("boundary_orders", {}).items():
        if side not in {"input", "output"} or len(labels) != len(projector.support) or set(labels) != projector.support:
            raise ValueError("boundary arrangement must permute the boundary labels")
    for levels in data.get("free_levels", {}).values():
        if not isinstance(levels, Mapping):
            raise ValueError("route layers must map strand labels to levels")
        if any(isinstance(n, bool) or not isinstance(n, (int, float))
               or not math.isfinite(n) or n < 0 for n in levels.values()):
            raise ValueError("route levels must be finite and nonnegative")
    return _json(data)


def _parity(order: Sequence[int], previous: Sequence[int]) -> int:
    if len(order) != len(previous) or set(order) != set(previous):
        raise ValueError("port order must permute the previous ports exactly")
    if any(isinstance(label, bool) or not isinstance(label, int) for label in order):
        raise ValueError("port labels must be integers")
    rank = {label: index for index, label in enumerate(previous)}
    values = [rank[label] for label in order]
    inversions = sum(a > b for i, a in enumerate(values) for b in values[i + 1 :])
    return -1 if inversions % 2 else 1


def project_port_orders(
    projector: Projector, changes: Mapping[int, Mapping[str, Sequence[int]]],
) -> Projector:
    """Translate a redraw to an exact oriented value, with relative parity once.

    Shared by commands and initial rendering. No IDs, history, layout selection,
    collapse, or term collection belong to this pure translation boundary.
    """
    orders = {i: dict(sides) for i, sides in projector.port_orders.items()}
    sign = 1
    for index, sides in changes.items():
        if isinstance(index, bool) or not isinstance(index, int) or index not in orders:
            raise ValueError("unknown projector node")
        node = projector.nodes[index]
        if not isinstance(node, (Symmetriser, Antisymmetriser)):
            raise ValueError("only S/A ports support redraw reordering")
        if not isinstance(sides, Mapping) or not sides or not set(sides) <= {"input", "output"}:
            raise ValueError("reorder requires input and/or output orders")
        for side, order in sides.items():
            parity = _parity(order, orders[index][side])
            if isinstance(node, Antisymmetriser):
                sign *= parity
            orders[index][side] = tuple(order)
    return Projector(
        projector.nodes, projector.connections, coefficient=projector.coefficient * sign,
        input_boundary=projector.input_boundary, output_boundary=projector.output_boundary,
        port_orders=orders, in_direction=projector.in_direction, out_direction=projector.out_direction,
    )


@dataclass(frozen=True, eq=False)
class EditorState:
    """One immutable term, drawing, and selection; IDs are editor-only data."""

    projector: Projector
    outer_factor: Factor
    term_id: str
    node_ids: tuple[str, ...]
    strand_ids: tuple[str, ...]
    presentation_json: str
    selection: tuple[str, ...] = ()
    revision: int = 0

    @classmethod
    def create(
        cls, projector: Projector, presentation: Mapping[str, object], *,
        outer_factor: Factor = Fraction(1), term_id: str | None = None,
    ) -> EditorState:
        if not isinstance(projector, Projector):
            raise TypeError("editor expects a Projector")
        if not isinstance(outer_factor, (Fraction, SymbolicCoefficient)):
            raise TypeError("outer factor must be an exact rational or symbolic scalar")
        projector = Projector(
            projector.nodes, projector.connections, coefficient=projector.coefficient,
            input_boundary=projector.input_boundary, output_boundary=projector.output_boundary,
            port_orders=projector.port_orders, in_direction=projector.in_direction,
            out_direction=projector.out_direction,
        )
        identity = term_id or uuid4().hex
        strands = len(projector.connections) + 2 * len(projector.support)
        return cls(
            projector, outer_factor, identity,
            tuple(f"{identity}:node:{i}" for i in range(len(projector.nodes))),
            tuple(f"{identity}:strand:{i}" for i in range(strands)),
            _presentation(projector, presentation),
        )

    @property
    def presentation(self) -> dict[str, object]:
        return json.loads(self.presentation_json)

    @property
    def displayed_coefficient(self) -> Factor:
        return self.outer_factor * self.projector.coefficient

    def payload(self) -> dict[str, object]:
        return {
            "projector": dict(projector_codec.encode(self.projector)),
            "outer_factor": _factor_payload(self.outer_factor),
            "term_id": self.term_id, "node_ids": list(self.node_ids),
            "strand_ids": list(self.strand_ids), "presentation": self.presentation,
            "selection": list(self.selection), "revision": self.revision,
        }

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EditorState):
            return False
        left, right = self.payload(), other.payload()
        left.pop("revision")
        right.pop("revision")
        return left == right

    __hash__ = None

    @classmethod
    def decode(cls, payload: Mapping[str, object]) -> EditorState:
        projector = projector_codec.decode(payload["projector"])
        if not isinstance(projector, Projector):
            raise ValueError("editor term requires a Projector")
        result = cls.create(projector, payload["presentation"],
                            outer_factor=_factor(payload["outer_factor"]),
                            term_id=payload["term_id"])
        if not isinstance(payload["term_id"], str) or not payload["term_id"]:
            raise ValueError("editor term ID must be a nonempty string")
        node_ids, strand_ids = tuple(payload["node_ids"]), tuple(payload["strand_ids"])
        ids = (result.term_id, *node_ids, *strand_ids)
        if (len(node_ids) != len(result.node_ids) or
                len(strand_ids) != len(result.strand_ids) or
                any(not isinstance(i, str) or not i for i in ids) or
                len(set(ids)) != len(ids)):
            raise ValueError("invalid or duplicate editor IDs")
        selection = tuple(payload.get("selection", ()))
        if not set(selection) <= set(ids):
            raise ValueError("selection references an unknown editor ID")
        revision = payload.get("revision", 0)
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ValueError("editor revision must be a nonnegative integer")
        return replace(result, node_ids=node_ids, strand_ids=strand_ids,
                       selection=selection, revision=revision)


class EditorSession:
    """Atomic reorder transactions and monotonic undo/redo for one occurrence."""

    def __init__(self, state: EditorState) -> None:
        self.state = state
        self._undo: list[EditorState] = []
        self._redo: list[EditorState] = []

    def _check_revision(self, revision: int) -> None:
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise ValueError("base revision must be an integer")
        if revision != self.state.revision:
            raise ValueError("stale editor command; use the current revision")

    def reorder(
        self, changes: Mapping[str, Mapping[str, Sequence[int]]], *,
        base_revision: int, presentation: Mapping[str, object] | None = None,
        selection: Sequence[str] | None = None,
    ) -> EditorState:
        """Reorder any input/output sides as one compensated redraw transaction."""
        self._check_revision(base_revision)
        if not isinstance(changes, Mapping):
            raise ValueError("reorder changes must map editor node IDs to port orders")
        before = self.state
        if selection is not None and not set(selection) <= {before.term_id, *before.node_ids, *before.strand_ids}:
            raise ValueError("selection references an unknown editor ID")
        if presentation is not None:
            before = replace(before, presentation_json=_presentation(before.projector, presentation))
        projector = before.projector
        indexed = {}
        for node_id, sides in changes.items():
            if node_id not in before.node_ids:
                raise ValueError(f"unknown editor node: {node_id}")
            indexed[before.node_ids.index(node_id)] = sides
        value = project_port_orders(projector, indexed)
        changed = any(projector.port_orders[i] != sides for i, sides in value.port_orders.items())
        if not changed:
            return self.state
        candidate = replace(before, projector=value, revision=self.state.revision + 1,
                            selection=tuple(selection) if selection is not None else before.selection)
        self._undo.append(before)
        self._redo.clear()
        self.state = candidate
        return candidate

    def presentation_checkpoint(self, presentation: Mapping[str, object], *, base_revision: int) -> None:
        """Bridge existing movement/routes; no layout or new editing algorithm."""
        self._check_revision(base_revision)
        candidate = replace(self.state, presentation_json=_presentation(self.state.projector, presentation))
        if candidate != self.state:
            self.state = replace(candidate, revision=self.state.revision + 1)
            # Existing non-port edits are history barriers for this first slice.
            self._undo.clear()
            self._redo.clear()

    def undo(self, *, base_revision: int) -> EditorState:
        self._check_revision(base_revision)
        if self._undo:
            self._redo.append(self.state)
            self.state = replace(self._undo.pop(), revision=self.state.revision + 1)
        return self.state

    def redo(self, *, base_revision: int) -> EditorState:
        self._check_revision(base_revision)
        if self._redo:
            self._undo.append(self.state)
            self.state = replace(self._redo.pop(), revision=self.state.revision + 1)
        return self.state

    def payload(self) -> dict[str, object]:
        return {"format": "birdtracks-editor", "version": 1, "state": self.state.payload(),
                "undo": [s.payload() for s in self._undo], "redo": [s.payload() for s in self._redo]}

    @classmethod
    def decode(cls, payload: Mapping[str, object]) -> EditorSession:
        if payload.get("format") != "birdtracks-editor" or payload.get("version") != 1:
            raise ValueError("unsupported projector editor format")
        result = cls(EditorState.decode(payload["state"]))
        result._undo = [EditorState.decode(s) for s in payload.get("undo", ())]
        result._redo = [EditorState.decode(s) for s in payload.get("redo", ())]
        if any(s.term_id != result.state.term_id or s.node_ids != result.state.node_ids
               or s.strand_ids != result.state.strand_ids for s in (*result._undo, *result._redo)):
            raise ValueError("history must belong to the same editor occurrence")
        return result
