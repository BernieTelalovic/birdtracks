# Birdtracks Whiteboard

Birdtracks Whiteboard is a desktop app for writing, drawing, evaluating,
saving, and reopening birdtrack calculations. A whiteboard is meant to feel
like typesetting in $\LaTeX$, with intuitive birdtrack drawing and interactive
kernel commands such as evaluating an equation line with shift+enter.

The app uses exact algebra internally. You can evaluate expressions step by
step without setting up Python or writing code.

## Install and run

The installers include a private Python runtime and every dependency. They do
not require an existing Python installation, Git, or a compiler, and they do
not modify the system Python.

### Windows

1. Download
   [`install-birdtracks.cmd`](https://github.com/BernieTelalovic/birdtracks/releases/latest/download/install-birdtracks.cmd).
2. Double-click the downloaded file and wait for installation to finish.
3. Open **Birdtracks Whiteboard** from the Start menu.

The installer associates `.whiteboard` files with the app, so saved boards can
also be opened by double-clicking them. Windows may display a SmartScreen
warning until signed releases are available. Choose **More info**, confirm the
file came from this repository's official Releases page, and choose **Run
anyway**.

### Linux

Download
[`install-birdtracks.sh`](https://github.com/BernieTelalovic/birdtracks/releases/latest/download/install-birdtracks.sh),
then run:

```console
chmod +x install-birdtracks.sh
./install-birdtracks.sh
```

Open **Birdtracks Whiteboard** from the application menu. The installer also
registers `.whiteboard` files with the desktop, so they can be opened from the
file manager.

An internet connection is required during installation but not for ordinary
use. Running a newer release's installer upgrades the managed installation.

## Start a whiteboard

Launch **Birdtracks Whiteboard** without a file to create an untitled board.
To open a board from a terminal, pass its path:

```console
birdtracks-whiteboard my-notes.whiteboard
```

Inside the app:

- Type ordinary LaTeX-style mathematics directly on a line.
- Type `\birdtracks` to insert an interactive projector.
- Type `\pair` to insert an interactive Young-diagram pair.
- Press `Enter` to create a new line.
- Press `Shift+Enter` to evaluate an expression exactly.
- Press `Shift+Backspace` to restore the source behind a generated result.
- Use **Save** to write the board to a `.whiteboard` file and **Load** to open
  another board.

The **Export to LaTeX** button remains visible but is disabled for the 0.2.0
release.

See the [Birdtracks Whiteboard user manual](src/birdtracks/projectors/whiteboard/README.md)
for every source command, keyboard shortcut, toolbar action, projector
interaction, and Young-diagram interaction.

## Whiteboard expressions

Use `A := expression` or `A \def expression` to give an expression a name.
Later lines can use that name. Start a line with `&` to continue the preceding
logical line.

Projector expressions support ordered products, grouped expressions, exact
coefficients, and traces such as `\tr A` or `\tr(A + B)`. Pair expressions use
`\oplus` for direct sums and `\otimes` for ordered tensor products. For example,
`2_4\pair` gives an embedded pair coefficient 2 with `N₀ = 4`.

Evaluating a projector expression applies automatic identities and exposes
interactive result terms. Operators can then be expanded manually to build a
calculation line by line. Evaluating a pair expression reveals its automatic
representation calculation steps.

## Development installation

This is optional. Most whiteboard users should use the Windows or Linux
installer above. From a repository checkout, developers can run:

```console
python -m pip install -e '.[app]'
birdtracks-whiteboard
```

## Advanced computation

The Python API and Birdtracks Lab are intended for larger calculations,
automation, notebooks, and direct access to exact algebraic objects. They are
secondary to the whiteboard app and are not needed for ordinary interactive
work.

The standard installer also provides **Birdtracks Lab**. Open it from the
desktop or application menu, create a Python notebook, and import Birdtracks:

```python
import birdtracks as bt

canvas = bt.create(session="my-equation")
canvas
```

Install only the jupyter notebook support in an existing environment with:

```console
python -m pip install -e '.[notebook]'
```

Install the complete coding environment and launch JupyterLab with:

```console
python -m pip install -e '.[coding]'
birdtracks-lab
```

The Python API exposes exact projector products, canonicalization, collapse,
and symbolic traces:

```python
collapsed = expression.collapse()
trace = collapsed.trace()
product = expression * expression
```

Saved calculator sessions use versioned `.canvas.json` sidecars. Reload the
final exact expression with `bt.load("my-equation")`, or reopen its complete
interactive history with `bt.create(session="my-equation")`.

Architecture and mathematical conventions are documented in
[`docs/`](docs/), including the [notation](docs/notation.md),
[calculator architecture](docs/calculator-app.md), and
[Young-diagram integration](docs/pair-multiplication.md).

## License

Birdtracks is source-available under the
[PolyForm Noncommercial License 1.0.0](LICENSE). It may be used, modified, and
shared for noncommercial purposes, including use by educational institutions
and public research organizations. Commercial use is not permitted.
