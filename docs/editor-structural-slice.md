# Shared structural editor: verification guide

See [ADR 0006](adr/0006-shared-structural-editor.md) for ownership, coefficient,
provenance, and persistence decisions. This extends the port slice without
changing the visual design.

## Launch and diagrams

From the repository root, with notebook/app extras already installed:

```sh
.venv/bin/python -m voila examples/shared_structural_editor.py --no-browser --port=8874 --VoilaConfiguration.extension_language_mapping=.py=python --VoilaConfiguration.language_kernel_mapping=python=python3
```

Open http://localhost:8874/. The example displays the existing canvas, standalone
widget, Create widget, and whiteboard. Its two-term diagram is
`−2/3 A(123) S(34) + 5/7 S(12) A(34)`, with input on the right. The first product
shares strand 3; the second pair has disjoint supports. All files live in a
fresh temporary directory, printed below the diagrams, so no existing document
is overwritten. Copy a demo session elsewhere before stopping the kernel if
you want to retain it. The standalone demo's two extra buttons invoke the
internal identity command and explicit tidy; they are demonstration controls,
not new application UI.

For a normal whiteboard, use `.venv/bin/birdtracks-whiteboard --debug`. Create
and save the same diagram as `P\def \birdtracks`, evaluate with Shift-Enter,
and check its authored diagram, generated result, and expanded reference `+P`.
Also try a symbolic prefactor such as `N` on a generated row.

## Gesture checklist

Repeat on the canvas, standalone widget, and supported whiteboard occurrences:

1. **Movement:** in Evaluate, drag A vertically. Record its
   new position and an untouched neighbour. One Ctrl-Z/Cmd-Z restores the whole
   drag; Ctrl-Shift-Z/Ctrl-Y restores it. The algebra and coefficient stay fixed.
   In Create, vertical movement is still placement; horizontal movement retains
   the existing connectivity/splice gesture and can change the operator.
2. **Routing:** drag a free strand around another operator. Cancel another drag
   with a pointer cancellation, then complete a drag. Cancellation must add
   no history; completion must add one action. Save immediately after release,
   then redraw/reload: the route and all manual positions remain.
3. **Reconnect:** use the Create A(12) diagram. Drag an attached input endpoint
   onto the other occupied input so the existing swap gesture reconnects both
   wires. This changes the operator, rather than adding redraw compensation.
   Undo restores both wires at once. Drop an endpoint in empty space: it must
   restore the accepted diagram and add no undo entry. Reorder handles in
   Evaluate instead: the expression stays equal, with one sign compensation.
4. **Recursive expansion:** on the first term's A(123), click a top/bottom
   triangle. A two-branch next line appears. Its coefficients must preserve
   the expression; the untouched S(34), neighbouring term, paint, and manual
   positions remain. Undo on the new line removes that entire line; redo restores
   its exact drawing. Repeat with an odd input ordering and the opposite triangle.
   For composite authored whiteboard formulas, first evaluate and expand their
   result line; a single inline diagram with a rational prefactor is supported.
5. **Full expansion:** double-click S/A. The separate factorial calculation
   creates a next line immediately, without a confirmation popup.
   It must not silently run during movement, routing, or recursive expansion.
6. **Replacement:** in the standalone demo, move S(34) first, then click
   `Identity: A → A A`. Only the A neighbourhood is replaced. S's ID/position,
   incident survivor wires, and the expression remain. Undo/redo restores the
   replacement atomically. This demonstrates the internal identity insertion
   boundary; no general replacement gesture has been added.
7. **Tidy and persistence:** rendering, saving, recalculating, or switching modes
   must not reset placement. Only the demo's explicit Tidy does a full reset;
   undo restores the drawing. Reload a canvas with
   `ProjectorCanvasSession.load(path).open(detangler=False)`; reopen a whiteboard
   with `whiteboard(path)`. Check undo/redo both for a structural term edit and
   for an undone expansion line. Standalone widgets round-trip through
   `ProjectorConfiguration.from_state(p, widget.configuration.state())`.
