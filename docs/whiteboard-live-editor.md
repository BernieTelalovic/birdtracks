# In-place whiteboard editor

Status: complete; released in `v0.2.2`. Retain this walkthrough for regression
verification; new behavior must follow [the maintenance guide](editor-layer-maintenance.md).

The shared Python document owns committed notation and embedded values.
Typing renders immediately, but incomplete source remains a draft with the last
valid value retained internally. There is no separate preview below the draft.
Evaluation and simplification still require Shift-Enter.

## Launch

Restart the notebook kernel/app to load the changed widget code, then rerun the
whiteboard cell. For a disposable demo with text, a diagram, and a Young pair:

```sh
.venv/bin/python -m voila examples/live_whiteboard_editor.py --no-browser --port=8876 \
  --VoilaConfiguration.extension_language_mapping=.py=python \
  --VoilaConfiguration.language_kernel_mapping=python=python3
```

Open `http://localhost:8876/`. The demo uses a temporary file and does not modify
existing documents. Copy the displayed file before stopping its kernel if you
want to keep it. In an ordinary notebook, use the existing `whiteboard(path)` API.

## Walkthrough

1. Click the first expression and type `x+\bi`. The completion suffix appears
   in place; Tab completes `\birdtracks`. Also try `\pa`, `\de`, `\op`, and
   `\ot`. Operator completions retain their trailing space.
2. Type `a+b`, click on either side of `+`, and navigate with arrows, Home, and
   End. Click beyond the rendered expression: the caret reaches the source end,
   not a position calculated from invisible raw LaTeX. Move inside a fraction:
   its source becomes editable in the same line.
3. Type `\frac{12}{`. Only that draft appears, with a small parse indication.
   Move through it character-by-character, then complete `\frac{12}{34}`.
   Click elsewhere: the completed fraction renders and the indication clears.
4. Save an incomplete source and reload the whiteboard. The exact draft and its
   last-valid Python value survive. Completing the marker restores the same
   embedded editor, with its drawing/pair edits intact.
5. Click the diagram to reveal contextual controls; move an operator or edit
   ports using the established Create/Evaluate behavior. Click a different row:
   controls hide, but values and placement remain. Return and undo/redo the
   diagram edit using its existing history controls.
6. Click the Young pair; double-click a target box to add it. Ctrl-Enter opens
   its prefactor editor. Type a coefficient, then leave: the Python-validated
   value appears inline. Editing another row must not steal focus or reset a
   partially typed coefficient. Save/reload and check the boxes/coefficient.
7. Type quickly, immediately Save, or switch away and back. Older replies must
   not restore older text, values, caret positions, or presentation. Shift-Enter
   remains the explicit calculation action. Export a complete expression and
   check the existing LaTeX/birdtracks.sty workflow.

For the compact-command/menu regressions, also check:

- Scroll down, click the active tab's name, rename it, then Save without returning
  to the document top. Transparent source overlays must not intercept the menu,
  and menu clicks must not activate a text row underneath.
- Use `B\def\pair\oplus 2_3\pair`, add boxes to both pairs, then evaluate
  `B\otimes B`. Compact notation must use the pair backend after save/reload.
  Command spacing exists only in the Python parsing view, not in saved source.
  Adjacent prefactors and explicit `\times` still multiply once; rational and
  negative projector prefactors retain exact values. No algebra rule changed.
- Add and remove pair boxes repeatedly without clicking outside/back into the
  tool. Delete, Backspace, and right-click deletion retain term focus and active
  controls; Backspace must not remove the surrounding `\pair` source marker.
- After evaluating an already completed scalar line, scroll back to the middle
  and press Enter to insert a row. The caret and viewport stay at the insertion,
  including after delayed replies. An earlier automatic calculation-follow
  target cannot redirect this manual edit; the calculation itself is unchanged.
- Use `A \def \birdtracks \otimes \birdtracks`, give both diagrams the same
  direction with Ctrl-hover/click on their direction controls, and Shift-Enter.
  The generated tensor projector retains all boundary arrows. Repeat with the
  opposite direction, then save/reload. Direction-only Create changes are draft
  edits committed through Python; the shared render projection refreshes direction
  even when topology/routes are reused. While changing factors one at a time,
  the compound display keeps its last valid value until their directions agree.
  Explicit evaluation still rejects a tensor of mismatched directions.

## Verification

Focused tests are in `tests/unit/test_whiteboard_document.py` and
`tests/ui/test_whiteboard_live_document.py`; existing whiteboard, shared-command,
pair-prefactor, and LaTeX tests are retained. The modern interaction fixture uses
the shipped frontend connected to actual Python document/child widgets, not
only an independent frontend state shim.

The running Voilà demo was checked with Chromium for Tab completion, arrows and
End, single-line invalid source, valid recovery, pair coefficient commit, and
Save. Screenshots were inspected without adding generated fixtures.

Focused verification:

- Existing whiteboard frontend, modern document interactions, and document unit
  tests: **163 passed** (82.76 s).
- Final modern interactions/document guards plus legacy pair-prefactor checks:
  **50 passed** (12.94 s).
- Shared-command conformance and LaTeX output: **104 passed** (11.08 s).

- Complete configured suite (`.venv/bin/python -m pytest -q`): **1,252 passed,
  8 skipped** (650.11 s). Skips are three unbuilt optional Cython checks and five
  unavailable Torch checks; there are no failures.
- `git diff --check` and Python compilation checks passed. No separate lint or
  type-check suite is configured in `pyproject.toml`.

Follow-up focused checks for compact commands, prefactor preservation, source
ownership, and scrolled menu interactions: **143 passed** (12.19 s). Existing
frontend/pair checks before generalizing the adapter: **177 passed** (85.12 s).

Final follow-up frontend suite: **267 passed** (189.80 s). The running Voilà
interface was also checked for repeated pair additions/deletions, Backspace
source isolation, retained pair focus, Enter after a completed calculation,
and renaming while scrolled. Its screenshot was visually inspected. The user
whiteboard was inspected/evaluated in memory only and was not changed.

Final follow-up complete configured suite: **1,287 passed, 8 skipped**
(666.90 s), with no failures. The skips remain three unbuilt optional Cython
checks and five unavailable Torch checks. `git diff --check` also passed.

Direction-only creation/tensor follow-up: both Ctrl direction gestures,
Shift-Enter rendering, and save/reload passed in the Python-connected frontend;
the generated arrows were visually inspected. Focused unit/export/document
checks: **133 passed** (0.77 s), followed by the intermediate-direction regression.
The final complete suite passed with **1,292 passed, 8 skipped** (664.57 s).
Skips remain the same optional Cython/Torch checks. No tensor algebra, LaTeX
connector rule, or `birdtracks.sty` behavior changed.

LaTeX connector/color follow-up: packed Evaluate exports use Python's repaired
`display_free_levels` column routes and the same visible strand endpoint keys
as whiteboard paint. Every adjacent operator layer retains its actual connector,
including identity permutations; a single operator omits identity connectors.
Boundary nodes and operator faces inherit the color of their visible entering
or exiting strand, including paths through hidden permutation nodes. Export
does not change committed state or manual placement; `birdtracks.sty` is unchanged.
Per the requested focused verification, export and display-graph tests only:
**33 passed** (0.57 s), including compilation of colored exported connectors
with `pdflatex`. `git diff --check` passed; the full suite was not rerun.
