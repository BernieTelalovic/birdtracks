# Maintaining the shared editing boundary

The shared-editor refactor is complete in `v0.2.2` on `main`. This is the coding
and review contract for subsequent changes, not another refactor plan. Read
[the architecture](architecture.md) and [ADR 0008](adr/0008-mandatory-editor-protocol.md)
for the implemented decisions. Preserve the existing gestures unless a new
user-facing behavior is explicitly requested.

## Ownership: choose the layer before adding code

| Responsibility | Owner and implementation boundary |
| --- | --- |
| Connectivity, ordered ports, exact coefficients, mathematical equality, identities | Immutable Python algebra values and their algorithms |
| Committed projector value, stable IDs, selection, placement/routes, local undo/redo | `projectors/editor.py`: `EditorState` and `EditorSession` |
| Committed pair value, styles, identity/revision, undo/redo | `projectors/pair_editor.py`: `PairEditorSession` |
| Source drafts, last valid notation, occurrence references, document revision | `projectors/whiteboard/document.py`: `DocumentSession` |
| Request validation/dispatch, exact result/source projection, host equation transactions | `editor_widget.py`, widget adapters, and `whiteboard/result_projection.py` |
| Drawing compilation and LaTeX output | Layout/display modules and `whiteboard/latex.py`, reading accepted owner state |
| Pointer/key handling, temporary previews, focus/caret, command transport | Shipped JavaScript views; never a second committed algebra owner |

All source paths above are under `src/birdtracks/`. Stable editor IDs and drawing
coordinates must never enter algebraic equality or hashing. Document ownership
does not mean copying a child value into another editable authority: occurrence
references resolve to the live projector/pair owner. Serialized document fields
are persistence/projection data, not permission to overwrite those owners.

## Add a gesture through the command boundary

1. Classify the intent as presentation-only, connectivity-changing, or an
   explicit calculation. Specify its exact before/after value and transaction
   boundary. Reuse an existing command where possible.
2. Put mathematical validation/transformation in Python. For an algebraic
   change, construct and validate the complete candidate before committing any
   value, presentation, revision, history, or host callback. Invalid edits leave
   all committed state unchanged.
3. Apply the edit through `EditorSession`, `PairEditorSession`, or
   `DocumentSession`, not by assigning rendering traits. Projector adapters
   dispatch through `editor_request`; pair and document adapters use
   `pair_editor_request` and `document_request`.
4. Include a request ID, current owner/occurrence identity, and base revision.
   Resolve stable IDs to algebraic indices only inside Python. Repeated requests
   must not repeat a successful transaction; stale/replaced occurrences must be
   rejected even if their source positions are reused.
5. Keep movement/typing previews local until the defined commit. A released
   drag makes one undo entry, not one per pointer move. Publish one accepted
   envelope containing the corresponding algebra and presentation.
6. Render the accepted envelope without triggering another edit. Keep queues
   attached to the model across view remounts. Callback publication must use
   current identity/revision checks; never reapply a captured old snapshot.

Existing host add/undo/save coordination notifications are not alternate value
protocols. New algebraic edits must not be hidden in those notifications or in a
render callback. Trusted Python initialization/import may seed an owner through
the existing validated adapters; browser projection writes are not that path.

## Coefficients and orientation: compensate once

A projector occurrence means `outer_factor * projector`. Preserve both members
in their supported exact domain; do not coerce symbolic factors into a rational
`ProjectorSum`, convert them to floats, or silently drop them during replacement.
Replacement branch coefficients multiply the parent occurrence factor once.

The Projector's raw coefficient belongs to its stored input/output orders.
`editor.py:project_port_orders` is the Python redraw translation. For an A, its
relative input and output parities multiply the raw coefficient once: odd/even
and even/odd negate it; odd/odd and even/even do not. An implicit coefficient is
exactly one, so it obeys the same rule as an explicit rational coefficient.
Port redraw preserves topology and mathematical value; an explicit permutation
or reconnection can change the operator and is a different command.

JavaScript may preview a prospective sign while dragging, relative to accepted
orders. That preview cannot update a coefficient, source factor, history, or
saved value. On commit, render Python's projection and discard the preview.
Do not add frontend sign-flip listeners or another reconstruction compensation.

When source owns a written prefactor, `result_projection.py` provides its
matching Python-derived `source_value` body. Parsing that body with the written
factor applies the factor once. This is an intentional translation projection,
not another value to independently edit or compensate. Keep ordered editor
equality separate from mathematical equality: a compensated redraw is still a
real representation/history change even when the expression is equal.