8. **Synchronization:** complete a drag and immediately Save, undo, or change
   another row. Delayed acknowledgements/remounts must not restore an old graph,
   coefficient, placement, route, or source. Check that symbolic factors and
   scalar-only terms remain in generated whiteboard results.

## Gesture → Python → rendering

The frontend previews the gesture and sends one revisioned request on release.
`editor_widget.py` invokes `EditorSession`; reconnection/replacement constructs
and validates a candidate before a history entry or committed mutation. Local
rewrites transfer explicit survivor provenance, and presentation transfer repairs
only affected controls. Python publishes one authoritative graph/coefficient/
presentation envelope. The frontend renders it; it does not compensate committed
signs. Whiteboard text/value translation remains in `result_projection.py`.
The document host inserts expansion descendants as one line transaction and
persists exact occurrence states and redo data.

## Automated verification

Commands used:

```sh
.venv/bin/python -m pytest -q tests/conformance/test_editor_surfaces.py tests/unit/test_editor_structural.py tests/unit/test_whiteboard_sidecar.py
.venv/bin/python -m pytest -q
git diff --check
```

The browser tests in `tests/ui/test_projector_editor_gestures.py`,
`test_whiteboard.py`, and `test_young_creator.py` load the shipped JavaScript and
connect interaction requests to actual Python widgets. Small exact collapse
comparisons are test oracles only. Tests also forbid collapse/node permutation
enumeration inside interactive commands, including a size-12 recursive case.

`pyproject.toml` configures no separate lint/type-check suite. Optional-backend
skips are distinct from failures; the pre-existing mismatched-Young whiteboard
stress-fixture comparison is not repaired by this editing stage.

Recorded verification (2026-10-08):

- Full configured run: 1,125 passed, one pre-existing failure, eight skipped
  in 382.17 seconds. The failure is
  `test_stress_whiteboard_contains_every_exact_case` at
  `tests/unit/test_mismatched_young_layers_stress.py:325`, also present before
  this stage. Three skips require the unbuilt optional Cython backend; five
  require Torch.
- Shipped-frontend gesture/creator run: 86 passed. The final targeted browser
  history/replacement run passed eight cases.
- Final model, shared-surface, and layout checks: 193 passed, including the
  additional redo-invalidation, mode-switch, and first-valid-Save cases added
  after the full run. Whiteboard v1 additionally replays structural undo/redo.
- The demo and its identity/undo/tidy actions executed successfully. Python
  syntax compilation and `git diff --check` passed.

The slowest full-suite case was the explicitly requested multi-line full
expansion/collection test (189.63 seconds), not an interactive command. A final
broad recheck excludes only that unchanged calculation, already passed above;
it recorded 1,131 passed, the same one pre-existing failure, eight dependency
skips, and one deselection in 190.59 seconds. The final targeted browser run
again passed all eight cases. No new test failure remains.

## Local spacing and corridor correction

The follow-up presentation correction reserves box/crossing space for newly
introduced operators and routes around actual saved box positions, rather than
treating a logical column's first operator as its physical location. Focused
synthetic tests cover lone and constrained expansions, reuse of disjoint survivor
columns, and real input/output drags through staggered and fractional-position
layouts. The user's whiteboard is not used as a regression fixture or rewritten.

Restart the app/kernel to load the updated frontend. Existing manual coordinates
remain authoritative: regenerate the affected expansion row (or explicitly tidy)
to obtain the new automatic spacing. Routing corrections apply to saved rows
without altering their algebra, signs, or placement.

Follow-up verification: 196 focused model/layout/conformance cases passed, as
did the two synthetic browser obstacle checks (including fractional placement).
The full run recorded 1,138 passed, the same pre-existing Young-layer fixture
failure, and eight optional-dependency skips in 372.62 seconds. The saved term
and a fresh expansion were additionally checked with real output-port drags;
their exact values remained equal and the whiteboard file checksum was unchanged.

