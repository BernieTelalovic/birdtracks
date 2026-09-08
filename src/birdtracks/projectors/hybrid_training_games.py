"""Canvas games for resolver and target-exposure training problems."""

from __future__ import annotations

from collections import Counter
import json
from os import PathLike
from pathlib import Path
from random import Random
from typing import Any, Literal

from .hybrid_simplification import (
    ExposureTarget,
    SATarget,
    StrandPath,
    find_sa_exposure_targets,
    find_sa_targets,
)
from .projector import NodePort, Projector
from .symmetrisers import Antisymmetriser, Symmetriser

DATASET_VERSION = 3
_SUPPORTED_DATASET_VERSIONS = frozenset({1, 2, DATASET_VERSION})
DEFAULT_MINIMUM_LINES = 4
DEFAULT_MAXIMUM_LINES = 24
DEFAULT_MINIMUM_LAYERS = 3
DEFAULT_MAXIMUM_LAYERS = 16
_REPOSITORY = Path(__file__).resolve().parents[3]
DEFAULT_RESOLVER_DATASET = _REPOSITORY / "dest" / "resolver-problems.json"
DEFAULT_EXPOSURE_DATASET = _REPOSITORY / "dest" / "exposure-problems.json"
ProblemKind = Literal["resolver", "exposure"]


def resolver_training_game(
    dataset: str | PathLike[str] = DEFAULT_RESOLVER_DATASET,
    *,
    style: dict[str, float | str] | None = None,
) -> object:
    """Collect projectors that already contain a ranked S/A target."""
    return _training_game("resolver", Path(dataset), style)


def exposure_training_game(
    dataset: str | PathLike[str] = DEFAULT_EXPOSURE_DATASET,
    *,
    style: dict[str, float | str] | None = None,
) -> object:
    """Collect projectors conditioned on a separated, obstructed S/A pair."""
    return _training_game("exposure", Path(dataset), style)


def random_resolver_problem(
    rng: Random | None = None,
    *,
    minimum_lines: int = DEFAULT_MINIMUM_LINES,
    maximum_lines: int = DEFAULT_MAXIMUM_LINES,
    minimum_layers: int = DEFAULT_MINIMUM_LAYERS,
    maximum_layers: int = DEFAULT_MAXIMUM_LAYERS,
    maximum_attempts: int = 256,
) -> tuple[Projector, SATarget]:
    """Generate a nonzero outermost S/A resolver problem."""
    random = rng or Random()
    _validate_generation_arguments(
        minimum_lines, maximum_lines, minimum_layers, maximum_layers,
        maximum_attempts, exposure=False,
    )
    for _ in range(maximum_attempts):
        layer_count = random.randint(
            minimum_layers, min(maximum_layers, maximum_lines)
        )
        line_count = random.randint(
            max(minimum_lines, layer_count), maximum_lines
        )
        projector = _random_resolver_candidate(
            random, line_count, layer_count
        )
        targets = find_sa_targets(projector)
        outer = next(
            (
                target for target in targets
                if set(target.nodes) == {0, len(projector.nodes) - 1}
            ),
            None,
        )
        if outer is not None and not _immediately_zero(projector):
            return projector, outer
    raise RuntimeError("could not generate a nonzero resolver problem")


def random_exposure_problem(
    rng: Random | None = None,
    *,
    minimum_lines: int = DEFAULT_MINIMUM_LINES,
    maximum_lines: int = DEFAULT_MAXIMUM_LINES,
    minimum_layers: int = DEFAULT_MINIMUM_LAYERS,
    maximum_layers: int = DEFAULT_MAXIMUM_LAYERS,
    maximum_attempts: int = 256,
) -> tuple[Projector, ExposureTarget]:
    """Generate a nonzero separated S/A target with only obstructed paths."""
    random = rng or Random()
    _validate_generation_arguments(
        minimum_lines, maximum_lines, minimum_layers, maximum_layers,
        maximum_attempts, exposure=True,
    )
    for _ in range(maximum_attempts):
        layer_count = random.randint(
            minimum_layers, min(maximum_layers, maximum_lines + 1)
        )
        required_lines = 4 if layer_count == 3 else layer_count - 1
        line_count = random.randint(
            max(minimum_lines, required_lines), maximum_lines
        )
        projector, nodes = _random_exposure_candidate(
            random, line_count, layer_count
        )
        target = next(
            (
                candidate for candidate in find_sa_exposure_targets(projector)
                if set(candidate.nodes) == set(nodes)
            ),
            None,
        )
        if (
            target is not None
            and not find_sa_targets(projector)
            and not _immediately_zero(projector)
        ):
            return projector, target
    raise RuntimeError("could not generate a nonzero exposure problem")


