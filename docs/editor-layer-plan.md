# Shared editor layer: requirements and stage-one audit

Historical requirements and baseline audit. For the implemented mandatory
communication boundary and latest verification, see
[ADR 0008](adr/0008-mandatory-editor-protocol.md). The requirements below remain
intact; references to legacy behavior describe the inspected baseline.

Status: inspection and proposal only, 2026-10-07 (Europe/Copenhagen).
Branch: feature/shared-editor-layer, created from feature/permutation-core at
8396c4f04663ea01e8f692a1a60b723f56a7cc65.

The inspected baseline includes the author's existing uncommitted changes and
untracked modules, tests, and whiteboard examples. It is not a clean-commit
baseline. This stage adds this document; it does not implement editor commands,
rewrite the UI, or alter algebra. The birdtrack-algebra skill guided the exact
orientation checks and use of the repository venv.

The current-stage request is to trace port reordering, signs, movement, routing,
expansion, undo, saving, and loading across the canvas, projector widget, and
whiteboard; identify state ownership, duplication, and stale overwrites;
document coefficients and orientation; propose the smallest shared boundary;
retain relevant tests, identify acceptance gaps, record the baseline, and finish
with an incremental implementation sequence and specific files.

## Full supplied requirements

The original brief is reproduced below in full, including requirements for later
stages. Those later behavior changes are not implemented in this stage.

Implement a shared editing layer for birdtracks so the projector canvas, widgets, and whiteboard use the same rules for changing diagrams. Read AGENTS.md and inspect the current implementation before making changes. Reuse existing algebra and serialization where possible.

**Required behavior**

- Python algebra owns mathematical meaning: connectivity, antisymmetric port ordering, coefficients, equivalence, and allowed transformations.
- A shared editor model owns the current algebraic value, drawing arrangement, selection, and undo/redo.
- Frontends translate gestures into shared commands and render the resulting state. They must not independently calculate algebraic signs.
- Preserve user-chosen operator positions, strand routes, and port arrangements through edits, calculations, and save/reload.
- The whiteboard renders while typing. Clicking rendered content exposes its source or birdtrack/pair editing controls within the document surface. Embedded widgets should share the surrounding typography and background, with controls visible when active.

**First inspect and document existing behavior**

Trace how each interface currently handles port reordering, coefficient changes, movement, expansion, serialization, and loading. Identify duplicate implementations and competing sources of state.

Write down the existing antisymmetric orientation convention before changing it. Distinguish ordered ports, connectivity, visual crossings, and canonical orientation. Avoid introducing a second sign convention.

**Implement shared state and commands**

Use immutable algebraic values inside an editor state with separate presentation metadata. Keep stable editor IDs for nodes and strands; translate these IDs to algebraic node indices as needed. Editor IDs and coordinates must not affect algebraic equality or hashing.

Provide shared commands for:

- Moving operators and rerouting strands.
- Reordering input or output ports.
- Reconnecting strands.
- Applying algebraic identities and replacing subgraphs.
- Editing and committing parsed source.

Each command must produce a validated state transition. Update algebra and presentation atomically, as one undoable action. On failure, preserve the previous state and provide a useful error. Reject stale asynchronous results rather than overwriting newer edits.

Record which objects survive a transformation so their presentation metadata can be retained. Lay out new objects locally; do not automatically rearrange the entire diagram.

**Antisymmetriser sign contract**

Ordinary port rearrangement is a redraw of the same mathematical expression. For an antisymmetriser, calculate the relative input and output permutation parities in Python:

sign = parity(input permutation) × parity(output permutation).

An odd combined parity must flip the displayed coefficient exactly once, compensating for the new orientation so the complete expression remains equivalent. An even combined parity must leave the coefficient unchanged.

This must work inside products and sums, with positive, negative, rational, and supported symbolic coefficients. Preserve normalization and surrounding term coefficients.

Explicitly applying a permutation as an algebraic operation is a different command: it changes the operator according to the algebra rather than automatically compensating to preserve the old expression.

Visual strand crossings alone do not determine parity. Moving a node or changing a routing control point does not change the algebra. If a gesture changes port order or connectivity, classify it accordingly.

Verify how existing canonical coefficients and orientation signs implement this contract. Do not apply compensation in both the algebra and frontend.

**Canonicalization and layout**

Keep mathematical canonicalization separate from the editable drawing. Canonicalization must not reset user placement or silently reorder displayed ports.

Use automatic layout for initial placement, newly introduced objects, and an explicit “tidy” action. Do not impose a tallest-S/top or tallest-A/bottom convention in this implementation.

Preserve manual placement and routing wherever topology permits. If a route becomes invalid after a structural edit, repair only the affected portion.

**Whiteboard behavior**

Keep one document model with rendered and active editing states for inline objects. Switching between them must not create independent copies of the mathematical value.

While typing incomplete or invalid source, retain the draft and last valid rendering without committing invalid algebra. Show a local parse indication. Successful parsing commits through the shared editing layer.

Preserve caret/focus during rendering updates. Prevent delayed parsing or rendering from replacing newer source. Clicking outside an object returns it to rendered mode without losing its edits.

Use contextual handles and controls rather than framed, separately styled embedded windows. Preserve current LaTeX output and the working birdtracks.sty behavior.

**Implementation sequence**

