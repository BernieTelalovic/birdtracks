"""Launch the shared projector canvas with Voilà."""

from fractions import Fraction
import os

from IPython.display import display

from birdtracks import Antisymmetriser, Projector, ProjectorSum, Symmetriser
from birdtracks.projectors.canvas_session import ProjectorCanvasSession
from birdtracks.projectors.widget import projector_sum_widget

name = os.environ.get("BIRDTRACKS_EDITOR_SESSION", "port-reorder-demo")
try:
    canvas = ProjectorCanvasSession.load(name).open(detangler=False, debug=True)
except FileNotFoundError:
    value = ProjectorSum((
        (Projector([Antisymmetriser((1, 2, 3)), Symmetriser((3, 4))]), Fraction(-2, 3)),
        (Projector([Symmetriser((1, 2))]), Fraction(5, 7)),
    ))
    canvas = projector_sum_widget(value, session=name,
                                  detangler=False, debug=True)

display(canvas)