def load_resolver_problems(
    path: str | PathLike[str] = DEFAULT_RESOLVER_DATASET,
) -> tuple[tuple[Projector, SATarget], ...]:
    result = []
    for index, (projector, example, dataset_version) in enumerate(
        _load_problems(Path(path), "resolver")
    ):
        targets = find_sa_targets(projector)
        if not targets:
            raise ValueError("saved resolver problem no longer contains a target")
        if _immediately_zero(projector):
            raise ValueError("saved resolver problem is immediately zero")
        target_data = example.get("active_target")
        if target_data is None:
            # Version-1 examples selected the first deterministically ranked target.
            if dataset_version == 1:
                target = targets[0]
            else:
                raise ValueError(
                    f"resolver problem {index} has no active-target data"
                )
        else:
            try:
                target = _target_from_data(target_data)
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"resolver problem {index} has invalid active-target data"
                ) from exc
            if target not in targets:
                raise ValueError(
                    f"resolver problem {index} active target does not belong "
                    "to its projector"
                )
        result.append((projector, target))
    return tuple(result)


def load_exposure_problems(
    path: str | PathLike[str] = DEFAULT_EXPOSURE_DATASET,
) -> tuple[tuple[Projector, ExposureTarget], ...]:
    result = []
    for index, (projector, example, version) in enumerate(
        _load_problems(Path(path), "exposure")
    ):
        if _immediately_zero(projector):
            raise ValueError("saved exposure problem is immediately zero")
        if find_sa_targets(projector):
            raise ValueError("saved exposure problem already contains a target")
        targets = find_sa_exposure_targets(projector)
        if not targets:
            raise ValueError(
                f"exposure problem {index} has no separated obstructed target"
            )
        target_data = example.get("active_target")
        if target_data is None:
            if version < DATASET_VERSION:
                target = targets[0]
            else:
                raise ValueError(
                    f"exposure problem {index} has no active-target data"
                )
        else:
            try:
                target = _exposure_target_from_data(target_data)
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"exposure problem {index} has invalid active-target data"
                ) from exc
            if target not in targets:
                raise ValueError(
                    f"exposure problem {index} active target does not belong "
                    "to its projector"
                )
        result.append((projector, target))
    return tuple(result)


def hybrid_dataset_overview(path: str | PathLike[str]) -> dict[str, object]:
    """Summarize a resolver or exposure problem dataset."""
    dataset = _read_dataset(Path(path), None)
    lines: Counter[int] = Counter()
    layers: Counter[int] = Counter()
    targets: Counter[int] = Counter()
    for example in dataset["examples"]:
        summary = example["summary"]
        lines[int(summary["lines"])] += 1
        layers[int(summary["layers"])] += 1
        targets[int(summary["targets"])] += 1
    return {
        "kind": dataset["kind"],
        "count": len(dataset["examples"]),
        "lines": dict(sorted(lines.items())),
        "layers": dict(sorted(layers.items())),
        "targets": dict(sorted(targets.items())),
    }


