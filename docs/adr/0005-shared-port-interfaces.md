# ADR 0005: One port command across projector interfaces

## Decision

Evaluate-mode projector widgets and canvases use `EditorSession` by default.
Whiteboard inline objects, expanded named references, rational result rows, and
symbolic result occurrences use the same revisioned command adapter. Creation,
source parsing, structural rewrites, and global equation history are not migrated.

`project_port_orders` remains the only compensation implementation for a port
redraw. Relative input/output parity changes the ordered Projector coefficient
once. Commands never collect occurrences or collapse operators. The frontend
selects a drawing-only drag preview relative to accepted orders; it does not
publish a mathematical coefficient or source change during movement.

Each view renders the accepted `editor_state` envelope, including its exact graph,
orders, drawing, IDs, coefficient, and revision. Legacy individual trait updates
cannot replace that envelope. Commands are serialized per model across remounts;
old revisions or another occurrence's response are rejected. A completed drag is
one command and one undo entry. Detached inline children cannot publish into a
replacement occurrence occupying the same source position.

## Document projection

`whiteboard/result_projection.py` projects accepted occurrences into text and
serialized diagram data. Whiteboard synchronization invokes that compiler and
publishes its output; it does not compute port parity. Generated rational rows
retain ordered occurrences and all scalar-only terms. Symbolic rows retain typed
`outer_factor` values, occurrence ordering, and scalar-only contributions. Their
two possible factor-preview strings are compiled in Python.

Inline source can own a displayed factor separately from its diagram occurrence.
The projection transfers a relative minus into that source factor and emits the
matching `source_value` body. This body is a derived parse projection, not another
editable algebra authority. Calculation reads it with the surrounding source
factor exactly once; the shared editor keeps its compensated ordered value.
When source does not own a suitable factor, the canvas draws the accepted scalar
and the surrounding source stays unchanged.

Named-reference views retain their source expression and persist the accepted
drawing. Restoring a presentation accepts an exact payload mathematically equal
to the referenced value, rather than requiring identical serialized orientation.
Editor IDs, manual positions, routes, and history consequently survive redraws.

Frontend sign caches, source-sign mutation listeners, and the unreachable
`renderConfigured` implementation are removed. Shared children are not saved via
legacy frontend snapshots. Python stores accepted configurations; save and export
callbacks cannot merge a stale frontend drawing over them. Creation snapshots
remain a separate protocol, with a complete snapshot applied before evaluation
ownership is attached.

## Persistence and remaining scope

The exact editor payload is retained in configuration JSON, canvas sidecars,
typed whiteboard v2 documents, and readable whiteboard v1 containers. No special
sign migration is applied. Historical graph-only documents remain ambiguous as
documented in ADR 0004; regenerated documents carry exact values.

Movement/routing use their existing presentation bridge. Reconnection, expansion,
replacement lineage, source draft transactions, and document-wide undo still
belong to later stages. Symbolic port projection and persistence do not introduce
a new symbolic aggregate solver or migrate symbolic expansion.

See [the manual checklist](../editor-port-migration.md) and the shared surface
conformance/browser tests for verification. No visual redesign is part of this
stage.
