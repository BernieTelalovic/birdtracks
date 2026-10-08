# `birdtracks.sty`

`birdtracks.sty` draws birdtrack projectors and Young diagram pairs with TikZ.
Copy it beside your document, or install it in your TeX search path, then load
it with:

```tex
\usepackage{birdtracks}
```

The complete example document is
[`birdtracks-example.tex`](birdtracks-example.tex), with a compiled copy in
[`birdtracks-example.pdf`](birdtracks-example.pdf). It includes layered
projectors, traced projectors, Young diagram pairs, and tables of global and
local settings.

## Layered projectors

Use the `projector` environment to describe a diagram from top to bottom.
Each `\layer` contains commands for its lines; every layer must describe the
same positive number of lines. `\symmetriser{n}` and
`\antisymmetriser{n}` draw operators across `n` lines, while
`\freelines{n}` leaves lines unobstructed. `\operator{n}{...}` draws a
general operator with content of your choice.

Use `\permute[styles]{sources}{targets}` to connect line positions between
layers. The source and target lists must have the same number of entries.
`\startnodes` and `\endnodes` add short boundary lines at the ends of the
diagram. The example document shows per-line arrows and TikZ styling on these
commands.

Operator height is based on the number of lines and the configured line
spacing. The top and bottom margins are measured in line spacings. Operator
width is a minimum; an operator grows to fit wider content.

## Traced projectors

In math mode, `\tr A` renders as `\mathrm{tr} A`, including in whiteboard
exports.

`tracedprojector` places a top and bottom projector together and joins their
lines with curved connectors. Use `\topprojector` and `\bottomprojector` to
define the two diagrams, and `\leftconnect` and `\rightconnect` to define
their connections. Connector permutations map bottom line positions to top
line positions. Both projectors must have the same positive number of lines.

The example document shows how to set trace gap, reach, turn, and lane spacing
for an individual traced projector. Its connector paths also accept per-line
arrow and TikZ styles.

## Young diagram pairs

Use `ydpair` with `\covar` and `\convar` to draw covariant and contravariant
diagrams. Within either diagram, `&` separates boxes and `\\` separates rows.
Each box can have TikZ node options followed by its content; the example uses
fills, dashed borders, and `\splitbox` for a diagonally divided box.

Use `\hpad{n}` to set the gap between the diagrams in box-size units; `n` may
be fractional. The pair is centred on TeX's math axis.

## Global and local settings

Set document-wide defaults with `\birdtracksetup{...}`. For example, the
example document sets the default box size, operator width, line spacing,
boundary length, and arrow type in its preamble.

Environment options override settings for one diagram. The `projector` and
`ydpair` environments accept the local options listed in the example
document's local-settings table. A `tracedprojector` also accepts the global
settings as local overrides. Per-box and per-line TikZ styles can be set on
individual entries and commands.

The example document's global and local settings tables list defaults,
aliases, and descriptions.