def _training_game(
    kind: ProblemKind,
    destination: Path,
    style: dict[str, float | str] | None,
) -> object:
    try:
        import ipywidgets
    except ImportError as exc:
        raise ImportError(
            "the training games require: pip install 'birdtracks[notebook]'"
        ) from exc
    from .widget import projector_creator

    purpose = (
        "Draw a projector containing a direct S–A strand and another strand "
        "between them obstructed by S/As. The largest support-union target is saved."
        if kind == "resolver"
        else "Draw a projector with an S–A pair joined by an obstructed strand, "
        "no direct strand, and at least one complete layer between the pair."
    )
    status = ipywidgets.HTML()
    body = ipywidgets.VBox()
    container = ipywidgets.VBox((
        ipywidgets.HTML(f"<b>{kind.title()} training game</b> — {purpose}"),
        status,
        body,
    ))
    container.layout.width = "100%"

    def new_problem(message: str = "") -> None:
        canvas = projector_creator(style=style, detangler=False)
        recorded = False

        def record(saved_canvas: object) -> None:
            nonlocal recorded
            if recorded:
                return
            editors = saved_canvas._term_editors
            if len(editors) != 1:
                status.value = "Save exactly one projector."
                return
            projector = editors[0].projector
            targets = find_sa_targets(projector)
            exposure_targets = find_sa_exposure_targets(projector)
            has_s = any(isinstance(node, Symmetriser) for node in projector.nodes)
            has_a = any(isinstance(node, Antisymmetriser) for node in projector.nodes)
            if _immediately_zero(projector):
                status.value = "Immediately-zero projectors are not training data."
                return
            if kind == "resolver" and not targets:
                status.value = "No direct-plus-potential S–A target was found."
                return
            if kind == "exposure" and (
                targets or not exposure_targets or not (has_s and has_a)
            ):
                status.value = (
                    "Need a separated S–A pair with obstructed paths only."
                )
                return
            selected = (
                targets[0] if kind == "resolver" else exposure_targets[0]
            )
            _append_problem(destination, kind, {
                "state": editors[0].configuration.state(),
                "active_target": (
                    _target_to_data(selected)
                    if isinstance(selected, SATarget)
                    else _exposure_target_to_data(selected)
                ),
                "summary": {
                    "lines": len(projector.support),
                    "nodes": len(projector.nodes),
                    "layers": len(projector.layers),
                    "targets": (
                        len(targets)
                        if kind == "resolver" else len(exposure_targets)
                    ),
                    "selected_support_union": (
                        selected.support_union_size
                    ),
                },
            })
            recorded = True
            count = hybrid_dataset_overview(destination)["count"]
            new_problem(f"Saved example {count} to {destination}")

        canvas.on_save(record)
        body.children = (canvas,)
        status.value = message or _overview_text(destination, kind)

    new_problem()
    return container


def _load_problems(
    path: Path, kind: ProblemKind
) -> tuple[tuple[Projector, dict[str, Any], int], ...]:
    from .widget import _projector_from_state

    result = []
    dataset = _read_dataset(path, kind)
    dataset_version = int(dataset["version"])
    for index, example in enumerate(dataset["examples"]):
        state = example.get("state")
        if not isinstance(state, dict):
            raise ValueError(f"problem {index} has no canvas state")
        try:
            projector = _projector_from_state(
                state["graph"], state["port_orders"], state["boundary_orders"]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"problem {index} has invalid projector data") from exc
        example_version = int(example.get("schema_version", dataset_version))
        result.append((projector, example, example_version))
    return tuple(result)


def _target_to_data(target: SATarget) -> dict[str, object]:
    """Serialize the exact conditioned target, including its active strand."""
    if len(target.direct_paths) != 1:
        raise ValueError("a resolver target must have exactly one direct path")
    return {
        "symmetriser_node": target.symmetriser,
        "antisymmetriser_node": target.antisymmetriser,
        "support_union": sorted(target.support_union),
        "direct_path": _path_to_data(target.direct_paths[0]),
        "potential_paths": [
            _path_to_data(path) for path in target.potential_paths
        ],
    }


def _target_from_data(value: object) -> SATarget:
    """Deserialize an explicitly conditioned target for validation on load."""
    if not isinstance(value, dict):
        raise TypeError("active target must be an object")
    symmetriser = _plain_int(value["symmetriser_node"], "symmetriser node")
    antisymmetriser = _plain_int(
        value["antisymmetriser_node"], "antisymmetriser node"
    )
    raw_support = value["support_union"]
    raw_potential = value["potential_paths"]
    if not isinstance(raw_support, list):
        raise TypeError("target support union must be a list")
    if not isinstance(raw_potential, list) or not raw_potential:
        raise ValueError("target potential paths must be a non-empty list")
    return SATarget(
        symmetriser=symmetriser,
        antisymmetriser=antisymmetriser,
        support_union=frozenset(
            _plain_int(label, "support label") for label in raw_support
        ),
        direct_paths=(_path_from_data(value["direct_path"]),),
        potential_paths=tuple(_path_from_data(path) for path in raw_potential),
    )


def _exposure_target_to_data(target: ExposureTarget) -> dict[str, object]:
    """Serialize an exposure pair and every currently obstructed strand."""
    return {
        "symmetriser_node": target.symmetriser,
        "antisymmetriser_node": target.antisymmetriser,
        "support_union": sorted(target.support_union),
        "obstructed_paths": [
            _path_to_data(path) for path in target.obstructed_paths
        ],
    }


