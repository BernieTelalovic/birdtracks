"""Immutable, exactly replayable projector editor configurations."""

from __future__ import annotations

from dataclasses import dataclass
import json
from os import PathLike
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .projector import Projector


@dataclass(frozen=True)
class ProjectorConfiguration:
    """An algebraic projector together with an immutable canvas snapshot."""

    projector: Projector
    _state_json: str

    @classmethod
    def from_state(
        cls, projector: Projector, state: dict[str, object]
    ) -> ProjectorConfiguration:
        """Freeze JSON-compatible synchronized editor state."""
        return cls(
            projector,
            json.dumps(state, sort_keys=True, separators=(",", ":")),
        )

    def state(self) -> dict[str, object]:
        """Return an independent mutable copy of the saved editor state."""
        value = json.loads(self._state_json)
        assert isinstance(value, dict)
        return value

    def evaluate(
        self,
        *,
        style: str | PathLike[str] | None = None,
        session: str | PathLike[str] | None = None,
        detangler: str | PathLike[str] | object | None = None,
    ) -> object:
        """Replay this exact configuration in an evaluation canvas."""
        if session is not None:
            from .canvas_session import (
                ProjectorCanvasSession,
                _resolve_canvas_session_path,
            )

            if _resolve_canvas_session_path(session).exists():
                return ProjectorCanvasSession.load(session).open(
                    style=style, detangler=detangler
                )
        from .projector_sum import ProjectorSum
        from .widget import projector_sum_widget, projector_widget

        editor = projector_widget(
            self.projector,
            style=style,
            configuration=self,
            mode="evaluate",
        )
        return projector_sum_widget(
            ProjectorSum((self.projector,)),
            style=style,
            initial_editor=editor,
            session=session,
            detangler=detangler,
        )


__all__ = ["ProjectorConfiguration"]
