# Birdtracks Calculator

Birdtracks provides exact algebraic objects and an interactive canvas for
constructing, simplifying, tracing, saving, and reloading sums of birdtrack
projection operators.

The calculator can run inside a Jupyter notebook or as a local browser app. Its
coefficients use exact integer and rational arithmetic.

## Download the standalone app

No Python installation is required. Download the file for your computer from
the project's GitHub Releases page:

- **Windows:** download `Birdtracks.exe` and double-click it.
- **Linux:** download `Birdtracks`, make it executable, and open it:

  ```console
  chmod +x Birdtracks
  ./Birdtracks
  ```

The app starts a private server on your own computer and opens the calculator
in the default browser. Closing the terminal or stopping the Birdtracks process
shuts it down. Saved expressions are placed in an `expressions` folder beside
the directory from which Birdtracks was launched.

Windows may show a SmartScreen warning until signed release binaries are
available. Choose **More info**, verify that the file came from this project's
official Releases page, and then choose **Run anyway**.

## Installation

This section is only for Python users and developers; users of the standalone
download can skip it.

Install the notebook support with:

```console
python -m pip install -e '.[notebook]'
```

To launch the calculator as a browser app from the command line, install the
application extras instead:

```console
python -m pip install -e '.[app]'
```

## Launching the calculator

In a notebook:

```python
import birdtracks as bt

canvas = bt.create(session="my-equation")
canvas
```

From a terminal, run:

```console
python -c "import birdtracks as bt; bt.create()"
```

This starts the complete calculator in your default browser. Press **Save** to
choose the expression filename. Server output is suppressed by default; use
`bt.create(debug=True)` when you want rendering errors and tracebacks to be
shown.

## Create mode

Create mode builds a sum of projectors:

- Add a line with either **+** control below the bottom line.
- Add a symmetriser by selecting **S**, or by double-clicking between two
  lines.
- Add an antisymmetriser by selecting **A**, or by double-clicking an existing
  symmetriser.
- Drag lines and operators to rearrange the diagram.
- Right-click a line or operator to delete it.
- Right-click a projector prefactor to delete that complete projector term.
- Add another projector with the **+** or **−** toolbar control, or the
  corresponding keyboard key.
- Hold Ctrl to reveal a projector's multiply control. Enter an exact fraction,
  use **/** to switch between numerator and denominator, and press Enter or
  click outside the editor to apply it.

## Evaluate mode

Evaluate mode manipulates the constructed expression while preserving exact
algebraic values:

- Double-click an S or A operator to expand it.
- Hover over an operator's top or bottom line and select the exposed tear icon
  to apply its recursive expansion identity.
- Drag operators and free lines vertically through equivalent arrangements.
  Reordering an antisymmetriser's ports updates the projector sign.
- Toggle **tr** to enclose every equation line in trace brackets and display
  the resulting polynomial in the symbolic dimension `N`.
- Hold Ctrl to reveal the undo control for an individual projector.
- Use the upper-right undo control to remove the latest equation line.

All terms in a traced sum should represent operators on the same domain size.
For example, a projector on three lines and one on four lines are otherwise
traced independently and their resulting polynomials are simply added.

## Saving and loading expressions

A bare session name is saved relative to the directory where Python was
started. Birdtracks creates an `expressions` subdirectory and appends
`.canvas.json` automatically:

```text
expressions/my-equation.canvas.json
```

An explicit path may point anywhere instead. Saved JSON contains the canvas
state and equation history in a readable, versioned format.

Reload the exact expression represented by the final saved equation line with:

```python
import birdtracks as bt

expression = bt.load("my-equation")
```

Reopen the complete saved canvas with:

```python
canvas = bt.create(session="my-equation")
```

## Why simplify manually?

Manual expansion and simplification can substantially reduce the intermediate
work needed for traces and projector products. It is also useful for checking
identities visually and building intuition before handing an expression to an
automatic solver:

```python
collapsed = expression.collapse()
trace = collapsed.trace()
product = expression * expression
```

The longer-term goal is automatic simplification of birdtrack expressions into
permutation sums for tasks such as projector normalization and orthogonality
checks. Bug reports, especially examples producing incorrect algebraic
results, are very welcome.

## License

Birdtracks is source-available under the
[PolyForm Noncommercial License 1.0.0](LICENSE). It may be used, modified, and
shared for noncommercial purposes, including use by educational institutions
and public research organizations. Commercial use is not permitted.
