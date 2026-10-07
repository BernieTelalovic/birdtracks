# ADR 0004: Shared state for projector port redraws

## Decision

The opt-in scope below records the first slice. [ADR 0005](0005-shared-port-interfaces.md)
extends it to every evaluate-mode projector surface by default.

The first slice is opt-in on the existing evaluation canvas via
projector_sum_widget(..., shared_editor=True). Generated rational whiteboard
result terms now use that same editor automatically. Structural creation keeps
its separate protocol. Restoring a shared canvas or result term restores its
protocol and IDs.

EditorState owns an immutable ordered Projector, an exact outer factor, stable
term/node/strand IDs, drawing metadata, selection, and revision. Node IDs map to
sequence indices; strand IDs map to the fixed internal connections followed by
input/output boundaries. This slice never changes that topology. Drawing data
uses the existing indexed positions/routes at the compatibility boundary; IDs
are not included in algebraic equality or hashing.

A term means outer_factor * projector. Rational canvas magnitudes live in the
Projector coefficient; the existing canvas's +/- separator is retained as the
outer factor. The model also supports exact symbolic outer factors, but their
whiteboard/UI integration belongs to a later slice. Ordinary ProjectorSum is
used only for rational aggregate values, never to store ordered occurrences.

Reorder validates relative input/output permutations in Python. The product of
their antisymmetric parities multiplies the raw coefficient once; topology and
normalization remain fixed. The existing Projector constructor derives canonical
coefficients. The frontend renders Python's magnitude/sign projection and does
not compute parity for shared sessions. Explicit permutations and reconnection
are distinct operations and are not implemented by this redraw command.
An omitted prefactor is the exact unit coefficient: an odd-side redraw makes
that displayed unit negative, just as it negates an explicit rational prefactor.
Odd input and odd output together multiply by +1, not by another compensation.

Editor equality compares serialized ordered algebra and drawing data, excluding
revision. Mathematical equality cannot detect a compensated redraw. One released
gesture creates one undo transaction; cancellation/no-op creates none. Undo/redo
restores drawing and algebra with a new revision. New edits clear redo. The
session's exact payload and both history stacks persist without replaying commands.

One synced editor_state envelope publishes accepted algebra and presentation.
Requests identify the occurrence, command, and base revision. Python rejects
invalid/stale requests; JavaScript serializes its requests, rejects older state,
and queues Save behind a pending gesture. Duplicate successful requests do not
create additional history entries. Legacy save snapshots cannot overwrite a
shared session. Existing movement/routing are bridged as presentation checkpoints
and history boundaries; their algorithms/undo model are not migrated here.
The JavaScript request queue belongs to the model, not its disposable view.
Result text updates can remount a view without losing a pending acknowledgement
or queued Save; a new view also consumes acknowledgements received while detached.

## Compatibility and review resolutions

There is one coefficient convention: the raw coefficient belongs to the stored
input/output orders. `project_port_orders` is the pure Python translation used
by editor commands, initial rendering, and result generation. Preserving
explicit orders applies no compensation; choosing new orders applies their
relative antisymmetric parity once. Layout chooses orders but does not compute
signs. New result text and embedded values are projected together; JavaScript
does not rewrite Python-owned result signs.

The legacy `port_swap_sign` metadata and reconstruction compensation have been
removed. Exact algebra/editor payloads are authoritative. Old graph-only
whiteboards have no compatibility guarantee and should be regenerated, as
requested by the author; no fallback compensation branch is retained.

Display columns follow traced operator dependencies, not local port labels.
The detangler scores complete column interfaces, separate from algebra layers.
Result-line formatting lives in `whiteboard/result_projection.py`, separate
from document synchronization and algebraic simplification. A result-line port
transaction preserves ordered occurrences and never collects them.

For example, with `p = Projector([Antisymmetriser((1, 2, 3))])`:

```python
from birdtracks.projectors.editor import project_port_orders

drawn = project_port_orders(p, {0: {"input": (2, 1, 3)}})
assert drawn.coefficient == -1
assert drawn.collapse() == p.collapse()  # Small test oracle, not an edit step.
```

The port path never calls collapse, detangle, expansion, or mixed-term collection,
and never runs default layout during a redraw. Small collapse comparisons are
test oracles only. The architecture review's one-to-many lineage, symbolic
whiteboard result persistence, and full-collapse collection issues are deferred
until the corresponding structural/document operations are migrated. They are
not reused by this slice.

During a port drag, the canvas previews only the drawn sign using parity
relative to the last Python-accepted orders and displayed sign. It does not
publish port orders, coefficients, or document source during movement. Release
still sends one Python-owned transaction; acceptance rebases the preview,
while cancellation or rejection restores the accepted drawing. The coefficient
magnitude, undo history, and persistence remain Python-owned.
If the whiteboard owns the visible prefactor, a DOM-only preview notification
updates its text prefix in place instead of drawing a second canvas prefactor.
This never changes block source or remounts the canvas during the gesture.

## Verification and use

See [the slice guide](../editor-layer-slice.md) for launch commands, a manual
diagram, the gesture path, and scope. Focused tests cover relative odd/even and
combined parity, products/sums, exact prefactors, representation-sensitive undo,
stable-ID persistence, manual drawing, stale/invalid requests, and a real browser
connected to Python. The shipped canvas was also exercised through live Voilà.
