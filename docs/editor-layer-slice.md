# Shared port-reordering slice

Status: complete; included in `v0.2.2`. The first-slice notes below are
historical; current rules live in [the maintenance guide](editor-layer-maintenance.md).

Historical first-stage guide. Movement, routing, connectivity, and local rewrites
have since migrated too: see [the structural editor guide](editor-structural-slice.md).
In particular, movement/routes are now undoable transactions, and complete
Create diagrams retain their shared session across mode changes.

[ADR 0008](adr/0008-mandatory-editor-protocol.md) records the current mandatory
protocol, including blank diagrams and pairs. Its scope/ownership statements
supersede the transitional compatibility section below.

Evaluate-mode canvases, projector widgets, and whiteboard diagrams now use the
same Python-owned port editor by default. See
[the cross-interface checklist](editor-port-migration.md) for this migration.
Use the repository venv. Its notebook/app extras provide anywidget and Voilà.

## Launch

From the repository root:

    .venv/bin/python -m voila examples/projector_editor.py --no-browser --port=8874 --VoilaConfiguration.extension_language_mapping=.py=python --VoilaConfiguration.language_kernel_mapping=python=python3

Open http://localhost:8874/. Stop the server with Ctrl-C.
The example creates or resumes expressions/port-reorder-demo.canvas.json.
Set BIRDTRACKS_EDITOR_SESSION to a different name/path for an independent demo.
Do not point it at an unrelated document. Save/reopen preserves exact values,
stable IDs, placement, routes, selection, and undo/redo stacks.

In a notebook, display the same existing canvas directly:

    from fractions import Fraction
    from birdtracks import Antisymmetriser, Projector, ProjectorSum, Symmetriser
    from birdtracks.projectors.widget import projector_sum_widget

    value = ProjectorSum((
        (Projector([Antisymmetriser((1, 2, 3)), Symmetriser((3, 4))]), Fraction(-2, 3)),
        (Projector([Symmetriser((1, 2))]), Fraction(5, 7)),
    ))
    canvas = projector_sum_widget(value, session="port-reorder-demo",
                                  detangler=False)
    display(canvas)

For programmatic reopen, use ProjectorCanvasSession.load(name).open(); the
shared protocol is restored from the persisted payload. Unlike the launch
example, directly constructing a canvas with session= writes that canvas to the
specified path; use the loader to resume existing work.

## Manual diagram and checks

The example is -2/3 A(1,2,3) S(3,4) + 5/7 S(1,2). The A is black and its
inputs are on its right. The product is nonzero; the A/S nodes share one line.

1. Drag the first A input handle down to the second. Its coefficient becomes
   +2/3; connections remain attached to the same labelled ports. The second
   term remains +5/7.
2. Swap two A output handles too. Two odd sides restore -2/3. Moving a handle
   across two slots is even and leaves the coefficient unchanged.
3. Repeat a swap to restore the prior arrangement. Use Ctrl-Z (Cmd-Z on macOS)
   to undo on the selected term; Ctrl-Shift-Z/Ctrl-Y or the contextual Redo
   port reorder button redoes it. The toolbar/local undo uses port history when
   a port transaction is available.
4. Move a node vertically or change a route, then reorder a port. That placement
   survives the reorder and its undo. Existing movement/routes form history
   boundaries in this first slice; their editing algorithms are still legacy.
5. Click Save immediately after a drag, then restart/reopen the example. The
   accepted coefficient/order and manual drawing survive without compensation
   being applied again. Accepted state is also persisted by the canvas's
   existing session writer.

The combined input/output command is atomic even though two separate browser
gestures are two actions. The tests exercise simultaneous odd/odd in one command.

## Gesture to Python to rendering

The existing port handle previews its order locally. On release it sends stable
term/node IDs, desired input/output orders, drawing metadata, and the base
revision through editor_request. editor_widget.py validates the request and
EditorSession.reorder constructs an exact Projector with one relative parity
compensation. The session retains one before/after transaction.

Python publishes one editor_state envelope containing the accepted coefficient,
orders, IDs, selection, placement, and routes. The shipped projector-widget.js
applies that envelope and renders the supplied magnitude/sign. It performs no
shared-session parity calculation. Pending saves wait in the same command queue;
older replies and invalid commands cannot replace accepted state. The existing
canvas's compatibility traits and configuration expose that accepted state.

## Scope and compatibility

Ordinary source editing, parsed-source commits, symbolic UI coefficients,
structural reconnection/replacement/expansion, and branch/merge provenance are
later slices. Create mode releases this shared evaluation session and continues
with existing creation behavior; entering evaluation on the opted-in canvas
creates a new shared session. Prefactor editing uses Create mode in this slice.
Default canvases keep their previous protocol. Generated rational whiteboard
result terms now use the shared editor; Python projects their exact occurrences
and written coefficients in one document update. Their IDs and undo stacks
persist in backend presentations.

Legacy orientation compensation and `port_swap_sign` metadata have been removed.
Old graph-only whiteboards should be regenerated; there is no compatibility
fallback. New shared snapshots encode the exact Projector and editor state.
No required dependency, compiled backend, or interactive full-collapse fallback
was added.

The six architecture-review concerns applicable to this slice are addressed by
exact persistence, protocol isolation, representation-sensitive history, explicit
factor ownership, fixed-topology stable IDs, and a port path without collapse.
Structural lineage and symbolic whiteboard persistence remain explicit later
requirements; see [ADR 0004](adr/0004-shared-editor-port-slice.md).

## Initial-slice verification

The final staged slice was exported to an isolated tree, imported from that
tree, and tested with the repository venv using `python -m pytest -q -r fEs`:
770 passed, 8 skipped. This includes 49 new exact/model/canvas tests and five
new browser gesture tests. The skips are three unbuilt optional Cython backend
checks and five training checks requiring the missing optional Torch package.
No lint/type-check suite is configured in pyproject.toml.

The full existing working tree was also tested before the final remount-ID
regression was added: 935 passed, 1 failed, 8 skipped. Its sole failure is the
pre-existing `test_stress_whiteboard_contains_every_exact_case` assertion in
the author's untracked mismatched-Young-layer stress fixture. It is not a missing
dependency or a port-editor failure; that unrelated work is not in this commit.
The final five-browser-test run passed after the remount fix.

A live Voilà page, using the real anywidget/kernel transport and shipped
frontend, additionally passed input dragging, coefficient rendering, keyboard
undo, and redo with no browser errors. The demo server was stopped after testing.

## Result-line follow-up verification

The follow-up adds 31 focused cases, using synthetic diagrams rather than the
author's example file. They cover topology-derived columns and complete routing
interfaces, contextual top/bottom recursion, explicit odd/odd and odd/even
orientations, correct new-line coefficient/diagram projection, product/sum
occurrences, persisted IDs/placement/undo, unary versus binary signs, and queued
saves surviving remounts before or after acknowledgement. Real browser controls
are connected to Python for the recursive-expansion checks. Port-command tests
also reject any interactive call to collapse.

Final full configured run: `python -m pytest -q -r fEs` — 967 passed, 1 failed,
8 skipped. The sole failure remains the pre-existing untracked stress-fixture
assertion named above. The skips remain three unbuilt optional Cython checks and
five missing optional Torch checks. There is no configured lint/type-check suite.