1. Implement antisymmetriser port reordering through the shared layer in one interface, including undo and persistence.
2. Connect the remaining interfaces to the same command.
3. Migrate movement, routing, reconnection, expansion, and replacement.
4. Implement seamless whiteboard rendering/editing transitions.
5. Remove superseded frontend logic after the shared paths are verified.

Complete these stages incrementally; do not perform an unrelated rewrite or redesign the solver. Do not introduce full permutation expansion into interactive edits. Use collapse only for small-case correctness checks.

**Acceptance checks**

Add focused algebra/state tests and browser interaction tests covering:

- One odd input reorder: coefficient flips and the expression remains equivalent.
- One odd output reorder: same result.
- Odd input plus odd output reorder: coefficient is unchanged.
- Even reorder: drawing changes, coefficient does not.
- Repeating the same swap twice restores the original expression and arrangement.
- Equivalent reorder sequences produce consistent signs.
- The above cases inside a multi-node product and a sum, including negative and rational prefactors.
- Node movement and pure rerouting preserve the algebraic value.
- Undo/redo restores both mathematical and presentation state.
- Saving and loading preserve signs, port orders, positions, and routes without applying compensation again.
- Expanding or replacing a subgraph preserves unaffected objects and their placement.
- Invalid reconnection leaves state unchanged.
- All interfaces produce equivalent results for the same command sequence.
- Incomplete whiteboard source preserves the draft and last valid value.
- Rapid typing and delayed responses do not restore stale content.
- Activating/deactivating inline editing preserves focus appropriately and does not lose changes.

Use small exact-collapse comparisons as an independent oracle for sign preservation. Keep larger interaction checks symbolic.

Run the relevant tests and configured checks. Visually inspect the actual canvas and whiteboard; backend tests alone do not establish seamless interaction. Report any checks that could not run.

In the handoff, explain the state ownership, trace one port-reordering command from gesture to Python to rendering, list remaining legacy paths, and provide the verification results so I can learn how to maintain this layer myself.

## Existing interfaces and authoritative state

Paths below are relative to the repository root. Function names identify the
inspected code; several files already have author changes.

| Surface/layer | Entry points | Current authority and copies |
| --- | --- | --- |
| Projector canvas | src/birdtracks/projectors/canvas.py: create; widget.py: projector_creator, projector_sum_widget; canvas_session.py | Canvas is a Python wrapper around term widgets, with _history, _line_states, _term_editors, _term_signs, and a separately saved _saved_projector_sum. |
| Single projector widget | widget.py: projector_widget | _source_projector is the opening value; _configured_projector and configuration are the last saved value/snapshot. Synced graph, port_orders, boundary_orders, effective_coefficient, positions, free_levels, and line_colors can describe newer edits. |
| Active projector renderer | static/projector-widget.js: renderCreator | Mutable browser-local nodes, connections, routes, inputOrder/outputOrder, initial orders, BigInt coefficient components, directionMode, and undoStack drive gestures. Trait changes are checkpoints, not one Python editor state. |
| Whiteboard | whiteboard/widget.py: whiteboard; static/whiteboard-widget.js: renderWhiteboard | blocks carries source, occurrence snapshots, calculation_value/terms, and backend_presentations. Python also maintains explicit and generated child widgets plus WhiteboardStores. Browser textarea values, mounted children, orientation-sign caches, and model.blocks coexist. |
| Algebra and persistence | projector.py, projector_sum.py; configuration.py; whiteboard/projector_codec.py, sidecar.py | Immutable Projector/ProjectorSum define exact meaning. ProjectorConfiguration freezes arbitrary JSON presentation beside a Projector. The algebra codec and saved widget graphs are separate ways to reconstruct mathematical values. |

These are not three independent canvas implementations. Both the full canvas and
whiteboard projector children call projector_widget and the same active
JavaScript renderer. The whiteboard adds source/prefactor handling and document
persistence; the full canvas adds equation rows, term signs, and history.

ProjectorWidget.projector explicitly returns the last saved projector, not the
live gesture state. calculate_projector_blocks and evaluate_projector_expression
consume _configured_projector. Other canvas operations reconstruct a value from
synced graph/orders. Thus there is currently no single live authority spanning
all operations.

renderConfigured remains in projector-widget.js with its own parity, drag,
packing, and save implementation. The module's default render calls renderCreator
for every ordinary projector; renderConfigured is currently unreachable through
that dispatch. Treat it as legacy code, not a third active path.

### Trace by operation

