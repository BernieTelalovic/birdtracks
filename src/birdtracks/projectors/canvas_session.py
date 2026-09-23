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
_WHITEBOARD_FORMAT = "birdtracks-whiteboard"
_DEFAULT_DIRECTORY = "expressions"
_SESSION_SUFFIX = ".canvas.json"
_WHITEBOARD_SESSION_SUFFIX = ".whiteboard.json"
_EXPRESSION_ROOT_ENV = "BIRDTRACKS_EXPRESSION_ROOT"


def _resolve_canvas_session_path(path: str | PathLike[str]) -> Path:
    """Normalize the suffix and place bare names in the expression cache."""
    supplied = Path(path)
    is_bare_name = not supplied.name.endswith(
        (_SESSION_SUFFIX, _WHITEBOARD_SESSION_SUFFIX)
    )
    if is_bare_name:
        supplied = supplied.with_name(supplied.name + _SESSION_SUFFIX)
    if supplied.parent == Path("."):
        root = Path(os.environ.get(_EXPRESSION_ROOT_ENV, Path.cwd()))
        resolved = root / _DEFAULT_DIRECTORY / supplied.name
    else:
        resolved = supplied
    return resolved


@dataclass(frozen=True)
class ProjectorCanvasSession:
    """A traceable JSON sidecar capable of reopening a projector canvas."""

    path: Path
    _state: dict[str, Any]
    _environment: object

    @classmethod
    def load(cls, path: str | PathLike[str]) -> ProjectorCanvasSession:
        """Load and validate a saved canvas session."""
        from .whiteboard import (
            EvaluationEnvironment,
            WhiteboardSidecar,
            projector_backend,
            projector_codec,
        )

        resolved = _resolve_canvas_session_path(path)
        state = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError("projector canvas session must contain a JSON object")
        if state.get("format") == _WHITEBOARD_FORMAT:
            sidecar = WhiteboardSidecar.load(
                resolved,
                backend=projector_backend,
                codec=projector_codec,
            )
            state = sidecar.document
            _validate_canvas_state(state)
            return cls(resolved, state, sidecar.environment)
        if state.get("format") != _FORMAT:
            raise ValueError("file is not a birdtracks projector canvas session")
        _validate_legacy_canvas_state(state)
        return cls(resolved, state, EvaluationEnvironment(projector_backend))

    @property
    def environment(self) -> object:
        """Return the shared named-value environment restored with the canvas."""

        return self._environment

    def state(self) -> dict[str, Any]:
        """Return an independent copy of the serialized session state."""
        return deepcopy(self._state)

    def expression(self) -> object:
        """Return the active representation document or latest projector sum."""
        if self._state.get("create_kind") == "young":
            from ..young_diagrams import PairExpression

            return PairExpression.from_state(self._state["pair_expression"])
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


def _validate_legacy_canvas_state(state: dict[str, Any]) -> None:
    if state.get("version") != _VERSION:
        raise ValueError(
            f"unsupported projector canvas session version: {state.get('version')!r}"
        )
    _validate_canvas_state(state)


def _validate_canvas_state(state: dict[str, Any]) -> None:
    if state.get("mode") not in {"create", "evaluate"}:
        raise ValueError("projector canvas session has an invalid mode")
    if state.get("create_kind", "birdtracks") not in {"birdtracks", "young"}:
        raise ValueError("canvas session has an invalid create kind")
    if state.get("create_kind") == "young" and "pair_expression" not in state:
        raise ValueError("Young-diagram session must contain a pair expression")
    if "pair_expression" in state:
        from ..young_diagrams import PairExpression

        PairExpression.from_state(state["pair_expression"])
    if not isinstance(state.get("lines"), list) or not state["lines"]:
        raise ValueError("projector canvas session must contain equation lines")
    whiteboard = state.get("whiteboard", [])
    if not isinstance(whiteboard, list):
        raise ValueError("whiteboard state must be an array")
    for index, block in enumerate(whiteboard):
        if not isinstance(block, dict) or not isinstance(block.get("id"), str):
            raise ValueError(f"whiteboard block {index} must have a string id")
        if not isinstance(block.get("source"), str):
            raise ValueError(f"whiteboard block {index} must have string source")
        if block.get("kind") not in {None, "projector", "diagram"}:
            raise ValueError(
                f"whiteboard block {index} must be a projector or diagram line"
            )


def write_canvas_session(
    path: str | PathLike[str],
    state: dict[str, Any],
    *,
    environment: object | None = None,
) -> ProjectorCanvasSession:
    """Atomically replace a canvas sidecar with whiteboard-backed state."""
    from .whiteboard import (
        EvaluationEnvironment,
        projector_backend,
        projector_codec,
        write_sidecar,
    )

    if environment is None:
        environment = EvaluationEnvironment(projector_backend)
    if not isinstance(environment, EvaluationEnvironment):
        raise TypeError("canvas session environment must be an EvaluationEnvironment")
    resolved = _resolve_canvas_session_path(path)
    write_sidecar(
        resolved,
        environment,
        codec=projector_codec,
        document=state,
    )
    return ProjectorCanvasSession.load(resolved)


def load(path: str | PathLike[str]) -> object:
    """Load the latest exact expression from a canvas session."""
    expression = ProjectorCanvasSession.load(path).expression()
    from ..young_diagrams import PairExpression

    if isinstance(expression, PairExpression):
        return expression
    if len(expression) == 1:
        projector, coefficient = next(iter(expression))
        return coefficient * projector
    return expression


__all__ = ["ProjectorCanvasSession", "load"]