## Layer/connector layout and bounded absorption

Rendering now follows the layered projector in `latex/birdtracks.sty`. S/A boxes
and straight free lines occupy operator layers; all crossings occupy connectors
between layers. An attached permutation adds neither a column nor width.
Only a standalone permutation uses a wider connector. Recursive expansion
removes redundant nested S/A operators in Python using the existing normalized
absorption rule, without full collapse. Shared Python line cleanup then removes
zero terms and combines equivalent mixed wiring without expanding the S/A nodes.

Use this small synthetic diagram in a notebook to check the two independently:

```python
from pathlib import Path
from tempfile import mkdtemp
from birdtracks import Antisymmetriser, Projector, ProjectorSum, Symmetriser
from birdtracks.projectors.widget import projector_sum_widget

p = Projector([Symmetriser((1, 2)), Antisymmetriser((2, 3, 4)),
               Symmetriser((1, 2)), Antisymmetriser((2, 3, 4)), Symmetriser((1, 2))])
path = Path(mkdtemp(prefix="birdtracks-connectors-")) / "layers.canvas.json"
canvas = projector_sum_widget(ProjectorSum((p,)), session=path, detangler=False)
display(canvas)
```

Click the top recursion triangle of the rightmost three-line A. Both descendants
should lose their leftmost newly introduced two-line A through absorption into
the surviving large A. In the first branch the redundant final S also disappears;
in the second, one two-line A remains alongside the final S. The branch factors
are `1/3` and `-2/3`. Automatically placed columns close vacated gaps, with
crossings confined to connectors and straight free strands across box layers.
Swap input and output ports of the remaining A and check the live sign preview,
undo/redo, and unchanged layer geometry. Save and reopen using
`ProjectorCanvasSession.load(path).open(detangler=False)`.

Repeat after manually moving a surviving operator: its coordinates must remain
fixed through expansion and reload. Explicit Tidy (available in the structural
demo) resets automatic placement in one undoable action. Older saved coordinates
without automatic-placement metadata remain conservatively manual; regenerate
the source diagram or explicitly tidy before expanding to check automatic gap
closure. Existing result rows are not silently rewritten.

Verification (2026-10-08): the full configured run passed 1,156 tests, with
eight optional-dependency skips, in 392.23 seconds. After the final sparse-state
and manual-collision guards were added, the final broad recheck passed 1,163
tests with the same eight skips and one deselection in 193.34 seconds. Only
`test_whiteboard_full_expansion_collects_equal_permutations` was excluded from
that recheck; it had passed in the full run. All 1,164 tests therefore passed
across the two runs. The skips are three unbuilt optional Cython checks and
five missing-Torch checks, not failures. The focused final model/layout/shared
surface run passed 226 tests; nine focused Chromium interaction checks passed,
including straight layer bands, connector-only crossings, and manual movement.
The full/broad runs also exercised every shipped frontend test. `git diff
--check` passed; no separate lint/type-check suite is configured.

## Cleanup after recursive and full expansion

Every expansion now uses the same bounded Python cleanup, including standalone
published branches and untouched occurrences carried into a new equation line.
It reaches a fixed point for nested S/S and A/A absorption, removes exact S–A
zeros, and collects terms using permutation-corridor normalization plus canonical
graph orientation. The comparison graph is never substituted for the surviving
editor drawing. The first representative retains its IDs, placement, routes,
and colors; exact rational and symbolic factors are combined once. Pure closed
permutation traces keep their dimension factors. Port drags still do not collect.

In the synthetic AA diagram above, first expand the rightmost three-line A,
then the middle two-line S in the second branch. The next line should contain
one term with factor `2/3`: the equivalent first two contributions combine,
and the double-connected S–A contribution disappears. Check Save/reload and
whole-line undo/redo, then repeat with an odd input or output redraw.