| Operation | Canvas/single widget path | Additional whiteboard path |
| --- | --- | --- |
| Input/output port reorder | renderCreator.startPortReorder mutates an ordered side during pointermove, snapshots local undo once, then syncPortOrders publishes orders and currentGraphCoefficient. Python reconstructs at save/expansion using _projector_from_state. Existing Python permute_node_ports already implements an equivalent compensated S/A move, but the gesture does not call it. | mountEmbeddedProjectors listens to child graph/orders/boundary orders; projectorOrientationSign computes parity again, compares a cached sign, and flipProjectorTermSign rewrites editor.value and blocks.source. |
| Coefficients and signs | widget_graph supplies coefficient/base_coefficient/port_swap_sign. JavaScript calculates currentGraphCoefficient and displayedTermSign. Canvas append_row splits magnitude and external term sign; flip_term_sign updates Python's signs/history. Local fraction editing updates browser coefficients and sign requests. | Numeric/unary source signs, prefactor_owned, child coefficient, result-source coefficients, symbolic prefactors, and cached orientation signs all participate. _result_source uses another Python presentation-sign calculation. |
| Movement | dragNode changes layer/level. Same-layer movement packs a column; evaluate mode persists positions. In create mode a horizontal move bypasses and splices the operator into strands, then saves: that gesture can change connectivity and operator order. | Same child gesture; positions reach document storage through captured explicit snapshots or backend_presentations. No separate whiteboard movement algebra. |
| Routing | drawRouteHandle mutates connection.route, sometimes repacks neighbouring operators/strands, then persistPresentation writes positions/free_levels. Routes are keyed by layer and boundary/strand labels, not stable strand IDs. | captureState/saveEmbeddedState store child snapshots; generated terms store backend_presentations. |
| Reconnection | startConnection/startAttachedConnection manipulate browser connections. validConnection uses source/target side and drawn x ordering. validationError and Python Projector validation act later. | Same child logic; no shared document transaction for reconnection. |
| Expansion/replacement | saveProjector serializes first, then emits expand_node_request. ProjectorWidget's observer and canvas expand_selection both call _expand_from_canvas_request. expand_node/recursive_expand_node use existing simplification, collection, contraction, and detangling; canvas appends a new equation row with newly built widgets. | on_backend_expand reads the child expansion and append_backend_expansion makes a generated block. _result_source writes placeholders and encoded values; color inheritance uses _expanded_line_colors/_calculation_color_map. Placement/routes are not transferred with explicit survivor maps. |
| Undo | Browser undoStack restores local nodes, connections, coefficient components, nextLabel, and term negativity. Canvas undo_equation_line removes an equation row; on the first row it delegates to local_undo_command. No shared redo stack. | Shift-Backspace restores a calculation group by dropping generated rows. Text editing relies on textarea/native editing behavior; pair widgets have another local history. These are distinct histories. |
| Save | saveProjector sorts nodes by layer/level, renumbers nodes/ports/strands, synthesizes identity nodes for free strands, publishes traits plus save_snapshot. _save_projector reconstructs Projector and ProjectorConfiguration and acknowledges saved_revision. Canvas persist writes _canvas_editor_state for each row; Save coordinates child acknowledgements. | captureState requests child saves and merges snapshots into blocks. on_saved also stores snapshots and recalculates stores. persist writes typed sidecars on blocks/title/save/color changes. Export captures state first. |
| Load | ProjectorCanvasSession.load accepts legacy canvas JSON and whiteboard-backed state. expression and projector_canvas_from_session rebuild values through _projector_from_state and external term signs. projector_widget replays configuration and rebuilds derived display data. Canonically collected older terms can trigger fresh widgets for that row. | _load_whiteboard_state reads typed v2 or migrates v1. sync_embedded_projectors prefers occurrence snapshots, then saved named values, then a blank creator. sync_backend_calculation decodes generated values and conditionally replays backend_presentations. |

saveProjector temporarily changes the local graph to make a serializable value,
then restores live nodes/connections/nextLabel. Its published graph can therefore
have different indices and labels from the still-mounted local graph.
persistPresentation writes the local indices into presentation traits afterward.
Stable identity must bridge this boundary before migrating structural commands.

### Source editing and rendering

whiteboard-widget.js updateSource publishes blocks.source before attempting its
local LatexParser rendering. Successful rendering sets lastValidSource; failure
calls renderInvalidSource, which replaces the rendering with raw invalid text,
retains inline marker anchors, and shows an error title/ARIA label. lastValidSource
is a browser rendering aid, not a separately committed algebraic document value.
There is no explicit draft/last-valid-value transaction.

renderSource handles markers and source ranges; mountEmbeddedProjectors
asynchronously resolves/renders children. showEditor/showRendered, the textarea,
source-range hit testing, positionCaret, active-fraction handling, and
updateEmbeddedModesForCaret keep rendering visible during editing. renderBlocks
retains unchanged rows and avoids replacing an active editable row. These
mechanisms already protect many focus/gesture cases and should be reused.

Pair objects follow _blank_pair_widget/on_pair_changed, PairExpression.from_state,
diagram_codec, and renderYoungCreator, with their own browser history. The shared
document should reference their one current value through a small adapter;
projector port-sign commands should not introduce a new pair algebra.

### Duplication and overwrite risks

The following separates inspected behavior from risks that need acceptance tests.

1. **Multiple sign owners (observed).** Projector._port_order_sign,
   canonical._canonical_orientation_sign, layout._crossing_reduced_port_orders,
   widget._relative_order_is_odd, renderCreator.portParityIsOdd,
   renderConfigured.effectiveCoefficient, and whiteboard.projectorOrientationSign
   compute related but different parities. Canonical topology parity is genuinely
   algebraic; renderer/source compensation is duplicated. Existing UI tests check
   source signs without an end-to-end exact-value comparison.
2. **Unversioned save overwrite (observed missing guard).**
   ProjectorWidget._save_projector accepts any nonempty snapshot and assigns its
   revision to saved_revision. It does not compare against an edit revision,
   reject an older save, or build all validated fields before assigning
   _configured_projector. save_snapshot protects against mixed trait arrival,
   but does not establish freshness or failure atomicity.
