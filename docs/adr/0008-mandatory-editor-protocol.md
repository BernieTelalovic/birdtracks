# ADR 0008: Mandatory Python-owned editor protocol

## Decision

Every projector editor, including a blank Create diagram, attaches an
`EditorSession`. Every editable pair attaches a `PairEditorSession`. A whiteboard
uses `DocumentSession` to own its source, drafts, occurrences, and generated
rows. There is no `shared_editor` opt-out. This supersedes the transitional
protocols described in ADRs [0004](0004-shared-editor-port-slice.md) and
[0005](0005-shared-port-interfaces.md), without changing their algebra convention.

The boundaries are:

- Immutable Python algebra values define connectivity, ordered ports, exact
  coefficients, validation, and identities.
- `editor.py` owns committed projector values, stable IDs, presentation, and
  undo/redo. `pair_editor.py` owns exact pair values, cell styles, identity,
  revision, and undo/redo. Neither draws or multiplies expressions.
- `editor_widget.py` translates validated requests into shared commands and
  publishes accepted rendering data. `whiteboard/document.py` owns source
  transactions; `whiteboard/result_projection.py` projects exact occurrences
  and source factors together. Widget adapters coordinate these owners.
- JavaScript maintains temporary gesture/source previews, focus, and command
  queues. It renders accepted state; it cannot publish committed algebra or
  replace it by copying a rendered graph back into Python.

## Commands, projections, and synchronization

Projector commands use `editor_request`; pairs use `pair_editor_request`, or a
document pair command for embedded occurrences; source uses `document_request`.
Each carries a request ID, owner/occurrence identity, and base revision. Successful
commands publish a new accepted envelope. Stale or invalid requests cannot change
the committed value or history. Duplicate acknowledgements do not repeat edits.

`graph`, positions, orders, coefficients, pair values/styles, blocks, and rendering
envelopes are read-only browser projections. Widget `set_state` boundaries reject
attempts to write them. Python initialization/import remains a trusted, validated
boundary. A source command cannot smuggle projector snapshots, generated values,
or pair history into a block patch. Replacing an occurrence invalidates the old
editor identity even if its source position is reused.

The retired save-snapshot, term-sign-flip, and expansion trait handlers are
removed. Term ordering/deletion go through the shared command adapter. Toolbar
add/undo and save-barrier notifications still coordinate host UI actions; they
do not own algebra or introduce a second sign/serialization implementation.

One released drag remains one committed transaction. Live antisymmetric parity
preview is drawing-only: Python applies relative input/output compensation
exactly once on commit. Odd/odd has product parity +1. Rational magnitude and the
canvas's outer sign are read from the owner, including after reload. When source
owns a written prefactor, its Python-derived `source_value` body prevents applying
that factor again during calculation; it is not another editable value.

Create-mode graph edits and coefficient controls remain local drafts until a
validated shared creation command commits them. A blank insertion strand is a
draft affordance, not a committed identity operator. Save and Shift-Enter wait
for child commits and drain source commands before consuming owner values.
Acknowledgement callbacks run after the complete comm update, not midway through
its document revision publication. Delayed render/parsing replies are rejected;
source acknowledgements do not reset an already-focused caret.

Recursive expansion remains bounded. Full expansion uses the explicit
`calculate_full` request and calculation path, not the interactive command
implementation. Both publish typed rewrite provenance and shared descendant
states. The old canvas/whiteboard expansion reconstruction path is removed.
Owned local placement is not passed through an implicit global layout policy.
An unchanged source blur does not detach an embedded editor during its gesture.

## Persistence and export

Configuration JSON and canvas sessions restore exact editor payloads rather than
reconstructing algebra from graph caches. Whiteboard persistence stores document
drafts, last valid values, and occurrence editor payloads. Pair payloads include
styles, stable identity, revision, and both history stacks. The same owners are
read by calculation and LaTeX export. An old drawing cache cannot overwrite a
newer accepted value or manual placement.

Outer document containers and supported file extensions are unchanged. Legacy
filename/read-only import adapters and pure dictionary export helpers are not
alternative live editing protocols. Historical graph-only diagram files may
need regeneration, as agreed with the author. No legacy orientation compensation
is retained. The public `shared_editor` keyword is removed; callers should omit
it. `birdtracks.sty`, mathematical simplification rules, and visual design are
unchanged in this cleanup.

## Verification

Use the repository venv. The focused unit/conformance run covering editor state,
protocols, structural rewrites, orientation, layout, document/pair translation,
LaTeX, persistence, backend rows, and cross-interface commands passed **559
tests**. All `tests/ui` passed **268 tests**, including actual Python owners
connected to the shipped frontend. The live interface was also visually inspected
with a projector and pair on one document surface.

The final focused run excludes
`test_whiteboard_full_expansion_collects_equal_permutations`: it previously passed
in this cleanup, but takes several minutes and was not rerun. The affected
training-policy check is skipped because optional Torch is absent, not because
of a failure; a dependency-free protocol test independently forbids an implicit
global layout policy during shared expansion. No full-repository test run is
claimed for this stage; verification
is limited to affected areas at the author's request. No lint/type-check suite
is configured in `pyproject.toml`.

## Launch and manual verification

Restart an existing notebook kernel or whiteboard process so it loads the new
Python and shipped JavaScript. From the repository root:

```sh
.venv/bin/birdtracks-whiteboard --debug
```

For a standalone canvas, use the Voilà command in
[the canvas guide](../editor-layer-slice.md), or display
`projector_sum_widget(value, detangler=False)` in a notebook. No opt-in argument
is needed.

1. Start a fresh board with `A\def \birdtracks`. Activate the diagram, add an A
   with two or three strands, save, and press Shift-Enter. The blank insertion
   affordance and Create-to-Evaluate transition should still work normally.
2. Drag two A inputs across each other; watch the live sign. Release, undo, and
   redo. Swap two outputs too: the second odd reorder restores the sign.
   Repeat with `-2/3` and with an omitted prefactor. Move an operator and reroute
   a strand before reordering; those placements must survive.
3. Use a top/bottom recursive expansion control, then double-click for full
   expansion. Verify the new line, signs, and unchanged surviving placement.
   Save immediately after a drag/expansion; reopen the canvas/whiteboard and
   verify exact values, IDs, colors, and available undo/redo.
4. On another row enter `B\def \pair`. Add several boxes without refocusing,
   color one, undo/redo, and save/reopen. Try `B\otimes B`. Values and styles
   should come from the same pair owner before and after evaluation.
5. Type an incomplete command or fraction, move the caret, use Tab completion,
   and leave/re-enter the row. Keep one in-place editing surface, the draft,
   and the last valid value internally. Insert a row in the middle with Enter;
   focus stays there without scrolling to the document bottom.
6. Export to LaTeX after a recent edit. Check multi-layer connectors, boundary
   colors, pair labels/styles, and prefactors against the accepted document.

Protocol poisoning, stale revisions/identities, duplicated requests, and replay
of a modified drawing cache are covered by `test_editor_protocol.py`; they are
not manual UI operations.
