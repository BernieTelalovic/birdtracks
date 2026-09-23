"""Voilà entry point for the standalone whiteboard application."""

from __future__ import annotations

import os

from IPython.display import display

from birdtracks.projectors.whiteboard.widget import whiteboard_workspace


display(
    whiteboard_workspace(
        os.environ.get("BIRDTRACKS_WHITEBOARD_SESSION"),
        debug=os.environ.get("BIRDTRACKS_DEBUG") == "1",
    )
)