3. **Checkpoint versus live value (observed).** Port reorder synchronizes traits
   without updating _configured_projector. Movement/routing in evaluate mode
   persist presentation only. A calculation based on the last saved value can
   lag a gesture unless its save handshake completes first.
4. **Source sign plus child compensation (verified boundary counterexample).**
   With p = Projector([Antisymmetriser((1, 2))]), q =
   permute_node_ports(p, 0, "input", 0, 1) is equal to p. Passing q as the saved
   marker value to evaluate_projector_expression with source r"-\birdtracks"
   produces -p, not p. Python already owns the compensating sign in q; applying
   the source minus again changes the complete value. This is a direct
   reconstruction/parser check, not a claim that every browser save takes this
   precise path. Browser, save, parse, and generated-result behavior need one
   combined oracle test.
5. **Generated algebra versus cached source/presentation (observed).**
   sync_backend_calculation uses calculation_value/terms and latest generated
   definitions. Its graph-equality guard prevents replaying presentation on a
   different graph, but an old presentation for the same graph has no edit
   revision. Whiteboard source orientation listeners can update textual signs
   without updating calculation_value/terms atomically. The displayed and
   calculated expression can consequently use different state owners.
6. **Positional identities (observed).** Keys such as block:projector:occurrence
   and block:backend:index change when markers/terms move. Snapshot pruning and
   listener removal protect deletion, but insertion/reordering needs stable
   object identity. Algebraic equality cannot distinguish two equal occurrences.
7. **Late document/calculation writes (risk; no common guard).**
   simplify_request.revision and expansion timestamps distinguish requests but
   are not checked against the current document/value revision before replacing
   blocks. save callbacks wait for saved_revision >= requested counters, not
   the state that the request was based on. Whole-block-list updates and
   captured callback state can replace newer source or rows.
8. **Browser-local state versus Python notifications (observed).**
   renderCreator captures template/nodes/connections at mount and does not
   subscribe to general graph/orders/positions replacement. It listens to mode,
   colors, signs, and selected controls. Keeping a canvas mounted protects
   gestures, but can preserve an older local state after a backend update.
   renderBlocks' active-editor early return is also a focus protection, not a
   semantic version check.
9. **Partial invalid reconnection (observed).** startAttachedConnection removes
   the attached connection while dragging. pointercancel restores it; an
   unsuccessful pointerup can leave it disconnected and does not push a normal
   undo entry. This does not satisfy “invalid reconnection leaves state unchanged.”
10. **Placement lost during rebuild (observed).** Canvas mode rebuilding passes
    positions but not the complete route/configuration state. Expansions build
    new widgets and default layouts, optionally optimize them, and chiefly
    inherit colors. ProjectorSum canonical collection can choose another
    representative. There is no survivor-ID map for preserving manual placement.
11. **Disposable display cache (existing protection).** Save deletes graph.display;
    configuration replay rebuilds it from Projector. Compiled-display validation
    has fallback behavior. Keep these safeguards; a display cache must never
    become authoritative connectivity.
12. **Loaded definition precedence (existing protection).** The whiteboard
    rebuilds stores from visible definitions, prefers the latest generated
    definition, keeps a persisted definition until an explicit editor saves,
    and gives pair definitions precedence over stale scalar names. Preserve
    these semantics while replacing the duplicated state paths.

## Existing coefficient and antisymmetric orientation convention

### Mathematical object and scalar domain

A Projector is a directed graph with immutable node values, ordered input/output
ports, explicit connections, fixed external boundary labels, and input/output
directions. NodePort.node is a sequence index. Internal labels are dummy names
under canonical graph equivalence; external labels are fixed. Drawing positions,
routes, and editor IDs are not part of algebraic equality or hashing.

Products act right-to-left: P * Q applies Q then P. Inputs are on the right,
outputs on the left; connections join a source output to a target input.
Normalized S and A nodes expand with 1/k!; A additionally uses permutation
parity. A closed loop contributes N, or the supplied exact dimension; collapse
can return dimension-polynomial coefficients. Reordering ports must preserve
this normalization and surrounding product coefficients.

Projector.coefficient and ordinary ProjectorSum coefficients are Fraction.
require_coefficient accepts integers, fractions, and finite floats interpreted
by decimal spelling; the editor should transmit exact numerator/denominator
strings. SymbolicCoefficient and calculation.SymbolicProjectorSum supply the
whiteboard's supported commuting symbolic prefactors. Symbolic coefficients
cannot be passed directly as Projector.coefficient. projector_codec supports
Projector, rational ProjectorSum, and symbolic scalar values, but not a complete
SymbolicProjectorSum; any editor persistence adapter must compose these existing
domains rather than pretending the rational codec already handles symbolic
projector sums.

### Three different coefficients

Let c be Projector.coefficient and let p(O) be the product, over every A node, of
the input and output order parities relative to that node's node.labels.

    canonical_coefficient = c * p(O)
    canonical_value_coefficient = c * p(O) * g(topology)

g is the BLISS canonical internal-orientation sign, including permutation
absorption; an odd automorphism gives g = 0. Equality/hashing use canonical
topology, canonical_value_coefficient, and directions. collapse uses
canonical_coefficient and contracts the actual wiring. Do not apply g again to
the displayed prefactor. node.labels retains supplied iterable order (sets are
sorted), so it is not always synonymous with sorted support.

