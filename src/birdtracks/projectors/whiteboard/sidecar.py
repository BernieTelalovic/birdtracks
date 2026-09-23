"""Versioned sidecar persistence for renderer-independent whiteboard state."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import os
from os import PathLike
from pathlib import Path
from typing import Any, Generic, TypeVar

from .engine import EvaluationEnvironment
from .protocol import AlgebraBackend, ValueCodec


ValueT = TypeVar("ValueT")
_FORMAT = "birdtracks-whiteboard"
_VERSION = 1
_DEFAULT_DIRECTORY = "expressions"
_SIDECAR_SUFFIX = ".whiteboard"
_LEGACY_SIDECAR_SUFFIX = ".whiteboard.json"
_EXPLICIT_JSON_SUFFIX = ".json"
_EXPRESSION_ROOT_ENV = "BIRDTRACKS_EXPRESSION_ROOT"
_TYPED_VERSION = 2


def resolve_sidecar_path(path: str | PathLike[str]) -> Path:
    """Normalize a whiteboard sidecar path and its default directory."""

    supplied = Path(path)
    if not supplied.name.endswith(
        (_SIDECAR_SUFFIX, _LEGACY_SIDECAR_SUFFIX)
    ) and supplied.suffix != _EXPLICIT_JSON_SUFFIX:
        supplied = supplied.with_name(supplied.name + _SIDECAR_SUFFIX)
    if supplied.parent == Path("."):
        root = Path(os.environ.get(_EXPRESSION_ROOT_ENV, Path.cwd()))
        return root / _DEFAULT_DIRECTORY / supplied.name
    return supplied


@dataclass(frozen=True)
class WhiteboardSidecar(Generic[ValueT]):
    """Loaded sidecar state with a reconstructed symbol environment."""

    path: Path
    environment: EvaluationEnvironment[ValueT]
    _document: dict[str, Any]

    @property
    def document(self) -> dict[str, Any]:
        """Return an independent copy of frontend-owned document state."""

        return deepcopy(self._document)

    @classmethod
    def load(
        cls,
        path: str | PathLike[str],
        *,
        backend: AlgebraBackend[ValueT],
        codec: ValueCodec[ValueT],
    ) -> WhiteboardSidecar[ValueT]:
        """Load and validate a sidecar using the selected backend and codec."""

        resolved = resolve_sidecar_path(path)
        state = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError("whiteboard sidecar must contain a JSON object")
        if state.get("format") != _FORMAT:
            raise ValueError("file is not a birdtracks whiteboard sidecar")
        if state.get("version") != _VERSION:
            raise ValueError(
                f"unsupported whiteboard sidecar version: {state.get('version')!r}"
            )
        if state.get("backend") != backend.name:
            raise ValueError("whiteboard sidecar was created for another backend")
        if state.get("codec") != codec.name:
            raise ValueError("whiteboard sidecar was created for another value codec")
        definitions = state.get("definitions")
        if not isinstance(definitions, list):
            raise ValueError("whiteboard sidecar definitions must be an array")
        if not isinstance(state.get("document", {}), dict):
            raise ValueError("whiteboard sidecar document must be an object")

        environment = EvaluationEnvironment(backend)
        for index, item in enumerate(definitions):
            if not isinstance(item, dict):
                raise ValueError(f"definition {index} must be a JSON object")
            name = item.get("name")
            if not isinstance(name, str):
                raise ValueError(f"definition {index} has an invalid name")
            if "value" not in item:
                raise ValueError(f"definition {index} has no value")
            environment.define(name, codec.decode(item["value"]))
        return cls(resolved, environment, deepcopy(state.get("document", {})))


@dataclass(frozen=True)
class WhiteboardStores:
    """The independent projector and diagram environments of one whiteboard."""

    projectors: EvaluationEnvironment[object]
    diagrams: EvaluationEnvironment[object]


@dataclass(frozen=True)
class TypedWhiteboardSidecar:
    """Loaded whiteboard state with separate typed value stores."""

    path: Path
    stores: WhiteboardStores
    _document: dict[str, Any]

    @property
    def document(self) -> dict[str, Any]:
        """Return an independent copy of frontend-owned document state."""

        return deepcopy(self._document)

    @classmethod
    def load(
        cls,
        path: str | PathLike[str],
        *,
        projector_backend: AlgebraBackend[object],
        projector_codec: ValueCodec[object],
        diagram_backend: AlgebraBackend[object],
        diagram_codec: ValueCodec[object],
    ) -> TypedWhiteboardSidecar:
        """Load a sidecar containing independently typed definition stores."""

        resolved = resolve_sidecar_path(path)
        state = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError("whiteboard sidecar must contain a JSON object")
        if state.get("format") != _FORMAT or state.get("version") != _TYPED_VERSION:
            raise ValueError("file is not a version 2 typed whiteboard sidecar")
        stores = state.get("stores")
        if not isinstance(stores, dict):
            raise ValueError("typed whiteboard stores must be an object")
        document = state.get("document", {})
        if not isinstance(document, dict):
            raise ValueError("whiteboard sidecar document must be an object")
        projectors = _load_store(
            stores.get("projectors"), projector_backend, projector_codec, "projector"
        )
        diagrams = _load_store(
            stores.get("diagrams"), diagram_backend, diagram_codec, "diagram"
        )
        return cls(
            resolved,
            WhiteboardStores(projectors=projectors, diagrams=diagrams),
            deepcopy(document),
        )


def write_sidecar(
    path: str | PathLike[str],
    environment: EvaluationEnvironment[ValueT],
    *,
    codec: ValueCodec[ValueT],
    document: dict[str, Any] | None = None,
) -> WhiteboardSidecar[ValueT]:
    """Atomically write definitions and optional frontend document state."""

    if document is not None and not isinstance(document, dict):
        raise TypeError("whiteboard document state must be a dictionary")
    serialized = {
        "format": _FORMAT,
        "version": _VERSION,
        "backend": environment.backend.name,
        "codec": codec.name,
        "definitions": [
            {"name": definition.name, "value": codec.encode(definition.value)}
            for definition in environment.definitions
        ],
        "document": deepcopy(document) if document is not None else {},
    }
    resolved = resolve_sidecar_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary = resolved.with_name(f".{resolved.name}.tmp")
    temporary.write_text(
        json.dumps(serialized, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(resolved)
    return WhiteboardSidecar.load(
        resolved,
        backend=environment.backend,
        codec=codec,
    )


def write_typed_sidecar(
    path: str | PathLike[str],
    stores: WhiteboardStores,
    *,
    projector_backend: AlgebraBackend[object],
    projector_codec: ValueCodec[object],
    diagram_backend: AlgebraBackend[object],
    diagram_codec: ValueCodec[object],
    document: dict[str, Any] | None = None,
) -> TypedWhiteboardSidecar:
    """Atomically write separate projector and diagram definition stores."""

    if document is not None and not isinstance(document, dict):
        raise TypeError("whiteboard document state must be a dictionary")
    serialized = {
        "format": _FORMAT,
        "version": _TYPED_VERSION,
        "stores": {
            "projectors": _serialize_store(
                stores.projectors, projector_backend, projector_codec
            ),
            "diagrams": _serialize_store(
                stores.diagrams, diagram_backend, diagram_codec
            ),
        },
        "document": deepcopy(document) if document is not None else {},
    }
    resolved = resolve_sidecar_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary = resolved.with_name(f".{resolved.name}.tmp")
    temporary.write_text(
        json.dumps(serialized, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(resolved)
    return TypedWhiteboardSidecar.load(
        resolved,
        projector_backend=projector_backend,
        projector_codec=projector_codec,
        diagram_backend=diagram_backend,
        diagram_codec=diagram_codec,
    )


def _serialize_store(
    environment: EvaluationEnvironment[object],
    backend: AlgebraBackend[object],
    codec: ValueCodec[object],
) -> dict[str, object]:
    if environment.backend.name != backend.name:
        raise ValueError("environment and backend do not match")
    return {
        "backend": backend.name,
        "codec": codec.name,
        "definitions": [
            {"name": definition.name, "value": codec.encode(definition.value)}
            for definition in environment.definitions
        ],
    }


def _load_store(
    state: object,
    backend: AlgebraBackend[object],
    codec: ValueCodec[object],
    label: str,
) -> EvaluationEnvironment[object]:
    if not isinstance(state, dict):
        raise ValueError(f"typed whiteboard {label} store must be an object")
    if state.get("backend") != backend.name or state.get("codec") != codec.name:
        raise ValueError(f"typed whiteboard {label} store has incompatible backend")
    definitions = state.get("definitions")
    if not isinstance(definitions, list):
        raise ValueError(f"typed whiteboard {label} definitions must be an array")
    environment = EvaluationEnvironment(backend)
    for index, item in enumerate(definitions):
        if not isinstance(item, dict):
            raise ValueError(f"{label} definition {index} must be a JSON object")
        name = item.get("name")
        if not isinstance(name, str):
            raise ValueError(f"{label} definition {index} has an invalid name")
        if "value" not in item:
            raise ValueError(f"{label} definition {index} has no value")
        environment.define(name, codec.decode(item["value"]))
    return environment


__all__ = [
    "TypedWhiteboardSidecar",
    "WhiteboardSidecar",
    "WhiteboardStores",
    "resolve_sidecar_path",
    "write_sidecar",
    "write_typed_sidecar",
]
