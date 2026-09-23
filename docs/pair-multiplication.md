# Standalone representation adapter

`birdtracks.representations` loads `pair_multiplication` only when used. Install
the separate checkout into the calculator's Python environment:

```sh
python -m pip install -e /path/to/pair_multiplication
```

The standalone package currently requires Python 3.12–3.14 and builds a Cython
extension with NumPy and SciPy dependencies. Birdtracks' base dependencies and
Python support are unchanged. No sibling checkout path is assumed at runtime.

```python
import birdtracks
from birdtracks.representations import pair_backend, tensor_product

pm = pair_backend()
left = birdtracks.Pair(((1,), (1,)))  # barred first, unbarred second
right = birdtracks.Pair(((1,), (1,)))
symbolic = tensor_product(left, right)
evaluated = tensor_product(left, right, Nc=3)
print(symbolic)
print(evaluated)
```

`birdtracks.Pair` (also `from birdtracks import Pair`) is the native standalone
class, loaded on first access. Plain `import birdtracks` does not load the
optional package. Accessing `Pair`, including through a wildcard import,
requires it to be installed.

This boundary intentionally returns native standalone values. Constructor
return types, integer multiplicities, weights, inherited `N0`, zero versus the
empty (trivial) partition, and existing operand `Nc` behavior remain upstream
semantics. Supplying `Nc` evaluates the product after multiplication. Numerical
dimension calculations retain upstream precision limitations.

## Calculator creation

In **Create** mode, the **Birdtracks / Young diagrams / tableaux** button
switches between the two workspaces. Each workspace retains its state.
The borderless Young canvas has guide dots alongside the pair, with no extra
bottom row of dots. The blank row below remains clickable for growth. The
dotted axis extends half a box above and below the full pair.

- Click an empty grid position at an addable corner to add a cell. Ordinary
  boxes are added on the right of the central axis; antiboxes on the left.
  Antiboxes sit below-left, right-aligned, with bullets until labeled.
  Starting a diagram from the lower guide row aligns the first cell automatically.
  Further rows must satisfy the partition rules; new rows below antiboxes must
  be at least as long as the row above.
- Double-click any cell to edit its integer tableau label. Labels are ordinary
  integers in boxes and barred integers in antiboxes. The input sits inside the
  cell. Enter or clicking away applies the edit; empty input clears a label;
  Escape cancels. Labels retain exact
  integer precision. This changes the label, not the kind of cell.
- Single-click an existing corner box or antibox to delete it. Deletion waits
  briefly to distinguish a single click from a double-click; undo restores it.
- Drag a corner cell to an empty position on the same side. A blue preview
  marks a valid destination; red marks an invalid one. Changes that leave a
  hole or violate the partition row rules are rejected. Labels move with their
  cells and are removed when those cells are deleted.
- Double-click the prefactor or its `N₀` subscript to edit directly over the
  displayed values. Ctrl-click still opens the same inline editor.
  Enter or clicking away applies the edit; Escape cancels. `N₀` must be at least
  the total number of rows. Adding rows raises that minimum automatically;
  removing rows preserves the inherited threshold. Coefficients may be signed
  or zero, and retain full integer precision.
- **⊕** appends a new term at the right end. **Undo** reverses edits and
  term insertion. Right-click a prefactor to delete its term. A single left-click
  leaves it intact. Deleting the last term leaves the zero sum; **⊕**
  starts a new term. Term deletion can also be undone. Select a corner and
  press Delete to remove that cell.

In birdtrack create mode, double-click the displayed prefactor or denominator
to edit the fraction in place. Enter or clicking away applies it; Escape cancels.

The Young workspace supports creation, saving and representation evaluation.
Choose **Evaluate** to expand bracketed tensor products and compute accepted
column-multiplication stages. The first line shows the written expression without
construction guides. Click each **=** beneath it to reveal one further line;
the final collected direct sum has no further step button. Intermediate tableaux
retain box/antibox labels and dashed removed cells from the standalone renderer.
Rejected candidates and handwritten linking-sequence captions are not generated.
Each product inherits the maximum operand N₀, and collection keeps distinct N₀
thresholds separate. Coefficients remain exact integers. **Create** returns to the
unchanged input. Invalid bracket/operator syntax displays an error for correction.

Save/reload retains both workspaces and the selected kind. Legacy projector
sessions continue to load. In a notebook, the current document is available as:

```python
canvas = birdtracks.create()
display(canvas)
# After editing in the browser:
document = canvas.current_pair_expression
native_terms = document.to_native_terms()  # (standalone Pair, integer coefficient)
```

`birdtracks.load()` returns a `PairExpression` for a session saved with the
Young workspace selected. The edit document preserves ordering, duplicate
terms, tableau labels, and zero coefficients; it does not collect or multiply terms. Empty
partitions denote the trivial representation, not the zero representation.
An expression with no terms denotes the zero sum.

Creation and session handling work without the optional algebra package. When
installed, its `draw_pair().as_dict()` supplies SVG cell geometry; the immediate
browser preview uses the same layout, checked against the standalone renderer.
Exporting native labels requires the optional package. Representation labels
do not specify projector topology or normalization, so conversion into canvas
operators still needs an explicit mathematical mapping.

Tableau annotations are stored on `PairTerm.labels` as `TableauLabel` values
and saved with the session. Coordinates index rows in the corresponding
partition and columns outward from the central axis, so rotation of the barred
drawing does not change cell identity. `to_native_terms()` exports representation
shapes and coefficients only; it does not convert these annotations into native
`PairTableau` candidates or impose semistandard-tableau ordering rules.

The adapter tests assert intentional upstream compatibility, including small
hand-derived decompositions. Backend-dependent tests skip when the optional
package cannot import; run them in an environment with that package installed
to exercise the mathematical cases.

Optional browser tests in `tests/ui/test_young_creator.py` use Playwright and
Chromium when available. They exercise the shipped JavaScript module's mouse
gestures, integer editor, undo, and mode toggle. Python tests cover kernel-side
validation and session round trips.

Pair create mode also supports unevaluated brackets and tensor products. The left
and right bracket buttons append at the right end of the equation; `[` / `]`
(or `(` / `)`) do the same outside text fields. The ⊕ and ⊗ buttons append a new
term or factor at the right end, regardless of the selected term or mouse
position. Brackets are centered on the equation and resize to the tallest pair.
Right-click a bracket or operator to remove it; Undo restores the edit. Saved
documents preserve this syntax, including incomplete brackets while editing.
Exporting an unevaluated bracketed document as a native direct sum is rejected;
Evaluate computes its collected result.

Drag a pair by its prefactor or blank top/bottom margin to move it horizontally,
including across brackets. The insertion marker shows the destination. Its
coefficient, N₀ and tableau labels move with it; an adjacent sum or tensor
operator moves with the term when needed. Undo restores the previous arrangement.

When the rightmost pair is still an untouched empty constructor, an opening
bracket goes immediately before it. Thus ⊗ followed by `(` produces
`… ⊗ ( [empty pair]`, ready to fill in. This also works after ⊕ and for nested
opening brackets; closing brackets still append at the right end.

Double-click the central symmetry line of an empty constructor to insert a
singleton (the trivial pair, with empty barred and unbarred partitions). It is
shown as a dot with construction guides still visible. Adding a box or antibox
turns it back into a diagram. Double-click the dot to clear the singleton marker,
or use Undo. The singleton is preserved in saved documents and acts
as the tensor-product identity, retaining its prefactor and N₀.