ProjectorSum collects using canonical_value_coefficient. Its public items/terms
move a representative's raw coefficient into the outer rational factor and
expose a raw-coefficient-one projector. This collection is separate from the
ordered editable list of occurrences.

### Existing display convention and the discrepancy to resolve later

layout.widget_graph emits a crossing-reduced order plus port_swap_sign relative
to sorted support, and computes:

    graph.coefficient = graph.base_coefficient = c * port_swap_sign

Even explicit orders enter this display-sign calculation.
_projector_from_state reconstructs:

    reconstructed raw c =
        graph.coefficient * graph.port_swap_sign * relative-edit-sign

It then gives explicit orders to Projector, whose constructor derives canonical
coefficients. effective_coefficient is saved presentation metadata, not an
independent authoritative scalar input to this reconstruction.

This restores algebra on ordinary replay, but hides an already compensated
explicit orientation in the visible scalar. Verified with one A(1,2), starting
at c = -2/3:

| Relative reorder | Required new raw c | canonical_coefficient | Equal/collapse equal to original | Fresh widget_graph visible coefficient |
| --- | --- | --- | --- | --- |
| Odd input only | +2/3 | -2/3 | Both true | -2/3 |
| Odd output only | +2/3 | -2/3 | Both true | -2/3 |
| Odd input and odd output | -2/3 | -2/3 | Both true | -2/3 |

Reconstruction from each generated graph still equals its input Projector.
Thus the algebra supports the brief, while fresh rendering of explicit orders
can obscure the required visible flip. append_row and _result_source explicitly
use this presentation sign to hide compensation. This is existing behavior to
characterize, not an algebra change made here.

### Required relative-reorder contract: one compensation

For a redraw command from old orders O to new orders O', with fixed connectivity:

    s = parity(relative input permutation) * parity(relative output permutation)
    c' = s * c
    p(O') = s * p(O)
    c' * p(O') = c * p(O)

Multiply s across affected A nodes. Relative parity must be measured against the
previous orders, not counted afresh against a renderer's opening snapshot.
Moving a port across two slots is even. A second identical swap restores the
original order and scalar. Symmetriser reorders have s = +1.

| Input change | Output change | Combined s | Displayed complete prefactor |
| --- | --- | --- | --- |
| Odd | Even/unchanged | -1 | Flips once |
| Even/unchanged | Odd | -1 | Flips once |
| Odd | Odd | +1 | Unchanged |
| Even | Even | +1 | Unchanged |

The shared command must return a Projector carrying c' and the new orders.
Projector computes canonical coefficients as derived meaning; that is not a
second editing compensation. Frontends render the returned scalar without
multiplying another parity or rewriting an additional mathematical minus.
An outer prefactor a remains unchanged: display a*c' once. This works for
negative/rational a and supported symbolic a without comparing symbolic values
to zero to choose a numerical sign.

For sums, target one stable term occurrence. Preserve its outer factor and all
other terms; do not collect/reorder the editable occurrence list just because
the aggregate ProjectorSum compares equal.

Explicit ApplyPermutation is a different mathematical command: compose an
actual permutation via the current algebra without automatic redraw
compensation. Boundary reassignment and strand reconnection are connectivity
commands. Pure crossings in a drawn path have no parity meaning; movement and
pure rerouting keep the exact Projector unchanged. A horizontal creator gesture
that bypasses/splices a node must be explicitly classified as structural.

Existing permute_node_ports is the best reference implementation for a one-port
redraw move: it reconstructs orders and derives the exact compensating scalar
from canonical_coefficient ratios, checks equality, and performs no factorial
expansion. Reuse it initially. A validated combined input/output command can
compose those local moves into one transition/history entry. Handling of empty,
zero, one-port, invalid, and non-S/A targets needs command-level tests.

## Smallest proposed shared editor model and command boundary

This is a proposed internal design, not a newly fixed public API.

### State

Add a narrow typed Python module, proposed src/birdtracks/projectors/editor.py:

- A frozen editor state containing a monotonic revision, an ordered tuple of
  editor terms, presentation, and selection.
- Each term has a stable term ID, its immutable ordered Projector, and one
  optional exact outer factor for supported symbolic/term scaling. Rational
  diagram scalars stay in Projector.coefficient; do not maintain another
  mutable effective_coefficient/sign authority.
- Presentation holds stable node IDs mapped to algebraic sequence indices,
  stable strand IDs mapped to exact endpoints/boundary attachments, positions,
  route points/levels, colors, and view metadata. Existing display-graph
  provenance can help translate visible corridors through hidden permutations.
- Ordered ports remain in Projector.port_orders because current algebra gives
  them meaning. Presentation references those ports by editor identity; it
  must not carry a competing semantic order. IDs/coordinates remain absent
  from Projector equality, hashing, and its algebra codec.
- A session/controller owns current state and undo/redo stacks of immutable
  states. Undo/redo restores algebra, arrangement, and selection together but
  assigns a fresh monotonic revision, so old replies cannot become current.
  No-op commands do not add undo entries.

Use ordered terms to preserve duplicate equal occurrences, zero drafts, and
manual term ordering. Derive a collected ProjectorSum only when computing or
comparing algebraic results. A shared command runner is sufficient; no event
sourcing framework, solver rewrite, compiled backend, or required dependency is
needed.

