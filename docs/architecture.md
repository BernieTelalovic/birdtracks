# Architecture

Status: shared-editor refactor complete; merged to `main` and released in
`v0.2.2`. Future changes must follow
[the separation-of-concerns guide](editor-layer-maintenance.md).

Immutable Python permutation, projector, pair, and exact linear-combination
values define mathematical meaning. Algorithms, caches, and rendering are
separate from those values; Python remains the semantic reference.

`EditorSession` owns committed projector values, stable editor IDs, presentation,
and undo/redo. `PairEditorSession` owns pair values and styles with the same
revisioned ownership contract. `DocumentSession` owns whiteboard source/drafts
and coordinates occurrences. Widget adapters translate requests and publish
read-only projections; JavaScript manages gestures, draft previews, and focus,
not algebraic signs or committed snapshots.

All editor surfaces use these owners, including blank Create diagrams. See
[ADR 0008](adr/0008-mandatory-editor-protocol.md) for the communication boundary,
verification, persistence, and manual checklist, and
[the original plan](editor-layer-plan.md) for the full requirements and baseline
audit. The audit is historical, not a description of current ownership.