def _exposure_target_from_data(value: object) -> ExposureTarget:
    if not isinstance(value, dict):
        raise TypeError("active exposure target must be an object")
    raw_support = value["support_union"]
    raw_paths = value["obstructed_paths"]
    if not isinstance(raw_support, list):
        raise TypeError("target support union must be a list")
    if not isinstance(raw_paths, list) or not raw_paths:
        raise ValueError("target obstructed paths must be a non-empty list")
    return ExposureTarget(
        symmetriser=_plain_int(value["symmetriser_node"], "symmetriser node"),
        antisymmetriser=_plain_int(
            value["antisymmetriser_node"], "antisymmetriser node"
        ),
        support_union=frozenset(
            _plain_int(label, "support label") for label in raw_support
        ),
        obstructed_paths=tuple(_path_from_data(path) for path in raw_paths),
    )


def _path_to_data(path: StrandPath) -> dict[str, object]:
    if not isinstance(path, StrandPath):
        raise TypeError("target paths must be StrandPath objects")
    return {
        "source": [path.source.node, path.source.label],
        "target": [path.target.node, path.target.label],
        "intervening_nodes": list(path.intervening_nodes),
    }


def _path_from_data(value: object) -> StrandPath:
    if not isinstance(value, dict):
        raise TypeError("target path must be an object")
    return StrandPath(
        source=_port_from_data(value["source"]),
        target=_port_from_data(value["target"]),
        intervening_nodes=tuple(
            _plain_int(node, "intervening node")
            for node in _required_list(value, "intervening_nodes")
        ),
    )


def _port_from_data(value: object) -> NodePort:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("target port must be a two-item list")
    return NodePort(
        _plain_int(value[0], "port node"),
        _plain_int(value[1], "port label"),
    )


def _required_list(value: dict[str, object], key: str) -> list[object]:
    result = value[key]
    if not isinstance(result, list):
        raise TypeError(f"target {key} must be a list")
    return result


def _plain_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    return value


def _validate_generation_arguments(
    minimum_lines: int,
    maximum_lines: int,
    minimum_layers: int,
    maximum_layers: int,
    maximum_attempts: int,
    *,
    exposure: bool,
) -> None:
    values = {
        "minimum_lines": minimum_lines,
        "maximum_lines": maximum_lines,
        "minimum_layers": minimum_layers,
        "maximum_layers": maximum_layers,
        "maximum_attempts": maximum_attempts,
    }
    if any(isinstance(value, bool) or not isinstance(value, int)
           for value in values.values()):
        raise TypeError("generation bounds must be integers")
    if minimum_lines < 3 or maximum_lines < minimum_lines:
        raise ValueError("line bounds must be ordered and at least three")
    if minimum_layers < 3 or maximum_layers < minimum_layers:
        raise ValueError("layer bounds must be ordered and at least three")
    required_lines = (
        (4 if minimum_layers == 3 else minimum_layers - 1)
        if exposure else minimum_layers
    )
    if maximum_lines < required_lines:
        raise ValueError(
            "line maximum is too small for the requested layer minimum"
        )
    if isinstance(maximum_attempts, bool) or not isinstance(maximum_attempts, int):
        raise TypeError("maximum_attempts must be an integer")
    if maximum_attempts < 1:
        raise ValueError("maximum_attempts must be positive")


def _random_resolver_candidate(
    rng: Random, strand_count: int, layer_count: int
) -> Projector:
    labels = list(range(1, strand_count + 1))
    rng.shuffle(labels)
    direct, potential = labels[:2]
    helpers = labels[2:layer_count]
    remaining = labels[layer_count:]
    rng.shuffle(remaining)
    split = rng.randint(0, len(remaining))
    left_support = [direct, potential, *remaining[:split]]
    right_support = [direct, potential, *remaining[split:]]
    left_type = Symmetriser if rng.random() < 0.5 else Antisymmetriser
    right_type = (
        Antisymmetriser if left_type is Symmetriser else Symmetriser
    )
    nodes: list[Symmetriser | Antisymmetriser] = [
        left_type(_shuffled(left_support, rng))
    ]
    for helper in helpers:
        node_type = Symmetriser if rng.random() < 0.5 else Antisymmetriser
        nodes.append(node_type(_shuffled([potential, helper], rng)))
    nodes.append(right_type(_shuffled(right_support, rng)))
    return Projector(nodes)


