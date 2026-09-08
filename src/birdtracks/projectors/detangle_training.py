"""Topology-safe states and random data for training a layout policy.

This module deliberately has no machine-learning dependency.  It defines the
legal insertion-move action space and its exact layout metrics; the executable
trainer in ``scripts/train_detangler.py`` supplies the optional PyTorch model.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot, log1p
from os import PathLike
from pathlib import Path
from random import Random
from typing import Any, Literal

from .projector import Connection, NodePort, Projector
from .symmetrisers import Antisymmetriser, Symmetriser

Unit = tuple[Literal["node", "free"], int]
ActionKind = Literal["stop", "layer", "input", "output"]
FEATURE_COUNT = 20
DETANGLER_SCHEMA_VERSION = 2


def _display_layers(projector: Projector) -> tuple[tuple[int, ...], ...]:
    """Return the S/A-only columns used by the current renderer."""
    from .display_graph import compile_display_graph

    return compile_display_graph(projector).operator_columns


def default_detangler_checkpoint() -> Path | None:
    """Return the source-tree default checkpoint when it has been trained."""
    candidate = Path(__file__).resolve().parents[3] / "dest" / "detangler.pt"
    return candidate if candidate.is_file() else None


@dataclass(frozen=True)
class DetangleAction:
    """Move one item to another legal slot without rewiring the graph."""

    kind: ActionKind
    owner: int = -1
    index: int = -1
    destination: int = -1


@dataclass(frozen=True)
class DetangleMetrics:
    """Visible line metrics accumulated over every inter-layer gap."""

    length: float
    crossings: int
    straight: int

    @property
    def loss(self) -> float:
        """Stable multiplicative training loss requested for detangling."""
        return (
            (1.0 + self.length)
            * (1.0 + self.crossings)
            / (1.0 + self.straight)
        )


@dataclass(frozen=True)
class DetangleState:
    """A projector plus topology-invariant vertical and port orderings."""

    projector: Projector
    layer_orders: tuple[tuple[Unit, ...], ...]
    port_orders: tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]

    @classmethod
    def from_projector(cls, projector: Projector) -> DetangleState:
        """Create a deterministic packed layout from existing port orders."""
        if not isinstance(projector, Projector):
            raise TypeError("projector must be a Projector")
        input_strands, _output_strands = _strand_labels(projector)
        layers: list[tuple[Unit, ...]] = []
        for layer in _display_layers(projector):
            active = {
                input_strands[NodePort(node_index, label)]
                for node_index in layer
                for label in projector.nodes[node_index].support
            }
            units: list[Unit] = [("node", index) for index in layer]
            units.extend(
                ("free", label)
                for label in sorted(projector.support - active)
            )
            layers.append(tuple(units))
        ports = tuple(
            (
                tuple(projector.port_orders[index]["input"]),
                tuple(projector.port_orders[index]["output"]),
            )
            for index in range(len(projector.nodes))
        )
        return cls(projector, tuple(layers), ports)

    @classmethod
    def random_layout(
        cls, projector: Projector, rng: Random | None = None
    ) -> DetangleState:
        """Create a randomized valid layout without changing topology."""
        random = rng or Random()
        input_strands, _output_strands = _strand_labels(projector)
        layers: list[tuple[Unit, ...]] = []
        for layer in _display_layers(projector):
            active = {
                input_strands[NodePort(node_index, label)]
                for node_index in layer
                for label in projector.nodes[node_index].support
            }
            units: list[Unit] = [("node", index) for index in layer]
            units.extend(
                ("free", label)
                for label in sorted(projector.support - active)
            )
            random.shuffle(units)
            layers.append(tuple(units))

        ports = []
        visible_nodes = {
            index for layer in _display_layers(projector) for index in layer
        }
        for node_index, node in enumerate(projector.nodes):
            input_order = list(node.labels)
            output_order = list(node.labels)
            if node_index in visible_nodes:
                random.shuffle(input_order)
                random.shuffle(output_order)
            ports.append((tuple(input_order), tuple(output_order)))
        return cls(projector, tuple(layers), tuple(ports))

    @classmethod
    def from_configuration(cls, configuration: object) -> DetangleState:
        """Recover a training state from an exactly saved canvas layout."""
        from .configuration import ProjectorConfiguration

        if not isinstance(configuration, ProjectorConfiguration):
            raise TypeError("configuration must be a ProjectorConfiguration")
        projector = configuration.projector
        state = configuration.state()
        geometry = state["graph"]["geometry"]
        positions = state["positions"]
        free_levels = state["free_levels"]
        top = float(geometry["top_line_level"])
        spacing = float(geometry["level_spacing"])
        layer_orders: list[tuple[Unit, ...]] = []
        for layer_index, layer in enumerate(_display_layers(projector)):
            ranked: list[tuple[int, Unit]] = []
            for node_index in layer:
                width = len(projector.nodes[node_index].support)
                centre = float(positions[str(node_index)]["y"])
                start = round((centre - top) / spacing - (width - 1) / 2)
                ranked.append((start, ("node", node_index)))
            exact_layer = int(state["graph"]["nodes"][layer[0]]["layer"])
            ranked.extend(
                (int(level), ("free", int(label)))
                for label, level in free_levels.get(str(exact_layer), {}).items()
            )
            ranked.sort(key=lambda item: (item[0], item[1]))
            layer_orders.append(tuple(unit for _level, unit in ranked))
        raw_ports = state["port_orders"]
        ports = tuple(
            (
                tuple(raw_ports[str(index)]["input"]),
                tuple(raw_ports[str(index)]["output"]),
            )
            for index in range(len(projector.nodes))
        )
        return cls(projector, tuple(layer_orders), ports)

    def legal_actions(self) -> tuple[DetangleAction, ...]:
        """Return every topology-preserving insertion move plus stop."""
        actions = [DetangleAction("stop")]
        for layer, units in enumerate(self.layer_orders):
            actions.extend(
                DetangleAction("layer", layer, index, destination)
                for index in range(len(units))
                for destination in range(len(units))
                if destination != index
            )
        visible_nodes = {
            value
            for units in self.layer_orders
            for kind, value in units
            if kind == "node"
        }
        for node_index, (inputs, outputs) in enumerate(self.port_orders):
            if node_index not in visible_nodes:
                continue
            actions.extend(
                DetangleAction("input", node_index, index, destination)
                for index in range(len(inputs))
                for destination in range(len(inputs))
                if destination != index
            )
            actions.extend(
                DetangleAction("output", node_index, index, destination)
                for index in range(len(outputs))
                for destination in range(len(outputs))
                if destination != index
            )
        return tuple(actions)

    def apply(self, action: DetangleAction) -> DetangleState:
        """Apply a legal action, retaining the identical Projector object."""
        if action not in self.legal_actions():
            raise ValueError("action is not legal for this detangle state")
        return self._apply_known_legal(action)

    def _apply_known_legal(self, action: DetangleAction) -> DetangleState:
        if action.kind == "stop":
            return self
        layers = [list(units) for units in self.layer_orders]
        ports = [[list(inputs), list(outputs)] for inputs, outputs in self.port_orders]
        if action.kind == "layer":
            order = layers[action.owner]
        else:
            order = ports[action.owner][0 if action.kind == "input" else 1]
        moved = order.pop(action.index)
        order.insert(action.destination, moved)
        return DetangleState(
            self.projector,
            tuple(tuple(units) for units in layers),
            tuple((tuple(inputs), tuple(outputs)) for inputs, outputs in ports),
        )

    def metrics(self) -> DetangleMetrics:
        """Measure the complete visible route of every boundary strand."""
        projector = self.projector
        from .display_graph import compile_display_graph

        display = compile_display_graph(projector)
        input_strands, output_strands = _strand_labels(projector)
        interfaces: list[tuple[dict[int, int], dict[int, int]]] = []
        for units in self.layer_orders:
            inputs: dict[int, int] = {}
            outputs: dict[int, int] = {}
            cursor = 0
            for kind, value in units:
                if kind == "free":
                    inputs[value] = outputs[value] = cursor
                    cursor += 1
                    continue
                node = projector.nodes[value]
                input_order, output_order = self.port_orders[value]
                for offset, label in enumerate(input_order):
                    inputs[input_strands[NodePort(value, label)]] = cursor + offset
                for offset, label in enumerate(output_order):
                    outputs[output_strands[NodePort(value, label)]] = cursor + offset
                cursor += len(node.support)
            interfaces.append((inputs, outputs))

        labels = sorted(projector.support)
        boundary_rank = {label: index for index, label in enumerate(labels)}
        output_boundary = {
            output_strands[port]: boundary_rank[label]
            for label, port in projector.output_boundary.items()
        }
        gaps: list[tuple[dict[int, int], dict[int, int]]] = []
        if interfaces:
            gaps.append((boundary_rank, interfaces[-1][0]))
            for right, left in zip(reversed(interfaces[1:]), reversed(interfaces[:-1])):
                gaps.append((right[1], left[0]))
            gaps.append((interfaces[0][1], output_boundary))
        else:
            gaps.append((boundary_rank, output_boundary))

        length = 0.0
        crossings = 0
        straight = 0
        corridor_widths = tuple(
            1.0 + 0.2 * min(1.0, complexity / 6.0)
            for complexity in reversed(display.corridor_complexities)
        )
        for (right, left), horizontal in zip(
            gaps, corridor_widths, strict=True
        ):
            strands = sorted(right, key=lambda label: (right[label], label))
            destinations = [left[label] for label in strands]
            length += sum(
                hypot(horizontal, right[label] - left[label]) for label in strands
            )
            straight += sum(right[label] == left[label] for label in strands)
            crossings += sum(
                first > second
                for index, first in enumerate(destinations)
                for second in destinations[index + 1 :]
            )
        return DetangleMetrics(length, crossings, straight)

    def action_features(
        self,
        action: DetangleAction,
        candidate_metrics: DetangleMetrics | None = None,
    ) -> tuple[float, ...]:
        """Return fixed-size features for ranking the candidate move."""
        if candidate_metrics is None:
            if action not in self.legal_actions():
                raise ValueError("action is not legal for this detangle state")
            metrics = self._apply_known_legal(action).metrics()
        else:
            metrics = candidate_metrics
        strands = max(1, len(self.projector.support))
        layers = max(1, len(self.layer_orders))
        gaps = layers + 1
        pairs = max(1, strands * (strands - 1) // 2)
        kinds = tuple(float(action.kind == kind) for kind in (
            "stop", "layer", "input", "output"
        ))
        owner_scale = (
            layers
            if action.kind == "layer"
            else max(1, len(self.projector.nodes))
        )
        order_size = 1
        left_width = right_width = 0
        left_node = right_node = 0.0
        if action.kind == "layer":
            order = self.layer_orders[action.owner]
            order_size = len(order)
            moved = order[action.index]
            displaced = order[action.destination]
            left_width = _unit_width(self.projector, moved)
            right_width = _unit_width(self.projector, displaced)
            left_node = float(moved[0] == "node")
            right_node = float(displaced[0] == "node")
        elif action.kind in {"input", "output"}:
            order = self.port_orders[action.owner][0 if action.kind == "input" else 1]
            order_size = len(order)
            left_width = right_width = 1
            left_node = right_node = 1.0
        visible_node_count = sum(
            kind == "node" for units in self.layer_orders for kind, _value in units
        )
        return (
            metrics.length / (strands * gaps),
            metrics.crossings / (pairs * gaps),
            metrics.straight / (strands * gaps),
            log1p(metrics.loss),
            strands / 16.0,
            layers / 8.0,
            visible_node_count / 32.0,
            *kinds,
            max(0, action.owner) / owner_scale,
            max(0, action.index) / max(1, order_size - 1),
            max(0, action.destination) / max(1, order_size - 1),
            (
                (action.destination - action.index) / max(1, order_size - 1)
                if action.kind != "stop"
                else 0.0
            ),
            left_width / strands,
            right_width / strands,
            left_node,
            right_node,
            order_size / strands,
        )

    def value_features(self) -> tuple[float, ...]:
        """Return layout-only features for a learned preference value."""
        return self.action_features(DetangleAction("stop"), self.metrics())

    def configured_projector(self) -> Projector:
        """Apply port orders, moving antisymmetric parity into the coefficient."""
        original = self.projector
        unit = Projector(
            original.nodes,
            original.connections,
            input_boundary=original.input_boundary,
            output_boundary=original.output_boundary,
            port_orders={
                index: {"input": inputs, "output": outputs}
                for index, (inputs, outputs) in enumerate(self.port_orders)
            },
        )
        result = unit * (
            original.canonical_coefficient / unit.canonical_coefficient
        )
        if result != original:
            raise AssertionError("learned layout changed projector topology")
        return result

    def configuration(
        self, style: dict[str, float | str] | None = None
    ) -> object:
        """Return an exactly replayable canvas configuration for this state."""
        from .configuration import ProjectorConfiguration
        from .layout import widget_graph

        projector = self.configured_projector()
        graph = widget_graph(projector, style)
        geometry = graph["geometry"]
        assert isinstance(geometry, dict)
        positions: dict[str, dict[str, float]] = {}
        free_levels: dict[str, dict[str, int]] = {}
        display_layers = _display_layers(projector)
        for layer, units in enumerate(self.layer_orders):
            cursor = 0
            exact_layer = int(graph["nodes"][display_layers[layer][0]]["layer"])
            free_levels[str(exact_layer)] = {}
            for kind, value in units:
                if kind == "free":
                    free_levels[str(exact_layer)][str(value)] = cursor
                    cursor += 1
                    continue
                width = len(projector.nodes[value].support)
                positions[str(value)] = {
                    "x": float(
                        geometry["first_layer_x"]
                        + geometry["layer_step"] * layer
                    ),
                    "y": float(
                        geometry["top_line_level"]
                        + geometry["level_spacing"]
                        * (cursor + (width - 1) / 2)
                    ),
                }
                cursor += width
        port_orders = {
            str(index): {
                "input": list(inputs),
                "output": list(outputs),
            }
            for index, (inputs, outputs) in enumerate(self.port_orders)
        }
        boundary_order = sorted(projector.support)
        return ProjectorConfiguration.from_state(
            projector,
            {
                "graph": graph,
                "positions": positions,
                "port_orders": port_orders,
                "free_levels": free_levels,
                "boundary_orders": {
                    "input": boundary_order,
                    "output": boundary_order,
                },
                "effective_coefficient": graph["coefficient"],
            },
        )


@dataclass(frozen=True)
class DetangleSearchResult:
    """Best state found by an exact, topology-preserving layout search."""

    state: DetangleState
    initial_metrics: DetangleMetrics
    actions: tuple[DetangleAction, ...]
    optimal_first_actions: tuple[DetangleAction, ...] = ()

    @property
    def metrics(self) -> DetangleMetrics:
        return self.state.metrics()


def greedy_detangle(
    state: DetangleState,
    *,
    max_moves: int = 256,
    tolerance: float = 1e-12,
) -> DetangleSearchResult:
    """Repeatedly apply the legal move with the lowest exact current loss."""
    _validate_search_arguments(max_moves=max_moves, tolerance=tolerance)
    initial = state.metrics()
    chosen: list[DetangleAction] = []
    for _ in range(max_moves):
        current_loss = state.metrics().loss
        candidates = (
            (state._apply_known_legal(action), action)
            for action in state.legal_actions()
            if action.kind != "stop"
        )
        best_state, best_action = min(
            candidates,
            key=lambda item: (
                item[0].metrics().loss,
                _action_key(item[1]),
            ),
            default=(state, DetangleAction("stop")),
        )
        if best_state.metrics().loss >= current_loss - tolerance:
            break
        state = best_state
        chosen.append(best_action)
    return DetangleSearchResult(state, initial, tuple(chosen))


def beam_search_detangle(
    state: DetangleState,
    *,
    depth: int = 3,
    beam_width: int = 16,
    tolerance: float = 1e-12,
) -> DetangleSearchResult:
    """Find a low-loss layout using bounded lookahead over legal moves.

    The returned ``optimal_first_actions`` contains every first action tied for
    the best score among the states actually explored.  It is therefore useful
    as a tie-aware classification target without imposing an arbitrary action
    ordering on visually equivalent moves.
    """
    _validate_search_arguments(
        max_moves=depth, tolerance=tolerance, beam_width=beam_width
    )
    initial = state.metrics()
    stop = DetangleAction("stop")
    best_loss = initial.loss
    best_records: list[tuple[DetangleState, tuple[DetangleAction, ...]]] = [
        (state, ())
    ]
    frontier: list[tuple[DetangleState, tuple[DetangleAction, ...]]] = [
        (state, ())
    ]
    visited = {state}

    for _ in range(depth):
        generated: list[
            tuple[DetangleState, tuple[DetangleAction, ...], float]
        ] = []
        for current, path in frontier:
            for action in current.legal_actions():
                if action.kind == "stop":
                    continue
                candidate = current._apply_known_legal(action)
                if candidate in visited:
                    continue
                visited.add(candidate)
                candidate_path = (*path, action)
                loss = candidate.metrics().loss
                generated.append((candidate, candidate_path, loss))
                if loss < best_loss - tolerance:
                    best_loss = loss
                    best_records = [(candidate, candidate_path)]
                elif abs(loss - best_loss) <= tolerance:
                    best_records.append((candidate, candidate_path))
        if not generated:
            break
        generated.sort(
            key=lambda item: (
                item[2],
                tuple(_action_key(action) for action in item[1]),
            )
        )
        frontier = [
            (candidate, path)
            for candidate, path, _loss in generated[:beam_width]
        ]

    best_records.sort(
        key=lambda item: tuple(_action_key(action) for action in item[1])
    )
    best_state, best_path = best_records[0]
    first_actions = {
        path[0] if path else stop for _candidate, path in best_records
    }
    return DetangleSearchResult(
        best_state,
        initial,
        best_path,
        tuple(sorted(first_actions, key=_action_key)),
    )


def _validate_search_arguments(
    *,
    max_moves: int,
    tolerance: float,
    beam_width: int | None = None,
) -> None:
    if isinstance(max_moves, bool) or not isinstance(max_moves, int):
        raise TypeError("search depth/max_moves must be an integer")
    if max_moves < 0:
        raise ValueError("search depth/max_moves cannot be negative")
    if tolerance < 0:
        raise ValueError("search tolerance cannot be negative")
    if beam_width is not None and (
        isinstance(beam_width, bool)
        or not isinstance(beam_width, int)
        or beam_width < 1
    ):
        raise ValueError("beam_width must be a positive integer")


def _action_key(action: DetangleAction) -> tuple[str, int, int, int]:
    return action.kind, action.owner, action.index, action.destination


@dataclass(frozen=True)
class LearnedDetangleResult:
    """The learned layout and enough diagnostics to judge its improvement."""

    state: DetangleState
    initial_metrics: DetangleMetrics
    steps: int

    @property
    def metrics(self) -> DetangleMetrics:
        return self.state.metrics()

    @property
    def projector(self) -> Projector:
        return self.state.configured_projector()

    def configuration(
        self, style: dict[str, float | str] | None = None
    ) -> object:
        return self.state.configuration(style)

    def evaluate(
        self,
        *,
        style: dict[str, float | str] | None = None,
        session: str | PathLike[str] | None = None,
    ) -> object:
        """Open the learned layout directly in an evaluation canvas."""
        return self.configuration(style).evaluate(session=session)


class LearnedDetangler:
    """A loaded PyTorch policy which applies topology-preserving legal moves."""

    __slots__ = ("_model", "checkpoint", "metadata")

    def __init__(
        self, model: Any, checkpoint: Path, metadata: dict[str, object]
    ) -> None:
        self._model = model
        self.checkpoint = checkpoint
        self.metadata = metadata

    @classmethod
    def load(
        cls, checkpoint: str | PathLike[str], *, device: str = "cpu"
    ) -> LearnedDetangler:
        """Load and validate a checkpoint produced by the training script."""
        try:
            import torch
            from torch import nn
        except ImportError as exc:
            raise ImportError(
                "learned detangling requires: pip install 'birdtracks[training]'"
            ) from exc
        resolved = Path(checkpoint)
        payload = torch.load(
            resolved, map_location=device, weights_only=True
        )
        if not isinstance(payload, dict) or not isinstance(
            payload.get("model_state"), dict
        ):
            raise ValueError("file is not a birdtracks detangler checkpoint")
        feature_count = int(payload.get("feature_count", -1))
        hidden = int(payload.get("hidden", -1))
        depth = int(payload.get("depth", -1))
        schema_version = int(payload.get("detangler_schema_version", -1))
        if (
            feature_count != FEATURE_COUNT
            or schema_version != DETANGLER_SCHEMA_VERSION
            or hidden < 1
            or depth < 1
        ):
            raise ValueError(
                "detangler checkpoint uses an incompatible action schema; "
                "retrain it with the current train_detangler.py"
            )
        layers: list[Any] = [nn.Linear(feature_count, hidden), nn.ReLU()]
        for _ in range(depth - 1):
            layers.extend((nn.Linear(hidden, hidden), nn.ReLU()))
        layers.append(nn.Linear(hidden, 1))
        model = nn.Sequential(*layers).to(device)
        model.load_state_dict(payload["model_state"])
        model.eval()
        metadata = {
            key: value for key, value in payload.items() if key != "model_state"
        }
        metadata["device"] = device
        return cls(model, resolved, metadata)

    def optimize(
        self,
        projector: Projector,
        *,
        max_moves: int = 256,
        state: DetangleState | None = None,
    ) -> LearnedDetangleResult:
        """Apply predicted topology-preserving moves to a stopping state."""
        if isinstance(max_moves, bool) or not isinstance(max_moves, int):
            raise TypeError("max_moves must be an integer")
        if max_moves < 0:
            raise ValueError("max_moves cannot be negative")
        if state is None:
            state = DetangleState.from_projector(projector)
        elif state.projector != projector:
            raise ValueError("initial state belongs to a different projector")
        initial = state.metrics()
        if self.metadata.get("model_kind") == "layout_value_v1":
            return self._optimize_value(state, initial, max_moves)
        steps = 0
        best_state = state
        best_loss = initial.loss
        visited = {state}
        oracle = self.metadata.get("oracle", {})
        allow_lookahead = (
            isinstance(oracle, dict)
            and oracle.get("kind") == "beam_search"
            and int(oracle.get("depth", 1)) > 1
        )
        try:
            import torch
        except ImportError as exc:  # pragma: no cover - load already checks this
            raise ImportError("learned detangling requires PyTorch") from exc
        with torch.inference_mode():
            for _ in range(max_moves):
                actions = state.legal_actions()
                candidates = tuple(
                    state._apply_known_legal(action) for action in actions
                )
                candidate_metrics = tuple(
                    candidate.metrics() for candidate in candidates
                )
                features = torch.tensor(
                    [
                        state.action_features(action, metrics)
                        for action, metrics in zip(
                            actions, candidate_metrics, strict=True
                        )
                    ],
                    dtype=torch.float32,
                    device=next(self._model.parameters()).device,
                )
                logits = self._model(features).squeeze(-1)
                for index, (action, candidate) in enumerate(
                    zip(actions, candidates, strict=True)
                ):
                    if action.kind != "stop" and candidate in visited:
                        logits[index] = float("-inf")
                selected = int(logits.argmax().item())
                action = actions[selected]
                candidate = candidates[selected]
                if action.kind == "stop":
                    break
                if (
                    not allow_lookahead
                    and candidate_metrics[selected].loss >= state.metrics().loss
                ):
                    break
                state = candidate
                visited.add(state)
                steps += 1
                if candidate_metrics[selected].loss < best_loss:
                    best_state = state
                    best_loss = candidate_metrics[selected].loss
        return LearnedDetangleResult(best_state, initial, steps)

    def _optimize_value(
        self,
        state: DetangleState,
        initial: DetangleMetrics,
        max_moves: int,
    ) -> LearnedDetangleResult:
        """Ascend learned layout value without prescribing a move sequence."""
        import torch

        visited = {state}
        steps = 0
        with torch.inference_mode():
            for _ in range(max_moves):
                actions = state.legal_actions()
                candidates = tuple(
                    state._apply_known_legal(action) for action in actions
                )
                features = torch.tensor(
                    [candidate.value_features() for candidate in candidates],
                    dtype=torch.float32,
                    device=next(self._model.parameters()).device,
                )
                values = self._model(features).squeeze(-1)
                for index, (action, candidate) in enumerate(
                    zip(actions, candidates, strict=True)
                ):
                    if action.kind != "stop" and candidate in visited:
                        values[index] = float("-inf")
                selected = int(values.argmax().item())
                if actions[selected].kind == "stop":
                    break
                state = candidates[selected]
                visited.add(state)
                steps += 1
        return LearnedDetangleResult(state, initial, steps)

    __call__ = optimize


def random_projector(
    rng: Random | None = None,
    *,
    strands: int = 8,
    layers: int = 4,
    maximum_support: int = 4,
) -> Projector:
    """Generate a valid layered S/A graph with arbitrary strand connections."""
    if strands < 4:
        raise ValueError("random training projectors require at least four strands")
    if layers < 1:
        raise ValueError("layers must be positive")
    if maximum_support < 2:
        raise ValueError("maximum_support must be at least two")
    random = rng or Random()
    labels = list(range(1, strands + 1))
    nodes = []
    occurrences: dict[int, list[NodePort]] = {label: [] for label in labels}

    for layer in range(layers):
        active = labels[:] if layer == 0 else [1, *(
            label for label in labels[1:] if random.random() < 0.75
        )]
        if len(active) < 2:
            active.append(random.choice(labels[1:]))
        random.shuffle(active)
        if active[0] != 1:
            active.remove(1)
            active.insert(0, 1)
        groups = _random_partition(active, maximum_support, random)
        port_to_strand = dict(
            zip(active, random.sample(labels, len(active)), strict=True)
        )
        layer_nodes: dict[int, int] = {}
        for group in groups:
            node_index = len(nodes)
            node_type = Symmetriser if random.random() < 0.5 else Antisymmetriser
            nodes.append(node_type(group))
            for port_label in group:
                layer_nodes[port_label] = node_index
                occurrences[port_to_strand[port_label]].append(
                    NodePort(node_index, port_label)
                )

    connections = []
    input_boundary = {}
    output_boundary = {}
    for strand, ports in occurrences.items():
        if not ports:
            raise AssertionError("the first random layer must cover every strand")
        output_boundary[strand] = ports[0]
        input_boundary[strand] = ports[-1]
        connections.extend(
            Connection(right, left)
            for left, right in zip(ports, ports[1:])
        )
    projector = Projector(
        nodes,
        connections,
        input_boundary=input_boundary,
        output_boundary=output_boundary,
    )
    if len(projector.layers) != layers:
        raise AssertionError("random generator failed to preserve requested layers")
    return projector


def _random_partition(
    values: list[int], maximum: int, rng: Random
) -> list[tuple[int, ...]]:
    groups: list[list[int]] = []
    cursor = 0
    while cursor < len(values):
        remaining = len(values) - cursor
        size = remaining if remaining <= maximum else rng.randint(2, maximum)
        if remaining - size == 1 and size < maximum:
            size += 1
        groups.append(values[cursor : cursor + size])
        cursor += size
    return [tuple(group) for group in groups]


def _strand_labels(
    projector: Projector,
) -> tuple[dict[NodePort, int], dict[NodePort, int]]:
    next_port = {
        connection.source: connection.target
        for connection in projector.connections
    }
    inputs: dict[NodePort, int] = {}
    outputs: dict[NodePort, int] = {}
    for boundary_label, start in projector.input_boundary.items():
        current = start
        while True:
            inputs[current] = boundary_label
            node = projector.nodes[current.node]
            output = NodePort(
                current.node,
                node.permutation(current.label)
                if hasattr(node, "permutation")
                else current.label,
            )
            outputs[output] = boundary_label
            target = next_port.get(output)
            if target is None:
                break
            current = target
    return inputs, outputs


def _unit_width(projector: Projector, unit: Unit) -> int:
    return len(projector.nodes[unit[1]].support) if unit[0] == "node" else 1


__all__ = [
    "DetangleAction",
    "DetangleMetrics",
    "DetangleSearchResult",
    "DetangleState",
    "FEATURE_COUNT",
    "DETANGLER_SCHEMA_VERSION",
    "LearnedDetangler",
    "LearnedDetangleResult",
    "beam_search_detangle",
    "default_detangler_checkpoint",
    "greedy_detangle",
    "random_projector",
]