## Presentation must survive algebra and rendering

Evaluate movement and pure rerouting change presentation only. Create gestures
that reconnect strands remain Python-validated connectivity edits. Do not infer
connectivity or equivalence from visible crossings, port labels, or coordinates.

Before structural cleanup/collection, carry rewrite provenance through each
branch. Preserve surviving node/strand IDs within their occurrence, manual
anchors, colors, directions, selection, and unaffected routes. Allocate IDs for
new objects, arrange them locally, and repair only invalidated routes. Define
which occurrence's presentation survives an intentional term merge; do not try
to recover lineage after mathematical collection has erased it.

Recompiling a graph cannot reinstall default positions over accepted placement.
Respect `automatic_positions` and manual pinning. Keep packed display-column
routes distinct from algebra-layer/Create `free_levels`; the namespaces cannot
alias simply because they share a numeric index. Full relayout belongs to the
explicit, undoable Tidy action, not normalization, redraw, save, or expansion.

Keep operator layers as S/A boxes and straight free lines; permutations belong
to connectors between layers. Changes to connector width, painting, typography,
or export syntax belong in presentation/export code, not algebraic values.
Extend `birdtracks.sty` for a missing notation command without changing Python
mathematical semantics to accommodate its appearance.

## Drafts, undo, persistence, and asynchronous work

Source editing retains a draft and last valid notation/value during incomplete
parsing. Keep the existing single in-place surface, completion, and caret/focus;
do not replace the editing DOM on an unchanged acknowledgement. Rendered and
active diagram/pair views share the same occurrence owners.

Undo/redo restores exact ordered algebra and presentation together, with a new
revision. New edits clear redo; no-op/cancelled gestures add no entry. A generated
rewrite line is one host transaction, separate from local term history. Persist
the owner payload and its history, rather than replaying commands on load.

Save, export, and evaluation wait for pending child commits and source commands.
Save must preserve incomplete drafts as well as last valid values. Read accepted
owner values/configurations for calculation and export, not raw widget graphs or
frontend compatibility traits. Restore exact editor payloads before deriving
render data; stale saved graph caches cannot override them.

Do not restore `save_snapshot`, `term_sign_flip_request`, or
`expand_node_request` handlers, a `shared_editor=False` path, or browser writes
to Python-owned blocks/value projections. Read-only old-format import helpers
and pure dictionary export APIs may remain at explicit boundaries; they must
never become competing live editing paths or legacy sign compensation.

## Keep interactive work bounded

Reorder, move, reroute, reconnect, save, validation, and undo cannot invoke full
collapse, factorial expansion, or an implicit global detangler. Recursive
expansion and cleanup use bounded structural rules and provenance. Full
expansion remains the separate explicit `calculate_full` calculation path;
double-click's current behavior must not be replaced by a new warning popup.
Small exact-collapse comparisons are test oracles, not interactive machinery.

## Required review and regression checks

For every new command, test exact value/representation behavior, invalid and
stale rejection without state/history mutation, one-gesture undo/redo, and
save/reload. For rewrites, also test survivor IDs, untouched placement/routes,
and coefficient propagation. Cover negative/rational/unit factors and both
input/output parity where orientation is relevant.

Keep the same-command sequences conformant across canvas, standalone widget,
and whiteboard. Pair commands need value/style/history and stale-identity checks.
Frontend tests must drive the shipped view against actual Python owners, not
declare success from JavaScript's optimistic preview. Include delayed replies,
remounts, save during pending edits, blank creation, incomplete source, and
caret/focus where the changed path is affected.

Start with `tests/unit/test_editor_protocol.py`, `test_projector_editor.py`,
`test_editor_structural.py`, `test_editor_display_routes.py`,
`test_whiteboard_document.py`, `tests/conformance/test_editor_surfaces.py`, and
the relevant `tests/ui` interaction tests. Export changes also need
`test_whiteboard_latex.py`, including its compilation check. Use the repository
venv and verification proportional to the change; do not rerun unrelated suites
to conceal missing focused coverage.

Reject a change if it introduces a second value/sign authority, accepts an
unversioned browser snapshot, loses exact factors or survivor metadata, silently
relayouts manual placement, uses algebraic equality for redraw no-op detection,
or makes an ordinary editing command perform full collapse. New mathematical
domains or gestures require their own explicit contract and tests; this completed
refactor is not permission to assume those semantics.
