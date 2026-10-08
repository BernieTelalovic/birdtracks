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
5. **Full expansion:** double-click S/A. Cancel the confirmation: nothing changes.
   Repeat and confirm: the separate factorial calculation creates a next line.
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
