# 0006: Shared structural editing and explicit rewrite provenance

Status: implemented on `feature/shared-editor-layer`.

## Boundary and ownership

`EditorSession` owns the exact ordered Projector, rational occurrence factor,
stable object IDs, committed presentation, revision, and undo/redo history.
`editor_widget.py` adapts the same commands for the projector widget, canvas,
and authored, parsed, generated, and symbolic whiteboard occurrences. JavaScript
owns a disposable gesture preview, not committed algebra or sign compensation.
The model-owned request queue survives view remounts. Requests carry occurrence
ID, request ID, and base revision; stale, detached, or invalid requests cannot
replace a newer accepted state.

Movement and strand rerouting commit presentation only: they retain the exact
Projector object. A completed drag is one transaction; cancellation restores
the preview without adding history. Evaluate movement is presentation-only.
Create horizontal movement retains its existing reconnect/splice meaning.
Python validates complete connectivity proposals and endpoint swaps before
committing. Partial swaps into occupied inputs, unknown ports, incompatible
boundaries, and unsupported cyclic render graphs leave committed state intact.
Incomplete initial creation remains a local draft until a valid graph is saved.
The first accepted Save attaches its session and document observers without
rebuilding the widget. Mode changes retain that occurrence and its history;
Save acknowledgements advance monotonically, including this first-save bridge.

The command boundary includes `move`, `reroute`, `reconnect`, `creation`,
`replace`, bounded `expand`, explicit `tidy`, and the existing reorder/history/
save commands. Arbitrary subgraph replacement is an internal API, not a new
selection gesture. The identity provider supplies a replacement Projector and
bijective input/output cut maps. Python checks the splice's validity, not a
factorial equivalence proof. Algebraic identity correctness belongs to that
provider and focused exact tests.

## Exact coefficients and IDs

The previous slice's orientation convention is unchanged: a coefficient belongs
to its stored input/output orders. A redraw permutation applies relative
antisymmetric input/output parity once through `project_port_orders`.
Reconnection changes the operator rather than compensating it.
Replacement computes its scalar from the canonical coefficients of the old
value, replacement, and unit splice; it does not reuse frontend signs.
`whiteboard/result_projection.py` owns authored/result coefficient translation,
including rational magnitudes, negative signs, and external symbolic factors.
It projects generated text and ordered occurrences together.

Survivor IDs are transferred explicitly by the splice, never recovered by
matching equal algebraic nodes. Identity is scoped by `(term_id, object_id)`:
branch descendants have new occurrence IDs and copied survivor object IDs.
Introduced nodes/internal strands receive new IDs; surviving cut strands keep
their IDs. Rendered boundary arrays can be sorted by port, while persistence
orders them by boundary label. The adapter therefore maps IDs by actual edge
endpoints, never by zipping those arrays.

## Rewrites and presentation

`editor_rewrites.py` performs local algebraic splices with explicit provenance.
`editor_presentation.py` transfers paint/routes and projects rendering corridors.
Surviving positions are copied exactly. Introduced nodes are placed near the
removed operator, reusing a compatible survivor column where possible. Local
packing reserves actual box widths and a crossing gap; it does not squeeze
visible operators into overlapping coordinates when the old gap is too narrow.
Only strand controls outside
their new spans or obstructed by introduced operators are repaired. Rendering
derives missing corridors against committed positions; it cannot install a
fresh default layout into editor state. Full placement reset is an explicit,
undoable `tidy` command.

Evaluate free-line controls use `presentation.display_routes`: stable column
anchor node ID → stable input-boundary strand ID → nonnegative integer row.
A packed display column is NOT an algebra layer, and an output boundary label
is NOT necessarily the strand's input identity through a permutation. The
adapter annotates the display projection with these identities; JavaScript
previews their rows and submits one `reroute` transaction, including any column
packing positions. Python validates the free-strand/column domain, reserves
manual rows before defaults, and repairs collisions before commit. Every free
strand has a handle, including automatically allocated ones.

Structural transfer remaps column anchors by surviving members and strands by
their explicit IDs. Only invalidated controls are repaired. `free_levels` and
concrete algebra-layer `strand_routes` remain isolated to Create/legacy hints;
Evaluate rendering never writes its packed columns back into those namespaces.
The optional presentation field is carried by the existing editor payload and
history, so widget configuration, canvas JSON, and whiteboard formats require
no format-version change. Tidy clears both routing namespaces explicitly.

Display columns express dependencies, not a promise that all their members have
the same saved x-coordinate. The frontend's geometric routing traverses actual
occupied box slabs, including staggered operators in endpoint columns, and keeps
crossings out of unrelated box interiors during port previews. It also respects
fractional/manual y-positions. This projection changes neither accepted placement
nor algebra; older tightly spaced saved rows require explicit tidy or regeneration
to adopt the improved automatic spacing.

Top/bottom recursive expansion uses the existing raw two-branch identity for
every supported size, including size two. No collapse, detangler, factorial
node expansion, or mixed-term equivalence search runs in that command.
Double-click requests full expansion directly, without a warning popup, as
requested by the author. It remains a separate calculation rather than an
interactive editing command. That calculation may remove known zeros and collect
fully expanded permutation occurrences, retaining the first drawing. A linear
boundary traversal supplies the algebraic aggregate for completely expanded
wiring; it never rewrites the committed drawings or collapses mixed S/A terms.

Document hosts insert the whole next equation line as one undoable action.
Local term edits undo first; then undo removes the generated line, and redo
restores its exact occurrence payloads. Canvas redo lines and whiteboard parent
redo blocks persist across reload. Inline expansion is supported for a single
authored diagram with a literal rational prefactor; composite authored formulas
must first be evaluated and expanded on their result line, preventing an
implicit full algebraic evaluation in an interactive edit.

## Persistence and verification

Existing configuration JSON, canvas v1 sidecars, and whiteboard v1/v2 containers
retain their schemas with additional editor/presentation/history payloads.
Loading an accepted editor payload takes precedence over legacy drawing fields.
No old orientation-compensation fallback was reintroduced. Document schema
compatibility does not promise reconstruction of old graph-only orientation
semantics, which the author previously allowed regenerating.

Focused tests cover small exact S/A recursive identities, products and sums,
survivor IDs/placement, invalid reconnections, paint and wire-ID transfer,
structural undo/redo, whole-line undo/redo after reload, and shared-command
conformance on all six surfaces. Browser tests load the shipped frontend and
connect gestures to Python. See [the structural slice guide](../editor-structural-slice.md)
for diagrams, launch instructions, gesture checks, and recorded results.

No visual redesign, backend change, required dependency, or unrelated editor
migration is part of this stage.