At the document level, extend the existing blocks model with stable inline
object references, draft source, last successfully parsed source/value,
parse status, and source revision. Rendered and active states reference the
same editor session. Browser caret/selection ranges remain view data; model
selection/object identity survives a remount. Introduce this document adapter
when migrating whiteboard commits, not as a prerequisite for the first port
command.

### Commands and atomic transitions

Proposed commands are ReorderPorts, MoveNode, RerouteStrand, ReconnectStrand,
ApplyIdentity/ReplaceSubgraph, CommitSource, and explicit ApplyPermutation/Tidy.
Names and payload details remain internal until implementation and tests
establish the boundary.

A request carries session/object IDs, command ID, base revision, and typed
arguments. Python validates identities, port permutations, connectivity,
boundary compatibility, and exact coefficients, builds a complete candidate,
then commits one state plus one history entry. Failure returns a useful local
error and leaves state/history unchanged. The response contains the accepted
revision, render projection, and survivor map.

For delayed parsing/calculation, capture the relevant revision and named-value
dependencies; reject a result if those changed. Do not install it merely because
the block ID still exists or its graph is equal. Serialize commands per session;
preview dragging can remain transient in the browser, with one final command
per completed gesture. Every accepted publication contains algebra and
presentation together; synced individual traits become compatibility views.

Use existing Projector validation and permute_node_ports rather than implementing
another sign convention. MoveNode/RerouteStrand return the same algebraic object.
ReconnectStrand/ReplaceSubgraph rebuild a validated Projector through existing
algebra helpers. Expansion/identities return terms plus deterministic old-to-new
node/strand correspondence; unaffected IDs retain their metadata. Do not infer
identity by matching equal nodes or by canonical graph indices. Where existing
private rewrite helpers know the index remap, expose a narrow optional
provenance result/adapter without changing mathematical results.

Lay out introduced objects near their replaced neighbourhood; preserve routes
whose endpoints survive and repair only invalid segments. Existing expansion
detangling can alter unrelated port arrangements, so its editor adapter must
preserve survivor orders with exact compensation or use a narrowly equivalent
path that does not impose that display rewrite. This decision requires focused
equivalence tests at the expansion stage. Default layout is used for initial
placement and new objects; whole-diagram layout occurs only for explicit Tidy.
No tallest-S/top or tallest-A/bottom policy is added.

### One port command, gesture to render

1. The existing port handle previews a new ordered side; on release it submits
   term/node IDs, old revision, and desired input/output orders.
2. Python resolves editor IDs to Projector indices, validates the permutation,
   calls the existing compensated port operation, and builds the next state
   without changing connections, positions, unaffected routes, or outer factors.
3. The session records one before/after pair and publishes the new revision and
   scalar/orders atomically.
4. Canvas or whiteboard renders that projection. Whiteboard's visible source
   prefactor is a projection of the same scalar; JavaScript calculates no sign.
5. Saving encodes the accepted Projector plus presentation IDs and metadata.
   Loading decodes that value directly and never executes ReorderPorts again.

For parsed source, consume a displayed prefactor once. A marker must expose a
coefficient-one *oriented* diagram to a parser scaling it by the displayed
prefactor, rather than expose the already scaled Projector and multiply again.
Construct that oriented unit without dividing by a possible zero coefficient.
Track whether source is a projection or an actual user draft; rendering a source
projection must not trigger another algebra commit. This is the crucial
whiteboard adapter boundary. Named references continue to resolve to their
defined algebraic values; changing a view of a reference must not mutate its
definition accidentally.

### Serialization and compatibility

Reuse projector_codec for immutable rational algebra, its symbolic scalar codec
for supported outer factors, ProjectorConfiguration for legacy snapshots, and
the existing atomic sidecar writers. Add an editor-state payload/version for
stable IDs, exact factor ownership, positions, and routes. The same payload
should serve standalone and embedded editors.

Import old canvas/whiteboard snapshots through the existing
_projector_from_state exactly once, retaining placement and legacy sign
metadata until conversion is complete. Never apply legacy port_swap_sign again
after decoding the new algebra payload. A loaded snapshot is a restore, not a
command. Recompute disposable display caches from accepted topology. Keep
legacy v1/v2 readers and current LaTeX output, including birdtracks.sty, while
the new payload is introduced.

## Tests to retain and acceptance gaps

Retain the following mathematical and behavior regressions. Tests that inspect
JavaScript function names or string fragments should eventually assert the
equivalent command/interaction behavior rather than require superseded parity
code to remain.

