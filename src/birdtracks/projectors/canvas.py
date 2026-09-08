"""Public entry point for creating or resuming projector canvases."""

from __future__ import annotations

from os import PathLike


def create(
    *,
    style: str | PathLike[str] | None = None,
    session: str | PathLike[str] | None = None,
    detangler: str | PathLike[str] | object | None = None,
    debug: bool = False,
) -> object:
    """Create, launch, or resume an interactive birdtrack canvas."""
    if session is None:
        from .app import launch_canvas_app, should_launch_canvas_app

        if should_launch_canvas_app():
            return launch_canvas_app(debug=debug)
    if session is not None:
        from .canvas_session import (
            ProjectorCanvasSession,
            _resolve_canvas_session_path,
        )

        if _resolve_canvas_session_path(session).exists():
            return ProjectorCanvasSession.load(session).open(
                style=style, detangler=detangler, debug=debug
            )
    from .widget import projector_creator

    return projector_creator(
        style=style, session=session, detangler=detangler, debug=debug
    )


__all__ = ["create"]
