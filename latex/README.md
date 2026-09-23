# `birdtracks.sty`

This is a detached LaTeX presentation layer. It does not read whiteboard
files or depend on the Python package; it supplies TikZ primitives used by the
whiteboard exporter.

Copy `birdtracks.sty` beside a document, or install it in the document's TeX
search path, and load it with:

```tex
\usepackage[
  cell width=1.6em,
  cell height=1.6em,
  operator width=2.2em,
  operator line separation=1.2em,
  operator top margin=1.5,
  operator bottom margin=1.5
]{birdtracks}
```

The S/A top and bottom margins are dimensionless numbers measured in units of
the configured `operator line separation`. For `n` connected lines, the
operator height is therefore

```
(operator top margin + n - 1 + operator bottom margin)
    * operator line separation
```

## Whiteboard export

The live Python whiteboard exposes the detached exporter without requiring a
TeX installation:

```python
document.to_latex()                 # fragment
document.to_latex(include_preamble=True)  # standalone .tex source
```

The same function is available for serialized state as
`birdtracks.whiteboard_latex(state)`.  Copy `birdtracks.sty` beside the
generated source, or add `latex/` to the TeX search path.

## Young-diagram pairs

`\btpair` takes ordinary matrix material. `&` separates columns and `\\`
separates rows. Cells are centred horizontally and vertically, and can be
coloured independently:

```tex
$\btpair{
  \btcell[fill=yellow!20,draw=red]{1} & \btdottedcell[fill=blue!10]{2} \\
  \btcustomcell[double,draw=purple]{3} & \btdivcell[fill=green!10]{4}{5}
}$
```

The available cell commands are:

- `\btcell[<TikZ options>]{text}` for a solid border;
- `\btdottedcell[<TikZ options>]{text}` for a dotted border;
- `\btcustomcell[<TikZ options>]{text}` for a caller-defined border;
- `\btdivcell[<TikZ options>]{left text}{right text}` for a box divided by
  a southwest-to-northeast diagonal.

The optional settings are TikZ settings, so `fill=...`, `draw=...`,
`line width=...`, `dashed`, `double`, and related styles can be selected per
cell. The pair-level options `cell separation=...` and
`pair row separation=...` can be supplied to `\btpair`.

These commands are math-mode primitives and work the same way in inline
material such as \(\btpair{\btcell{a}}\) and in display math or an equation
environment.

## Birdtrack projectors

Use one `\btin` and one `\btout` command for every connected line. Their
optional TikZ settings belong only to that line:

```tex
\[
\begin{btSA}[A][operator fill=gray!10]
  \btin[draw=red, line width=1pt]
  \btin[draw=blue, dashed]
  \btin[draw=black]
  \btout[draw=red, line width=1pt]
  \btout[draw=blue, dashed]
  \btout[draw=black]
\end{btSA}
\]
```

`btprojector` is the general spelling; set `operator=S` or `operator=A` in
its options. Input and output line counts must match, and all S/A boxes use
the global `operator width`. Global projector geometry can be set at package
load time or later with `\btset{...}`.

Projectors are also valid inline, for example
\(\begin{btSA}[S]\btin\btout\end{btSA}\).

## General boxes

`\btbox` accepts arbitrary LaTeX content and is independently configurable:

```tex
\[
  \btbox[bt/box width=4em,bt/box height=3em,fill=gray!10]{
    \btpair{\btcell{a} & \btcell{b}}
  }
\]
```

The package defaults are `box width` and `box height`; the per-box TikZ keys
`bt/box width=...` and `bt/box height=...` override those defaults.
