# ADR 0004: Shared state for projector port redraws

## Decision

The first slice is opt-in on the existing evaluation canvas via
projector_sum_widget(..., shared_editor=True). Embedded whiteboard editors and
structural creation retain their existing protocols. Restoring a shared canvas
automatically restores its protocol.

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

## Compatibility and review resolutions

New snapshots contain an exact algebra codec payload plus a versioned editor
payload. New loads bypass legacy orientation compensation. The legacy readers
remain unchanged: old graph-only files preserve their existing interpretation.
They cannot always recover the original expression, since opposite exact values
can have identical old widget graphs. A live Projector/ProjectorConfiguration
provides authoritative algebra when initializing the shared drawing.

The port path never calls collapse, detangle, expansion, or mixed-term collection,
and never runs default layout during a redraw. Small collapse comparisons are
test oracles only. The architecture review's one-to-many lineage, symbolic
whiteboard result persistence, and full-collapse collection issues are deferred
until the corresponding structural/document operations are migrated. They are
not reused by this slice.

## Verification and use

See [the slice guide](../editor-layer-slice.md) for launch commands, a manual
diagram, the gesture path, and scope. Focused tests cover relative odd/even and
combined parity, products/sums, exact prefactors, representation-sensitive undo,
stable-ID persistence, manual drawing, stale/invalid requests, and a real browser
connected to Python. The shipped canvas was also exercised through live Voilà.
