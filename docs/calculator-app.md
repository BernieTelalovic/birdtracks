# Calculator application boundary

The projector calculator is already split at the boundary needed for a small
application:

- immutable `Projector` and `ProjectorSum` values own exact algebra;
- `compile_display_graph()` derives operator columns and permutation corridors;
- `ProjectorCanvasSession` owns serializable equation history for the projector
  canvas;
- `birdtracks.whiteboard()` owns the separate editable document and renders a
  small native MathML subset on blur, including larger `$$...$$` display blocks;
- projector and diagram definitions use separate evaluators and codecs, while
  their user-authored names remain independent ordered source lines;
- `projector_sum_widget()` is the calculator view and interaction controller.

The display graph is disposable. Creation and evaluation save and transform the
exact graph, then compile a new display graph. This keeps a future redesign from
changing coefficients, canonical equality, creation semantics, or evaluation.

The create-mode kind toggle also opens the [Young-diagram workspace](pair-multiplication.md).
Its ordered `PairExpression` document is synchronized through the toolbar and
saved beside the projector lines. Switching kinds hides the inactive workspace
without rebuilding its editors. Representation terms keep partitions, exact
integer coefficients, and `N₀`; they do not imply an operator mapping.

The standalone whiteboard supports exact projector assignments with either
`A := expression` or `A \\def expression`. Continuation blocks beginning with
`&` are evaluated as one logical expression. A later `+A` or `-A` source line
keeps its editable source but displays the named backend value in place.
Embedded projectors are entered as the atomic symbol `\\birdtracks`.
Embedded pairs are entered as `\\pair`, which opens the Young-diagram editor
inline. Pair prefactors are defined by adjacency: `2_4\\pair` has coefficient
2 and prefactor `N₀ = 4`; without a subscript the prefactor `N₀` is 1, and the
effective value is always the maximum of it and the pair's inherent `N₀`.
Use `\\oplus` and `\\otimes` to evaluate pair expressions. Ordinary `+` and
`-` remain renderable but deliberately raise a not-implemented evaluation
error. Press Enter or Shift+Enter on a generated pair equation to reveal its
next automatic Python calculation line; Shift+Backspace restores the source.
Shift+Enter evaluates one connected expression and creates its first exact
evaluation line. Automatic identities run first; the resulting terms are then
shown as evaluate-mode projector widgets, where selecting an operator appends
the next line manually. After that, the connected source is locked until
Shift+Backspace restores it. The evaluator treats adjacent names as ordered
products, `(...)`, `[...]`, and `{...}` as grouping, and distinguishes `\\tr A`
from `\\tr(A + B)` by tracing the next term versus the bracketed expression.
An expression containing `=` is reported as non-sequential and is not
simplified.

## Local browser application

A local web application served by Voilà renders the existing AnyWidget canvas
with a live Python kernel and requires no second implementation of the algebra.
Install it with `pip install 'birdtracks[app]'`. Calling `birdtracks.create()`
from a Python terminal or command-line script launches the application in the
default browser; the same call in Jupyter continues to return an embedded
widget.

1. construct or restore a `ProjectorCanvasSession`;
2. display one `projector_sum_widget()` as the application root;
3. persist explicit Save actions to a user-selected canvas sidecar;
4. leave file selection and recent-document UI outside the canvas component.

Voilà and pywebview are optional dependencies in the `app` extra. The
`birdtracks-whiteboard` command starts Voilà on localhost and displays it in
its own native webview window; the algebra remains in Python.

The standalone whiteboard is launched with `birdtracks-whiteboard` and uses the
`.whiteboard` document extension. Older `.whiteboard.json` documents remain
compatible. The application and its document files use the same three-line
permutation icon so they are easy to identify in application menus and file
browsers.

## Redesign seams

The root uses the `birdtracks-calculator-app` class and semantic CSS variables
for surfaces, borders, radii, and control sizing. A visual redesign can override
those tokens and reorganize toolbar groups without changing projector SVG
geometry. Diagram colors and measurements remain in `projector-widget.yaml`.

The next UI decision should be the launch form: local browser app, desktop
window, or hosted multi-user service. That choice determines persistence and
security requirements, but does not change the display-graph contract.
