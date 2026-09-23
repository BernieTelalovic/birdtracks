"""The narrow communication contract between document state and algebra."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, TypeVar


ValueT = TypeVar("ValueT")


class AlgebraBackend(Protocol[ValueT]):
    """Operations required by the generic whiteboard evaluation layer.

    ``validate`` is the only place where a concrete value type enters the
    environment.  It may canonicalize an incoming value, but it must return
    an immutable value suitable for retaining as a named definition.
    """

    name: str

    def validate(self, value: object) -> ValueT:
        """Validate and, if needed, canonicalize a definition value."""

    def multiply(self, left: ValueT, right: ValueT) -> ValueT:
        """Compose two values in the backend's documented order."""


class ValueCodec(Protocol[ValueT]):
    """Serialize one backend value without exposing it to the sidecar layer."""

    name: str

    def encode(self, value: ValueT) -> Mapping[str, object]:
        """Return a deterministic JSON-compatible value payload."""

    def decode(self, payload: object) -> ValueT:
        """Validate and reconstruct a value payload."""


__all__ = ["AlgebraBackend", "ValueCodec"]
