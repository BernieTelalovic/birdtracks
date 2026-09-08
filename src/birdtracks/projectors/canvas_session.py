"""Durable, versioned state for projector canvases."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import os
from os import PathLike
from pathlib import Path
from typing import Any


_FORMAT = "birdtracks-projector-canvas"
_VERSION = 1
_DEFAULT_DIRECTORY = "expressions"
_SESSION_SUFFIX = ".canvas.json"
_EXPRESSION_ROOT_ENV = "BIRDTRACKS_EXPRESSION_ROOT"


def _resolve_canvas_session_path(path: str | PathLike[str]) -> Path:
    """Normalize the suffix and place bare names in the expression cache."""
    supplied = Path(path)
    if not supplied.name.endswith(_SESSION_SUFFIX):
        supplied = supplied.with_name(supplied.name + _SESSION_SUFFIX)
    if supplied.parent == Path("."):
        root = Path(os.environ.get(_EXPRESSION_ROOT_ENV, Path.cwd()))
        return root / _DEFAULT_DIRECTORY / supplied.name
    return supplied


@dataclass(frozen=True)
class ProjectorCanvasSession:
    """A traceable JSON sidecar capable of reopening a projector canvas."""

    path: Path
    _state: dict[str, Any]

    @classmethod
    def load(cls, path: str | PathLike[str]) -> ProjectorCanvasSession:
        """Load and validate a saved canvas session."""
        resolved = _resolve_canvas_session_path(path)
        state = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError("projector canvas session must contain a JSON object")
        if state.get("format") != _FORMAT:
            raise ValueError("file is not a birdtracks projector canvas session")
        if state.get("version") != _VERSION:
            raise ValueError(
                f"unsupported projector canvas session version: {state.get('version')!r}"
            )
        if state.get("mode") not in {"create", "evaluate"}:
            raise ValueError("projector canvas session has an invalid mode")
        if not isinstance(state.get("lines"), list) or not state["lines"]:
            raise ValueError("projector canvas session must contain equation lines")
        return cls(resolved, state)

    def state(self) -> dict[str, Any]:
        """Return an independent copy of the serialized session state."""
        return deepcopy(self._state)

    def expression(self) -> object:
        """Return the exact projector sum on the saved canvas's latest line."""
        from .projector_sum import ProjectorSum
        from .widget import _projector_from_state

        terms: list[object] = []
        for term in self._state["lines"][-1]["terms"]:
            state = term["state"]
            projector = _projector_from_state(
                state["graph"], state["port_orders"], state["boundary_orders"]
            )
            terms.append(int(term["sign"]) * projector)
        return ProjectorSum(terms)

    def open(
        self,
        *,
        style: str | PathLike[str] | None = None,
        detangler: str | PathLike[str] | object | None = None,
        debug: bool = False,
    ) -> object:
        """Open this saved session as a live projector canvas."""
        from .widget import projector_canvas_from_session

        return projector_canvas_from_session(
            self, style=style, detangler=detangler, debug=debug
        )


def write_canvas_session(
    path: str | PathLike[str], state: dict[str, Any]
) -> ProjectorCanvasSession:
    """Atomically replace a canvas sidecar with validated JSON state."""
    resolved = _resolve_canvas_session_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    document = {"format": _FORMAT, "version": _VERSION, **state}
    temporary = resolved.with_name(f".{resolved.name}.tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(resolved)
    return ProjectorCanvasSession.load(resolved)


def load(path: str | PathLike[str]) -> object:
    """Load the latest exact expression from a canvas session."""
    expression = ProjectorCanvasSession.load(path).expression()
    if len(expression) == 1:
        projector, coefficient = next(iter(expression))
        return coefficient * projector
    return expression


__all__ = ["ProjectorCanvasSession", "load"]