def _random_exposure_candidate(
    rng: Random, strand_count: int, layer_count: int
) -> tuple[Projector, tuple[int, int]]:
    labels = list(range(1, strand_count + 1))
    rng.shuffle(labels)
    first_path, second_path = labels[:2]
    left_type = Symmetriser if rng.random() < 0.5 else Antisymmetriser
    right_type = (
        Antisymmetriser if left_type is Symmetriser else Symmetriser
    )
    if layer_count == 3:
        helper_labels = labels[2:4]
        remaining = labels[4:]
        middle_supports = [
            [first_path, helper_labels[0]],
            [second_path, helper_labels[1]],
        ]
    else:
        bridges = labels[2 : layer_count - 1]
        remaining = labels[layer_count - 1 :]
        middle_supports = [[first_path, bridges[0]]]
        middle_supports.extend(
            [left, right]
            for left, right in zip(bridges, bridges[1:])
        )
        middle_supports.append([bridges[-1], second_path])
    left_support = [first_path, second_path]
    right_support = [first_path, second_path]
    if len(remaining) == 1:
        middle_supports[0].append(remaining.pop())
    nodes: list[Symmetriser | Antisymmetriser] = [
        left_type(_shuffled(left_support, rng))
    ]
    for middle_index, support in enumerate(middle_supports):
        node_type = Symmetriser if rng.random() < 0.5 else Antisymmetriser
        nodes.append(node_type(_shuffled(support, rng)))
        if middle_index == 0:
            while remaining:
                width = min(len(remaining), rng.randint(2, 4))
                if len(remaining) - width == 1:
                    width += 1
                isolated = [remaining.pop() for _ in range(width)]
                isolated_type = (
                    Symmetriser if rng.random() < 0.5 else Antisymmetriser
                )
                nodes.append(isolated_type(_shuffled(isolated, rng)))
    nodes.append(right_type(_shuffled(right_support, rng)))
    return Projector(nodes), (0, len(nodes) - 1)


def _shuffled(values: list[int], rng: Random) -> tuple[int, ...]:
    result = list(values)
    rng.shuffle(result)
    return tuple(result)


def _immediately_zero(projector: Projector) -> bool:
    """Return whether the currently automatic exact identities annihilate it."""
    return not projector.simplify()


def _read_dataset(path: Path, kind: ProblemKind | None) -> dict[str, Any]:
    if not path.exists():
        if kind is None:
            raise FileNotFoundError(path)
        return {"format": "birdtracks-hybrid-training", "version": DATASET_VERSION,
                "kind": kind, "examples": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("format") != "birdtracks-hybrid-training"
        or value.get("version") not in _SUPPORTED_DATASET_VERSIONS
        or value.get("kind") not in {"resolver", "exposure"}
        or not isinstance(value.get("examples"), list)
        or (kind is not None and value.get("kind") != kind)
    ):
        raise ValueError(f"{path} is not a compatible {kind or 'hybrid'} dataset")
    return value


def _append_problem(path: Path, kind: ProblemKind, example: dict[str, object]) -> None:
    dataset = _read_dataset(path, kind)
    previous_version = int(dataset["version"])
    for existing in dataset["examples"]:
        existing.setdefault("schema_version", previous_version)
    example.setdefault("schema_version", DATASET_VERSION)
    dataset["version"] = DATASET_VERSION
    dataset["examples"].append(example)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(dataset, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def _overview_text(path: Path, kind: ProblemKind) -> str:
    dataset = _read_dataset(path, kind)
    return f"{len(dataset['examples'])} saved examples"


__all__ = [
    "DEFAULT_MAXIMUM_LAYERS",
    "DEFAULT_MAXIMUM_LINES",
    "DEFAULT_MINIMUM_LAYERS",
    "DEFAULT_MINIMUM_LINES",
    "DEFAULT_EXPOSURE_DATASET",
    "DEFAULT_RESOLVER_DATASET",
    "exposure_training_game",
    "hybrid_dataset_overview",
    "load_exposure_problems",
    "load_resolver_problems",
    "random_exposure_problem",
    "random_resolver_problem",
    "resolver_training_game",
]
