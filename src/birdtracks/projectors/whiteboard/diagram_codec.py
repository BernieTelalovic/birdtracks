"""Exact serialization for Young-diagram / pair-expression values."""

from __future__ import annotations

from collections.abc import Mapping

from birdtracks.young_diagrams import PairExpression


class DiagramValueCodec:
    """Encode pair expressions through their existing validated state format."""

    name = "diagram-v1"

    def encode(self, value: PairExpression) -> Mapping[str, object]:
        if not isinstance(value, PairExpression):
            raise TypeError("diagram codec expects a PairExpression value")
        return value.state()

    def decode(self, payload: object) -> PairExpression:
        return PairExpression.from_state(payload)


diagram_codec = DiagramValueCodec()

__all__ = ["DiagramValueCodec", "diagram_codec"]
