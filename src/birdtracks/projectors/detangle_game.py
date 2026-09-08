"""Notebook game for collecting human detangling demonstrations."""

from __future__ import annotations

from dataclasses import asdict
import json
from os import PathLike
from pathlib import Path
from random import Random
from typing import Any

from .detangle_training import DetangleState, random_projector
from .projector import Projector

DATASET_FORMAT = "birdtracks-detangler-demonstrations"
DATASET_VERSION = 2


def detangle_game(
    dataset: str | PathLike[str] = "dest/detangler-demonstrations.json",
    *,
    seed: int = 7,
    min_strands: int = 4,
    max_strands: int = 10,
    min_layers: int = 2,
    max_layers: int = 7,
    maximum_support: int = 4,
    style: dict[str, float | str] | None = None,
) -> Projector:
    """Open an endless evaluation canvas and save human before/after layouts.

    Move nodes, free lines, and ports in Evaluate mode, then press the canvas's
    normal Save button.  The demonstrated layout is appended to ``dataset`` and
    a new random problem replaces it.  Skip produces a new problem without
    recording an example.
    """
    _validate_bounds(min_strands, max_strands, min_layers, max_layers)
    try:
        import ipywidgets
    except ImportError as exc:
        raise ImportError(
            "the detangle game requires: pip install 'birdtracks[notebook]'"
        ) from exc

    destination = Path(dataset)
    rng = Random(seed)
    status = ipywidgets.HTML()
    skip = ipywidgets.Button(description="Skip", icon="forward")
    heading = ipywidgets.HTML(
        "<b>Human detangling game</b> — rearrange the diagram without changing "
        "its topology, then press <b>Save</b>."
    )
    body = ipywidgets.VBox()
    container = ipywidgets.VBox((heading, ipywidgets.HBox((skip, status)), body))
    container.layout.width = "100%"
    round_number = 0

    def new_round(message: str = "") -> None:
        nonlocal round_number
        round_number += 1
        round_seed = rng.randrange(2**63)
        round_rng = Random(round_seed)
        projector = _random_nonzero_projector(
            round_rng,
            min_strands=min_strands,
            max_strands=max_strands,
            min_layers=min_layers,
            max_layers=max_layers,
            maximum_support=maximum_support,
        )
        initial = DetangleState.random_layout(projector, round_rng)
        initial_configuration = initial.configuration(style)
        canvas = initial_configuration.evaluate(style=style, detangler=False)
        recorded = False

        def save_demonstration(saved_canvas: object) -> None:
            nonlocal recorded
            if recorded:
                return
            editors = saved_canvas._term_editors
            if len(editors) != 1:
                raise ValueError("detangle demonstrations must contain one term")
            final_configuration = editors[0].configuration
            final = DetangleState.from_configuration(final_configuration)
            if final.projector != initial.projector:
                raise ValueError("detangling changed the projector topology")
            _append_demonstration(
                destination,
                {
                    "round_seed": round_seed,
                    "initial": initial_configuration.state(),
                    "final": final_configuration.state(),
                    "initial_metrics": asdict(initial.metrics()),
                    "final_metrics": asdict(final.metrics()),
                },
            )
            recorded = True
            count = len(_read_dataset(destination)["examples"])
            new_round(f"Saved example {count} to {destination}")

        canvas.on_save(save_demonstration)
        body.children = (canvas,)
        status.value = message or f"Problem {round_number}"

    def skip_round(_button: object) -> None:
        new_round("Skipped; generated a new problem")

    skip.on_click(skip_round)
    new_round()
    return container


def _random_nonzero_projector(
    rng: Random,
    *,
    min_strands: int,
    max_strands: int,
    min_layers: int,
    max_layers: int,
    maximum_support: int,
    maximum_attempts: int = 256,
) -> object:
    """Sample until exact automatic identities do not annihilate the diagram."""
    for _attempt in range(maximum_attempts):
        projector = random_projector(
            rng,
            strands=rng.randint(min_strands, max_strands),
            layers=rng.randint(min_layers, max_layers),
            maximum_support=maximum_support,
        )
        if projector.simplify():
            return projector
    raise RuntimeError(
        f"failed to generate a nonzero detangling problem after "
        f"{maximum_attempts} attempts"
    )


def _read_dataset(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "format": DATASET_FORMAT,
            "version": DATASET_VERSION,
            "examples": [],
        }
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("format") != DATASET_FORMAT
        or value.get("version") not in {1, DATASET_VERSION}
        or not isinstance(value.get("examples"), list)
    ):
        raise ValueError(f"{path} is not a compatible detangling dataset")
    # Version 1 stored exact-layer layouts. Configuration replay below projects
    # those demonstrations onto the current visible S/A-column schema.
    value["version"] = DATASET_VERSION
    return value


def load_detangle_demonstrations(
    path: str | PathLike[str],
) -> tuple[tuple[DetangleState, DetangleState], ...]:
    """Load validated ``(initial, human-preferred)`` state pairs."""
    from .configuration import ProjectorConfiguration
    from .widget import _projector_from_state

    examples = _read_dataset(Path(path))["examples"]
    demonstrations: list[tuple[DetangleState, DetangleState]] = []
    for index, example in enumerate(examples):
        if not isinstance(example, dict):
            raise ValueError(f"demonstration {index} must be an object")
        states: list[DetangleState] = []
        for name in ("initial", "final"):
            saved = example.get(name)
            if not isinstance(saved, dict):
                raise ValueError(f"demonstration {index} has no {name} state")
            try:
                projector = _projector_from_state(
                    saved["graph"],
                    saved["port_orders"],
                    saved["boundary_orders"],
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"demonstration {index} has an invalid {name} state"
                ) from exc
            configuration = ProjectorConfiguration.from_state(projector, saved)
            states.append(DetangleState.from_configuration(configuration))
        initial, preferred = states
        if initial.projector != preferred.projector:
            raise ValueError(f"demonstration {index} changes projector topology")
        demonstrations.append((initial, preferred))
    return tuple(demonstrations)


def _append_demonstration(path: Path, example: dict[str, object]) -> None:
    dataset = _read_dataset(path)
    dataset["examples"].append(example)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(dataset, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _validate_bounds(
    min_strands: int,
    max_strands: int,
    min_layers: int,
    max_layers: int,
) -> None:
    if min_strands < 4 or min_strands > max_strands:
        raise ValueError("strand bounds must be ordered and at least four")
    if min_layers < 1 or min_layers > max_layers:
        raise ValueError("layer bounds must be ordered and positive")


__all__ = ["detangle_game", "load_detangle_demonstrations"]
