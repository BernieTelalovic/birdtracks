# 0007: One document for in-place whiteboard editing

Status: implemented on `feature/shared-editor-layer`.

## Ownership and boundaries

`whiteboard/document.py:DocumentSession` owns revisioned blocks, draft source,
last-valid source, parse status, and references to the existing live Python
occurrence editors. `ParsedSource` is immutable notation referencing those
occurrences, not a duplicate algebraic value. Diagram values remain in their
`EditorSession`; pair values remain in the registered Python pair owner.
`occurrence_value()` reads that live owner rather than a saved/frontend copy.

Source parsing checks notation completeness without evaluation, simplification,
or collapse. Incomplete source updates the draft and error only; committed
notation, definitions, diagram/pair values, and saved presentation remain valid.
`source_translation.py` supplies an idempotent, token-aware command-spacing view
to both Python algebra parsers. Compact TeX such as `B\def\pair` keeps command
boundaries through marker substitution. Original notation and offsets, text/font
groups, and compound symbol names remain unchanged. This adapter does not own or
apply prefactors; existing coefficient translation/multiplication remains exact.
Coefficient translation still belongs to `result_projection.py`. A diagram edit
during an incomplete draft updates the committed source and occurrence snapshot
without replacing the draft. Neither source rendering nor activation computes
algebraic signs or applies an additional coefficient compensation.

The widget adapter publishes `document_state` and accepts revisioned
`document_request` messages for source, field-level block patches, and validated
pair edits. Existing diagram commands retain their shared editor boundary.
Parse metadata is Python-owned and cannot be overwritten or removed by a
frontend patch. `blocks` remains the persistence/legacy projection, not the
current frontend state authority.

## Synchronization and editing

The JavaScript transport belongs to the model, not a mounted view. It sequences
source transactions, rebases rejected stale commands against Python's revision,
and finishes queued saves even when the view detaches. Older document and pair
envelopes cannot replace newer accepted projections. Save, export, and explicit
evaluation wait for queued document commands. No asynchronous parse worker or
extra runtime dependency is introduced.

Rows reuse their textarea and embedded editors across acknowledgements and
other-row updates. Pending text is a disposable display draft, never a frontend
algebraic commit. The existing permissive MathML renderer handles immediate
typing and completion; Python supplies committed parse status. Raw incomplete
source, partial commands, and rendered symbols use current source ranges for
mouse placement and navigation. Plain draft text moves character-by-character;
rendered operators remain atomic. External source changes map the selection
through the changed range instead of moving it to the end.

The author rejected the initial separate last-valid preview. Invalid/incomplete
source now uses **one in-place line** with a small parse indication; the last
valid value is retained internally, not rendered below the draft. Tab completion,
fraction editing, and explicit Shift-Enter evaluation retain their established
behavior. Clicking an embedded editor activates its contextual controls;
leaving hides them without discarding edits. Paper background and typography
are inherited, without additional window framing.

Pair redraws restore focused terms without stealing focus from external forms.
Embedded click routing uses the original event path because a box edit can
detach its SVG target before bubbling; consumed pair keys do not edit source.
Manual row insertion cancels older automatic calculation-follow viewport
targets, not calculations, and uses current toolbar geometry for visibility.
The scrolled toolbar stays above transparent source overlays and is excluded
from blank-paper hit testing.

## Persistence and scope

Optional `source_edit` metadata accompanies existing block source/snapshots in
the supported whiteboard containers. It records per-source revision,
`committed_source`, and `error`, so saving and reloading an incomplete draft
restores its last-valid occurrences. Existing document formats, LaTeX exporter,
and `birdtracks.sty` are unchanged; complete expressions retain existing output.
This is not a new full LaTeX parser or an algebra/diagram canonicalization stage.

Focused Python tests exercise invalid/stale atomic boundaries and draft reload.
Browser tests connect shipped JavaScript to actual Python owners and cover
typing, completion, caret geometry, activation, delayed replies, detached queues,
pair edits, and diagram movement. The running Voilà app is also inspected.
See [the walkthrough](../whiteboard-live-editor.md) for launch and verification.