For a separate absorption check, use
`c = Projector([Antisymmetriser((2,3)), Symmetriser((1,2))])` and display
`ProjectorSum((c * c,))`. Expand the middle S, then the remaining right-hand A
in the second branch. Absorption must also run on the carried first term;
the cleaned result is one `3/4 c` term. Here S/A nodes are individually
normalized; `c` is not rescaled to an idempotent Young projector.

Focused tests use these small algebraic constructions, not the user's saved
whiteboard as a fixture. They cover signed/rational/symbolic collection, zero
removal, repeated absorption, fixed-point cleanup, free boundary strands,
direction distinctions, loop factors, manual presentation preservation,
persistence, whole-line undo/redo, and both real browser expansion gestures.

Cleanup verification (2026-10-08): 194 focused algebra/editor/surface cases
passed, as did three focused Chromium gesture/layer checks. The full configured
suite passed 1,187 tests with eight optional-dependency skips in 391.27 seconds.
Three skips require the unbuilt optional Cython backend; five require Torch.
There were no failures. `git diff --check` passed, and no separate lint/type-check
suite is configured. The current saved AA and CC rows were also inspected
read-only: cleanup preserved their exact collapsed values while reducing the
reported final lines to `2/3 A` and `3/4 C`. The user's whiteboard was neither
rewritten nor adopted as a regression fixture. Restart the app/kernel and
regenerate the expansion rows to exercise the updated pipeline.

## Independent free lines in tensor columns

The routing fix is presentation-only. Packed display columns now have stable
column controls separate from algebra-layer routes. Strands retain their input
identity through permutations instead of borrowing the output boundary label.
Python reserves explicit rows before allocating automatic free lines; all free
lines receive drag handles. A completed drag, including its existing column
packing, is one undoable transaction. Cancel leaves committed state unchanged.
Surviving controls transfer through replacements without resetting placement.

For a small synthetic diagram, set
`a = Projector([Symmetriser((1,2)), Antisymmetriser((2,3,4)), Symmetriser((1,2))])`
and display `ProjectorSum((a @ a,))`; `@` is tensor product, not composition.
In a whiteboard with that definition, evaluate `A\otimes A` and recursively
expand a lower-factor A to introduce a permutation connector.

Check the canvas, standalone widget, and whiteboard:

1. Free lines in each operator column occupy separate rows, including lower
   strands passing through a permutation. Hover each line to find its handle.
2. Drag two neighbouring free lines independently in the same column. Existing
   column packing may move its operators; other columns stay unchanged. Crossings
   remain in connectors, not operator bands.
3. Cancel a drag, then complete one. Undo/redo restores the complete drag once.
   Reorder an A input/output port and verify the separate routing remains.
4. Save, reload, and repeat the drag. Manual positions, stable identities, routes,
   coefficients, and undo history survive. A delayed old render must not restore
   previous lanes. Only explicit Tidy resets placement and controls.

The shared API accepts `EditorSession.reroute({}, display_changes={column_id:
{input_strand_id: row}}, base_revision=revision, geometry=geometry)`. Obtain IDs
from the authoritative display projection's `column_ids` and strand `editor_id`,
not from local/output labels or algebra layer numbers. The command validates
that the strand is free in that column; it never computes a permutation or
calls collapse. Focused exact-collapse checks are test oracles only.

The reported saved tensor term was also verified read-only through shipped
JavaScript and Python: strands 6/7 separated on load and drag; other columns
and manual placement were retained; reload preserved controls. The user's
whiteboard was neither modified nor used as a regression fixture. Restart the
app/kernel and reload the document to use the new frontend and Python projection.

Routing verification (2026-10-08): the final full configured suite passed 1,205
tests with eight optional-dependency skips in 389.99 seconds, with no failures.
Three skips require the unbuilt optional Cython backend; five require Torch.
The focused model/shared-surface run passed 146 tests, and all 100 layout checks
passed. The shipped-frontend gesture run passed 51 tests; final tensor/stale-render
and whiteboard persistence checks also passed. The full run includes all browser
tests. `git diff --check` passed; no separate lint/type-check suite is configured.
