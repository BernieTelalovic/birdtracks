# Cross-interface port verification

Use the repository venv and restart a running kernel/app after pulling this
change. Launch the canvas demo as described in [the slice guide](editor-layer-slice.md),
or run `.venv/bin/birdtracks-whiteboard --help` for the
whiteboard launch options.

In a notebook, a small nonzero test operator is:

```python
from fractions import Fraction
from birdtracks import Antisymmetriser, Projector, Symmetriser
from birdtracks.projectors.widget import projector_widget

p = Projector([Antisymmetriser((1, 2, 3)), Symmetriser((3, 4))],
              coefficient=Fraction(-2, 3))
display(projector_widget(p))
display(p.evaluate(session="port-migration-demo", detangler=False))
```

For the whiteboard, create and save the same A/S diagram as a definition, evaluate
it with Shift-Enter, and test both the locked inline definition and its generated
row. Also test an expanded named reference (`+P`) and a symbolic coefficient such
as `N`. Port reordering belongs to evaluate mode, not structural creation.

## Repeat on every surface

1. Move an operator and route a free strand before starting. Record the placement
   and an untouched neighbouring term.
2. Drag A input port 1 across port 2. The sign changes during movement. Before
   releasing, cross another slot and move back: each parity change is previewed.
   Cancel a drag and check that the accepted sign and drawing return.
3. Release one swap: the compensating coefficient changes once, with no second
   flip when Python acknowledges. Connectivity and the expression are unchanged.
4. Swap two output ports too. The two odd sides restore the original sign. An
   even reorder leaves the coefficient unchanged; repeating a swap restores its
   previous arrangement.
5. Use Ctrl-Z/Cmd-Z once to undo one complete drag, then Ctrl-Shift-Z/Ctrl-Y or
   the contextual redo control. Check ports, signs, placement, and routes together.
6. Save immediately after release. Click away or update another row while the
   response is pending. It must not restore an older drawing, source, or position.
7. Reload the configuration/canvas or whiteboard. Verify signs, port orders,
   stable IDs (programmatically), placement, routing, and undo/redo history. No
   additional compensation should occur on load.
8. In a multi-term line, leave another term untouched. Simplify small cases and
   confirm that equal topology still collects with the orientation-adjusted
   coefficients. For symbolic rows, check that symbolic factors and scalar-only
   contributions remain present.

## Ownership and gesture path

The frontend previews an order locally, then sends one `reorder` request with
stable node IDs and the accepted revision. `EditorSession` validates it and calls
`project_port_orders`. The adapter publishes one committed algebra/drawing
envelope. Whiteboard source/value projection is done in Python; the view only
renders that projection. Save persists the same exact payload. Small collapse
comparisons are test oracles, never part of an edit.

Automated coverage is in `tests/conformance/test_editor_surfaces.py`,
`tests/ui/test_projector_editor_gestures.py`, and
`tests/ui/test_whiteboard_result_projection.py`.

## Recorded verification

The migration's final full run passed 1058 tests. The existing
`test_stress_whiteboard_contains_every_exact_case` fixture comparison still
fails at `tests/unit/test_mismatched_young_layers_stress.py:325`; it also failed
before this stage. Eight tests were skipped: three need the unbuilt Cython
backend, and five need Torch. A subsequently added focused symbolic live-preview
browser test passed separately.

The surface conformance suite passed 28 cases; the cross-surface drag/undo/save
browser suite passed 12 cases. Configuration JSON, canvas sidecars, typed
whiteboard v2, and whiteboard v1 containers were checked for exact state replay.
Implementation diffs passed `git diff --check`. Staging the previously untracked
artifacts additionally exposed existing trailing whitespace in
`examples/whiteboard/example.tex` and `texput.log`; those artifacts were retained
unchanged as requested. `pyproject.toml` configures no separate lint/type-check
suite. The browser checks load the shipped JavaScript/CSS and connect commands
to Python; the checklist above remains the desktop/notebook manual handoff.
