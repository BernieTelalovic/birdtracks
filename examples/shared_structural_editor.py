"""Disposable diagrams for the shared structural editor; launch with Voilà."""

from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from IPython.display import Markdown, display
from ipywidgets import Button, HBox

from birdtracks import Antisymmetriser, Projector, ProjectorSum, Symmetriser
from birdtracks.projectors.widget import projector_sum_widget, projector_widget
from birdtracks.projectors.whiteboard.widget import whiteboard, _result_source
from birdtracks.projectors.whiteboard.projector_codec import projector_codec


# Keep the directory alive for the kernel lifetime. Never overwrite a real file.
demo_directory = TemporaryDirectory(prefix="birdtracks-structural-")
demo_path = Path(demo_directory.name)
a = Projector([Antisymmetriser((1, 2, 3)), Symmetriser((3, 4))], coefficient=Fraction(-2, 3))
b = Projector([Symmetriser((1, 2)), Antisymmetriser((3, 4))], coefficient=Fraction(5, 7))
value = ProjectorSum((a, b))
canvas = projector_sum_widget(value, session=demo_path / "demo.canvas.json", detangler=False, debug=True)
standalone = projector_widget(a, debug=True)
create_editor = projector_widget(Projector([Antisymmetriser((1, 2))]), mode="create", debug=True)
board = whiteboard(demo_path / "demo.whiteboard", debug=True)
source, terms = _result_source(value)
board.blocks = [{"id":"demo", "source":source, "read_only":True,
                 "calculation_group":"demo", "calculation_step":1,
                 "calculation_value":projector_codec.encode(value), "calculation_terms":terms}]


def command(editor, action, **arguments):
    state = editor.editor_state
    editor.editor_request = {"request_id":uuid4().hex, "term_id":state["term_id"],
                             "base_revision":state["revision"], "action":action, **arguments}
    if editor.editor_feedback.get("error"):
        raise ValueError(editor.editor_feedback["error"])


def replace_a(_button):
    state = standalone._editor_session.state
    index = next(i for i, node in enumerate(state.projector.nodes) if isinstance(node, Antisymmetriser))
    labels = state.projector.nodes[index].support
    replacement = Projector([Antisymmetriser(labels), Antisymmetriser(labels)])
    command(standalone, "replace", node_id=state.node_ids[index], replacement=projector_codec.encode(replacement))


replace_button = Button(description="Identity: A → A A")
replace_button.on_click(replace_a)
tidy_button = Button(description="Explicit tidy")
tidy_button.on_click(lambda _button: command(standalone, "tidy"))

display(Markdown("### Canvas: −2/3 A(123) S(34) + 5/7 S(12) A(34)"))
display(canvas)
display(Markdown("### Standalone: movement, routing, and internal identity replacement"))
display(standalone, HBox((replace_button, tidy_button)))
display(Markdown("### Create: A(12), reconnect the input endpoints"))
display(create_editor)
display(Markdown("### Whiteboard: the same two-term expression"))
display(board)
display(Markdown(f"Disposable session files: `{demo_path}` (removed when the kernel exits)."))