| Existing test files | Coverage to preserve |
| --- | --- |
| tests/unit/test_projectors.py | Explicit immutable port orders, compensated antisymmetric equality, invalid ports/boundaries, noncommutative composition/associativity. |
| tests/unit/test_projector_canonicalization.py and test_projector_collapse.py | Internal dummy-label orientation, canonical equality/hash, crossed wiring versus permutation absorption, exact saved-order collapse, loop factors. |
| tests/unit/test_projector_simplification.py and test_projector_identities.py | permute_node_ports/recursive expansion, exact expansion signs, surrounding coefficients, absorption, projector identities, zero cleanup. |
| tests/unit/test_projector_sums.py and test_symbolic_coefficients.py | Rational collection/display factors and supported symbolic scalar arithmetic. |
| tests/unit/test_projector_layout.py | Crossing-reduced initial display, no-op save, compensated reorder/reopen, complete configuration replay, cache rebuild, boundary permutations, color remap, canvas session load, local/global undo, topology/presentation separation. |
| tests/unit/test_projector_display_graph.py | Visible corridor provenance and hidden permutation topology. |
| tests/unit/test_whiteboard_backend.py and test_whiteboard_sidecar.py | Saved versus unmaterialized definitions, latest generated definitions, numeric parser factors, snapshot load, generated presentation persistence, expansion labels/colors, typed/legacy sidecars. |
| tests/unit/test_whiteboard_pair_calculation.py and test_whiteboard_latex.py | Pair/scalar precedence, parser grouping, mixed-operation rejection, exact export source, boundary permutations, styles, and TeX compilation. |
| tests/ui/test_whiteboard.py | Real A-port drag/source-sign checks; remount orientation; movement survives blur/lower-row edits; unchanged mounts; Enter snapshots; deleted-object pruning; calculation cancellation; result focus; invalid-source recovery; fraction/caret hit testing. |
| tests/ui/test_young_creator.py | Existing pair gesture, coefficient, insertion/deletion, and creator interaction behavior while embedding changes. |
| tests/conformance, tests/properties, tests/performance | Existing algebra/backend laws and performance contract; editor changes should not expand port edits factorially. |

Particularly useful named regressions to carry forward are
test_antisymmetric_order_and_compensating_sign_compare_canonically,
test_saved_antisymmetric_port_order_uses_canonical_coefficient,
test_internal_antisymmetriser_swap_is_equal_and_reopens_exactly,
test_configurator_no_op_save_preserves_displayed_port_state,
test_saved_configuration_rebuilds_stale_display_routing,
test_generated_term_presentation_survives_whiteboard_reopen,
test_dragging_real_antisymmetriser_port_updates_whiteboard_sign, and
test_result_rebuild_keeps_keyboard_focus. Preserve their semantic guarantees;
document intentional updates to visible-coefficient expectations when replacing
the legacy presentation-sign convention.

The missing or incomplete acceptance coverage is:

- A shared state/command suite (proposed tests/unit/test_projector_editor.py):
  odd input, odd output, simultaneous odd/odd, even moves, two swaps, equivalent
  sequences, multiple A nodes, multi-node products, sums, negative/rational
  factors, supported symbolic factors, zero and one-port cases. Compare both
  canonical value and small exact collapse; assert the *visible* factor too.
- Semantic distinction between a redraw reorder and ApplyPermutation or
  connectivity changes; raw line crossings alone never change signs.
- Movement/pure rerouting preserving the identical algebraic value; structural
  creator movement classified separately. All unaffected IDs/positions/routes
  survive expansion and replacement, including duplicate equal nodes.
- One gesture equals one undo action; redo restores both value and drawing;
  undo followed by a late response cannot restore the undone state.
- Save/load and repeated no-op save/reload preserve visible prefactors, ordered
  ports, placement, routes, selection as applicable, and stable IDs without
  repeating compensation. Import fixtures with an already odd explicit order
  and nontrivial legacy port_swap_sign.
- Failure atomicity for invalid/repeated/missing ports, incompatible boundaries,
  failed parse, and invalid reconnection, including pointerup and pointercancel.
- End-to-end whiteboard reorder -> source -> save -> Python parse -> calculation
  -> reload with one scalar owner. Existing source-sign browser checks alone
  do not establish complete-expression equivalence.
- Replay the same command sequence through standalone projector, full canvas,
  explicit whiteboard object, and generated backend object, with equal algebra
  and consistent presentation. Include rational and symbolic source factors.
- Incomplete source retains the draft and the last valid rendering/value; a
  corrected draft commits once. Delayed parsing, saves, calculation, and child
  mounts cannot overwrite newer source, values, or object identities.
- Browser focus/caret/selection and controls survive activation, blur, remount,
  and rapid typing. Reuse existing hit-testing/focus tests and add revision
  races, symbolic prefactors, surrounding typography/background, and controls
  only visible while the object is active.

Use real shipped browser modules for interaction assertions and at least one
roundtrip through the Python command/save/parser boundary. Current browser
fixtures use an in-memory widget model/host, so transport and algebra atomicity
need additional integration coverage. Keep collapse small and exact; larger
interaction cases stay symbolic.

## Baseline verification

Date: 2026-10-07. Venv: .venv/bin/python, Python 3.14.7, pytest 8.4.2.
pyproject.toml configures pytest (strict markers/config, tests directory).
It does not configure a lint or type-check command; no ruff/mypy executable
module is installed. No new dependency or generated repository fixture was added.

Initial command:

    .venv/bin/python -m pytest

This sandboxed attempt was incomplete (exit 143). It encountered two
multiprocessing conformance failures from a forbidden AF_UNIX forkserver socket;
a focused -x rerun confirmed PermissionError: Operation not permitted.
Chromium launch also failed inside the sandbox and UI fixtures skipped.
These are environment restrictions, not the authoritative product baseline.

Complete rerun with sandbox restrictions lifted:

    .venv/bin/python -m pytest -q -r fEs

Result: **882 passed, 1 failed, 8 skipped in 204.37 seconds; 891 collected.**
Full temporary log: /tmp/birdtracks-editor-layer-baseline.log (not a committed
artifact).

Actual assertion failure:

