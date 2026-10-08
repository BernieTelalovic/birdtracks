# In-place whiteboard editor

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
