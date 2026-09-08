# Calculator application boundary

The projector calculator is already split at the boundary needed for a small
application:

- immutable `Projector` and `ProjectorSum` values own exact algebra;
- `compile_display_graph()` derives operator columns and permutation corridors;
- `ProjectorCanvasSession` owns serializable equation history;
- `projector_sum_widget()` is the calculator view and interaction controller.

The display graph is disposable. Creation and evaluation save and transform the
exact graph, then compile a new display graph. This keeps a future redesign from
changing coefficients, canonical equality, creation semantics, or evaluation.

## Local browser application

A local web application served by Voilà renders the existing AnyWidget canvas
with a live Python kernel and requires no second implementation of the algebra.
Install it with `pip install 'birdtracks[app]'`. Calling `birdtracks.create()`
from a Python terminal or command-line script launches the application in the
default browser; the same call in Jupyter continues to return an embedded
widget.

1. construct or restore a `ProjectorCanvasSession`;
2. display one `projector_sum_widget()` as the application root;
3. persist explicit Save actions to a user-selected session file;
4. leave file selection and recent-document UI outside the canvas component.

Voilà remains an optional dependency in the `app` extra. Packaging the local
application as a desktop window later can use
the same local web entry point (for example through a webview) without moving
algebra into JavaScript.

## Redesign seams

The root uses the `birdtracks-calculator-app` class and semantic CSS variables
for surfaces, borders, radii, and control sizing. A visual redesign can override
those tokens and reorganize toolbar groups without changing projector SVG
geometry. Diagram colors and measurements remain in `projector-widget.yaml`.

The next UI decision should be the launch form: local browser app, desktop
window, or hosted multi-user service. That choice determines persistence and
security requirements, but does not change the display-graph contract.
