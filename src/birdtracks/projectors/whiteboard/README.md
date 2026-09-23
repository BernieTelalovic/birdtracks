# Birdtracks Whiteboard command reference

## Launch commands

Install the desktop dependencies with `pip install 'birdtracks[app]'`, then
launch a new document:

```text
birdtracks-whiteboard
```

Open an existing document by passing its path:

```text
birdtracks-whiteboard my-notes.whiteboard
```

Use `birdtracks-whiteboard --debug` to enable the webview developer tools.
Linux installations also provide **Birdtracks Whiteboard** in the application
menu. Windows installations provide it in the Start menu. On either platform,
opening a `.whiteboard` file launches the same application.

## Toolbar commands

- **Paintbrush** chooses a color. With the paintbrush active, click a projector
  line or a Young-diagram box to color it.
- **Save** writes the current `.whiteboard` document.
- **Load** opens a `.whiteboard`, `.whiteboard.json`, or JSON document.
- **Export to LaTeX** is visible but disabled for the 0.2.0 release.
- The title field changes the document name.

In a multi-document workspace, select a named tab to switch documents, **+**
creates a new document, and **×** closes the selected document.

## Editing and calculation commands

| Command | Result |
| --- | --- |
| `Enter` in an editable line | Split the line at the caret and save embedded state. |
| `Enter` on rendered editable content | Edit the line. |
| `Enter` on a generated result | Add an editable line after its calculation group. |
| `Ctrl+Enter` on a generated result | Add an editable line before its calculation group. |
| `Enter` on a pair calculation | Reveal the next automatic calculation line. |
| `Shift+Enter` | Evaluate the connected expression. |
| `Shift+Backspace` | Restore the source lines behind a generated calculation. |
| `Backspace` at the start of a line | Merge it into the preceding editable line. |
| Arrow keys at a line boundary | Move to the adjacent line. |
| `Tab` after `\\b`, `\\p`, or `\\d` | Complete `\\birdtracks`, `\\pair`, or `\\def`. |
| `Space` on focused rendered content | Edit the line. |

Start a line with `&` to continue the preceding logical line. Define a named
expression with either `A := expression` or `A \\def expression`. Later lines
can use that name. Adjacent projector names are ordered products. Parentheses,
square brackets, and braces group calculations. `\\tr A` traces the next term;
`\\tr(A + B)` traces the grouped expression.

## Whiteboard source commands

- `\\birdtracks` inserts an editable birdtrack projector.
- `\\pair` inserts an editable Young-diagram pair. A prefactor can be attached,
  for example `2_4\\pair`.
- `\\def` renders the definition operator; `:=` is equivalent.
- `\\oplus` and `\\otimes` are direct sum and ordered tensor product for pair
  expressions.
- `\\tr` is the trace operator.
- `\\frac{numerator}{denominator}` and `\\sqrt{value}` create a fraction and
  square root.
- `\\text{text}` and `\\mathrmtext{text}` insert literal text.
- `\\mathbb{...}`, `\\mathcal{...}`, `\\mathfrak{...}`, `\\mathrm{...}`, and
  `\\mathbf{...}` select double-struck, script, Fraktur, upright, and bold text.
- `\\left` and `\\right` accept the following delimiter.
- `\\quad` and `\\qquad` insert one-em and two-em spaces.
- `_` and `^` add subscripts and superscripts. Both braced and single-character
  arguments are accepted; `\\_` is accepted as an escaped subscript marker.
- `$...$` and `\\(...\\)` delimit inline math. `$$...$$` and `\\[...\\]` delimit
  display math. A line without delimiters is treated as math.

The supported named symbols are:

```text
\\alpha \\beta \\gamma \\delta \\epsilon \\varepsilon \\zeta \\eta
\\theta \\vartheta \\iota \\kappa \\lambda \\mu \\nu \\xi \\pi \\varpi
\\rho \\sigma \\tau \\upsilon \\phi \\varphi \\chi \\psi \\omega
\\Gamma \\Delta \\Theta \\Lambda \\Xi \\Pi \\Sigma \\Phi \\Psi \\Omega
\\cdot \\times \\pm \\mp \\leq \\geq \\neq \\infty \\to \\mapsto
\\partial \\nabla \\sum \\prod \\int \\oplus \\otimes
```

Other named LaTeX commands are rejected and shown as invalid source.

## Embedded projector commands

Click an embedded projector to activate its editing controls. The available
pointer commands are:

- Double-click an empty line or the space between lines to add a symmetriser.
- Double-click a symmetriser or antisymmetriser to switch its kind.
- Right-click an operator to delete it and reconnect its strands.
- Drag an operator to reposition it.
- Drag ports, free lines, boundary lines, or connection handles to reorder or
  reconnect them. Right-click a connection to delete it.
- Use the boundary **+** controls to add a line.
- Use the top or bottom triangle on an operator to add a line. Hold `Ctrl` to
  make the same control remove a line.
- Hold `Ctrl` and click a direction control to cycle the projector direction.
- Hold `Ctrl` to reveal the local multiply control in create mode or local undo
  in evaluate mode. Multiplication accepts an integer numerator and a nonzero
  integer denominator; `Enter` applies it and `Escape` closes the editor.
- In evaluate mode, double-click an operator to save that evaluation step. The
  top and bottom recursion controls recursively expand from the selected line.
- **Save Projector** or **Save Step** stores the current embedded state.
- When several result terms are shown, drag a term horizontally to reorder it.

The shared projector toolbar can switch between create and evaluate modes,
switch between birdtracks and Young diagrams, add positive or negative terms,
add a symmetriser or antisymmetriser, multiply by an exact fraction, toggle a
trace, undo the most recent edit, and zoom in or out. With an embedded editor
active and no text field focused, `+` and `-` insert signed birdtrack terms,
while `(`, `[`, `)`, and `]` add pair-expression brackets.

## Embedded Young-diagram commands

- Click an empty grid position to add a box.
- Click a box to select it, right-click it (or press `Delete`/`Backspace`) to
  remove it, and drag it to another valid position.
- Double-click a box to edit its integer tableau label. `Enter` or **Apply
  label** accepts the label; an empty label removes it; `Escape` cancels.
- Double-click the central axis of an empty pair to toggle a singleton pair.
- Drag a term by its prefactor to reorder it.
- Double-click a prefactor to edit its integer value and `N₀`. `Enter` or
  **Apply** accepts the values; `Escape` cancels. `Ctrl+click`, `Ctrl+Enter`,
  `Enter`, or `Space` on a focused prefactor also opens this editor.
- Right-click a prefactor to delete the term.
- Right-click `\\oplus`, `\\otimes`, or a grouping bracket to remove it.
- Use the direct-sum, tensor-product, and bracket controls in the shared
  toolbar to build a pair expression; use **+** or **−** to add a term.
- On a pair-evaluation result, click **=** to reveal the next simplification
  step.
