"""Voilà entry point for the standalone projector canvas."""

import os

from IPython.display import display

from birdtracks.projectors.widget import projector_creator


display(
    projector_creator(
        prompt_for_session=True,
        debug=os.environ.get("BIRDTRACKS_DEBUG") == "1",
    )
)