- tests/unit/test_mismatched_young_layers_stress.py::
  test_stress_whiteboard_contains_every_exact_case, line 325.
  The number of embedded projectors matches CASES, but at least one loaded
  editor.projector does not equal its expected case.projector. This uses the
  pre-existing untracked examples/whiteboard/mismatched-young-layers.whiteboard
  and untracked stress test. It is not a missing dependency. Root cause was
  not investigated or fixed in this inspection-only stage.

Missing optional capabilities, separately:

- Three conformance tests skipped: optional Cython backend not built.
  Cython itself is also absent.
- Five detangle-training tests skipped: torch is not installed.
- anywidget, Playwright/Chromium, igraph, and pair_multiplication are available.
  The full rerun had no browser-test skips.

Read-only exact probes verified compensated input/output/both-side reorders
with a negative rational coefficient, canonical equality, collapse equality,
and widget reconstruction, and verified the double-scaling boundary
counterexample documented above.

Visual inspection used real Python widget state and the shipped JavaScript/CSS
in Chromium with the existing fixture model/host. Inspected the standalone term
renderer and correctly embedded whiteboard in rendered and active editing
states. The inline diagram shares the document surface and suppresses its
separate Save button; standalone rendering has separate canvas controls.
Temporary screenshots:
 /tmp/birdtracks-editor-layer-canvas.png,
 /tmp/birdtracks-editor-layer-whiteboard.png,
 /tmp/birdtracks-editor-layer-whiteboard-active.png.
This establishes the current rendering appearance, not a live notebook,
desktop-host, asynchronous transport, or seamless-editing acceptance claim.
Those host checks remain for the implementation stages.

Caution for future baseline runs: the stress test opens its repository example
through whiteboard(path), whose constructor persists loaded documents. Prefer
a temporary copy for diagnostic reruns of that test; do not regenerate the
author's fixture to hide the failure.

## Proposed implementation sequence and files

Each stage is a reviewable behavior slice. Do not remove legacy logic until its
replacement passes the exact and browser acceptance checks.

1. **Shared port reorder in one interface, with undo and persistence.**
   Start with the single projector widget used by the standalone canvas.
   Add editor.py (typed state, ID mapping, ReorderPorts, revision checks,
   history), and proposed editor_codec.py only for the narrow persistence
   adapter. Reuse simplification.py: permute_node_ports and existing Projector
   validation; keep projector.py/canonical.py mathematics unchanged.
   Wire widget.py and static/projector-widget.js port handles to the Python
   command; project its returned scalar without another parity factor.
   Adapt layout.py's editor projection and configuration.py/canvas_session.py
   restore boundaries. Add test_projector_editor.py and focused additions to
   test_projector_layout.py/test_whiteboard_sidecar.py plus actual port-drag
   tests. Complete odd/even/sign, undo/redo, stale rejection, and save/reopen
   before moving on.
2. **Connect full canvas and whiteboard to that same command.**
   Migrate widget.py's term-factor/history integration and
   whiteboard/widget.py's explicit/generated child ownership. Adapt
   whiteboard/calculation.py parsing and _result_source to consume/project the
   scalar once; use whiteboard/projector_codec.py for algebra payloads.
   Replace static/whiteboard-widget.js orientation-driven source rewrites
   with state projections. Keep sidecar.py migration support. Add cross-surface
   sequence tests and reorder/save/parse/calculate/reload browser integration,
   including symbolic and rational prefactors.
3. **Migrate movement, routing, reconnection, expansion, and replacement.**
   Extend editor.py commands/provenance and their codec; replace corresponding
   mutation paths in static/projector-widget.js and widget.py. Use
   display_graph.py/layout.py for derived rendering and local initial layout.
   Add narrow provenance adapters at known remap points in
   simplification.py/identities.py, preserving existing algebra results.
   Update whiteboard/widget.py expansion integration and metadata retention.
   Add invalid-reconnection atomicity, movement invariance, survivor placement,
   unaffected route, duplicate-object, and one-action undo/redo tests.
4. **Complete inline whiteboard draft/render/edit transitions.**
   Extend whiteboard/model.py or add a small document-editor adapter beside it;
   keep existing evaluation environment/backend protocols.
   Integrate CommitSource and revision/dependency checks in
   whiteboard/widget.py/calculation.py (and the pair adapter where necessary).
   Reuse static/whiteboard-widget.js source-range/caret and mount safeguards,
   adding last-valid rendering/value and contextual active controls.
   Adjust whiteboard-widget.css/projector-widget.css only for the requested
   typography/background/control behavior. Preserve whiteboard/latex.py and
   birdtracks.sty output, with export tests and actual canvas/whiteboard visual
   inspection. Add rapid-typing/delayed-result/focus/blur acceptance tests.
5. **Remove superseded paths after conformance is established.**
   Remove unreachable renderConfigured and frontend parity/sign ownership,
   old snapshot-as-live-state and competing history paths in widget.py and
   both JavaScript modules. Keep legacy readers at an explicit compatibility
   boundary until migration tests cover them. Rewrite implementation-string
   assertions to semantic state/browser tests. Update docs/editor-layer-plan.md,
   docs/architecture.md, whiteboard/README.md, and add a short editor-state ADR
   under docs/adr describing scalar ownership, canonical/drawing separation,
   identity mapping, and persistence. Run the configured suite, report the
   baseline failure separately, and list any remaining compatibility paths.
