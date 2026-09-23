"""Exact representation evaluation with backend column-tableau display stages."""
from __future__ import annotations

from dataclasses import dataclass, replace
from html import escape
from itertools import product
from xml.etree import ElementTree as ET

from .representations import pair_backend
from .young_diagrams import PairExpression, PairTerm

ET.register_namespace('', 'http://www.w3.org/2000/svg')

@dataclass(frozen=True)
class Node:
    kind: str
    children: tuple[Node, ...] = ()
    term: PairTerm | None = None
    drawing: object = None


def atom(term, drawing=None):
    return Node('pair', term=term, drawing=drawing)


def join(kind, children):
    children = tuple(children)
    return children[0] if len(children) == 1 else Node(kind, children)


def parse(expression):
    """Tensor binds tighter than direct sum; brackets preserve explicit grouping."""
    tokens = expression.syntax or tuple(t for i in range(len(expression.terms))
                                        for t in (('sum', 'pair') if i else ('pair',)))
    position = term_index = 0

    def operand():
        nonlocal position, term_index
        if position >= len(tokens):
            raise ValueError('Expected a pair after the operator or opening bracket.')
        token = tokens[position]
        position += 1
        if token == 'pair':
            value = atom(expression.terms[term_index])
            term_index += 1
            return value
        if token == '(':
            value = sum_node()
            if position >= len(tokens) or tokens[position] != ')':
                raise ValueError('Missing closing bracket.')
            position += 1
            return value
        raise ValueError('Expected a pair or opening bracket.')

    def tensor():
        nonlocal position
        children = [operand()]
        while position < len(tokens) and tokens[position] == 'tensor':
            position += 1
            children.append(operand())
        return join('tensor', children)

    def sum_node():
        nonlocal position
        children = [tensor()]
        while position < len(tokens) and tokens[position] == 'sum':
            position += 1
            children.append(tensor())
        return join('sum', children)

    if not tokens:
        return Node('sum')
    root = sum_node()
    if position != len(tokens):
        raise ValueError('Expected ⊕ or ⊗ between operands; check the brackets.')
    return root


def expand(node):
    if node.kind == 'pair':
        return [(node.term,)]
    if node.kind == 'sum':
        return [monomial for child in node.children for monomial in expand(child)]
    return [tuple(term for group in groups for term in group)
            for groups in product(*(expand(child) for child in node.children))]


def collect(terms):
    # N0 is part of a summand, including when identical shapes occur at
    # different admissibility thresholds. All arithmetic stays in Python ints.
    values = {}
    for term in terms:
        key = (term.barred, term.unbarred, term.n0)
        values[key] = values.get(key, 0) + term.coefficient
    return tuple(PairTerm(b, u, coefficient, n0) for (b, u, n0), coefficient in values.items() if coefficient)


def _pair_operator_svg(operation, x, y, width, height):
    """Return the compact inline SVG used for pair algebra operators."""

    center = 14
    radius = 10
    offset = radius / 2**0.5
    if operation == "sum":
        lines = (
            f'<line x1="{center - radius}" y1="{center}" '
            f'x2="{center + radius}" y2="{center}"/>',
            f'<line x1="{center}" y1="{center - radius}" '
            f'x2="{center}" y2="{center + radius}"/>',
        )
        label = "direct sum"
    else:
        lines = (
            f'<line x1="{center - offset}" y1="{center - offset}" '
            f'x2="{center + offset}" y2="{center + offset}"/>',
            f'<line x1="{center - offset}" y1="{center + offset}" '
            f'x2="{center + offset}" y2="{center - offset}"/>',
        )
        label = "tensor product"
    return (
        f'<svg x="{x}" y="{y}" width="{width}" height="{height}" '
        'viewBox="0 0 28 28" class="birdtracks-pair-operator" '
        f'data-operation="{operation}" aria-label="{label}" '
        'fill="none" stroke="currentColor" stroke-width="1.1">'
        f'<circle cx="{center}" cy="{center}" r="{radius}"/>'
        f'{"".join(lines)}</svg>'
    )


def _prepare_pair_svg(svg):
    """Make a backend drawing safe to embed in a colourable equation."""
    # The standalone renderer has its own default colour.  Pair equations use
    # the surrounding line colour instead, without storing that presentation
    # choice in the next calculation line.
    svg.set('style', 'color:inherit')
    for element in svg.iter():
        if element.tag.rsplit('}', 1)[-1] == 'rect':
            # Opaque cells keep neighbouring colours from showing through,
            # while the inherited stroke and the labels remain visible.
            element.set('fill', 'white')
            element.set('stroke', 'currentColor')
            element.set('pointer-events', 'all')
    return svg


def render_tokens(items, *, leading_equals=False, leading_assignment=None):
    """Compose clean compact backend SVGs, prefactors, N0 and parentheses."""
    items = list(items)
    if leading_assignment is not None:
        items.insert(0, ("assignment", str(leading_assignment)))
        items.insert(1, "equals")
    elif leading_equals:
        items.insert(0, 'equals')
    prepared = []
    box = 26
    drawing_index = 0
    for item in items:
        if isinstance(item, tuple) and item[0] == "assignment":
            prepared.append((item, max(12, len(item[1]) * 12), 26))
            continue
        if isinstance(item, str):
            prepared.append((item, 22.4 if item in ('sum', 'tensor') else 20, 26))
            continue
        term, drawing = item
        svg = _prepare_pair_svg(ET.fromstring(drawing.to_svg(box_size=box)))
        for element in svg.iter():
            cell = element.get('data-cell')
            if cell is not None:
                element.set('data-cell', f'{drawing_index}:{cell}')
        drawing_index += 1
        width, height = float(svg.get('width')), float(svg.get('height'))
        # Crop the standalone drawing's horizontal export margin, retaining
        # one pixel for the outer stroke. The equation supplies its own gap.
        inset = box * 0.3 - 1
        width -= 2 * inset
        svg.set('viewBox', f'{inset} 0 {width} {height}')
        svg.set('width', str(width))
        svg.set('font-family', 'Georgia, serif')
        prefix = 4 + len(str(term.coefficient)) * 12 + len(str(term.n0)) * 8
        prepared.append(((term, svg, prefix), width + prefix, height))
    height = max([26] + [item[2] for item in prepared])
    x, content = 2, []
    for item, width, item_height in prepared:
        token = []
        token_kind = "pair"
        if isinstance(item, tuple) and item[0] == "assignment":
            token_kind = "assignment"
            token.append(
                f'<text x="{x + width / 2}" y="{height / 2}" '
                f'text-anchor="middle" dominant-baseline="central" '
                f'font-family="Georgia, serif" font-size="22">{escape(item[1])}</text>'
            )
        elif isinstance(item, str):
            token_kind = item
            if item in ('(', ')'):
                start, control = (16, 1) if item == '(' else (4, 19)
                token.append(f'<path d="M{x+start} 2 Q{x+control} {height/2} {x+start} {height-2}" fill="none" stroke="currentColor"/>')
            elif item in ('sum', 'tensor'):
                token.append(_pair_operator_svg(
                    item, x + (width - 22.4) / 2, (height - 22.4) / 2,
                    22.4, 22.4,
                ))
            elif item == 'equals':
                token.append(
                    f'<text x="{x+width/2}" y="{height/2}" '
                    f'text-anchor="middle" dominant-baseline="central" '
                    f'font-family="Georgia, serif" font-size="22">=</text>'
                )
            else:
                token.append(f'<text x="{x+width/2}" y="{height/2}" text-anchor="middle" dominant-baseline="central" font-size="24">{escape(item)}</text>')
        else:
            term, svg, prefix = item
            token.append(f'<text x="{x}" y="{height/2}" dominant-baseline="central" font-size="22">{term.coefficient}<tspan baseline-shift="sub" font-size="12">{term.n0}</tspan></text>')
            svg.set('x', str(x + prefix))
            svg.set('y', str((height - item_height) / 2))
            token.append(ET.tostring(svg, encoding='unicode'))
        content.append(
            f'<g data-pair-token="{token_kind}" data-token-x="{x}" '
            f'data-token-width="{width}">{"".join(token)}</g>'
        )
        x += width + 2
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{x}" height="{height}" viewBox="0 0 {x} {height}" data-natural-width="{x}" data-line-height="{height}" font-family="Georgia, serif" class="birdtracks-pair-evaluation-line" role="img" aria-label="Pair equation">{"".join(content)}</svg>'


def tokens(node, parent=None):
    if node.kind == 'pair':
        return [(node.term, node.drawing or pair_backend().draw_pair(node.term.native()))]
    if not node.children:
        return ['0']
    result = []
    for child in node.children:
        if result:
            result.append(node.kind)
        result.extend(tokens(child, node.kind))
    return ['(', *result, ')'] if parent == 'tensor' and node.kind == 'sum' else result


def remainder(term, processed):
    """The unprocessed columns of the right operand, with original labels."""
    from pair_multiplication.drawing import Drawing, Cell, Label
    width = term.barred[0] if term.barred else 0
    cells = []
    for cell in pair_backend().draw_pair(term.native()).cells:
        if cell.column < processed:
            continue
        barred = cell.row >= len(term.unbarred)
        label = width - cell.column if barred else cell.column - width + 1
        cells.append(Cell(cell.row, cell.column - processed, labels=(Label(str(label), barred),)))
    if not cells:
        return None
    top = min(cell.row for cell in cells)
    cells = tuple(replace(cell, row=cell.row-top) for cell in cells)
    return Drawing(cells, max(c.row for c in cells)+1, max(c.column for c in cells)+1)


def _pair_multiply_verbosely(backend, left, right):
    """Run the legacy column algorithm without creating nested process pools.

    ``pair_multiplication`` opens a new full-size process pool for every
    column.  Whiteboard evaluation already runs outside the browser event
    loop, and repeated pool startup can stall grouped direct-sum products.
    This is the same ordered candidate loop, executed in the current process.
    """

    tableaux = backend.tableau_classes
    pair_a = tableaux.PairTableau(
        partitions=right, column_sort=True, working_pair=False
    )
    pair_b = tableaux.PairTableau(
        partitions=left, column_sort=True, working_pair=False
    )
    len_barred_b = len(pair_b.br.array[0])
    minimum_n0 = max(
        len(right[0]) + len(right[1]),
        len(left[0]) + len(left[1]),
    )
    candidates = tableaux.CandidateList(
        partition_pair=[left, right], min_n0=minimum_n0
    )
    stages = []

    barred_columns = tableaux.np.array(
        list(set(-pair_a.br.imag.astype(int).flatten()))
    )
    barred_columns = tableaux.np.flip(barred_columns[barred_columns > 0])
    for column in barred_columns:
        box_count = tableaux.np.sum(-pair_a.br.imag.astype(int) == column)
        smallest_column = tableaux.np.min(barred_columns)
        arguments = [
            [column, box_count, minimum_n0, candidates[index], smallest_column]
            for index in range(candidates.length)
        ]
        next_candidates = tableaux.CandidateList(min_n0=minimum_n0)
        for argument in arguments:
            next_candidates += tableaux.process_iterate_cands_barred(argument)
        candidates = next_candidates
        stages.append(candidates)

    unbarred_columns = tableaux.np.array(
        list(set(pair_a.ubr.real.astype(int).flatten()))
    )
    unbarred_columns = unbarred_columns[unbarred_columns > 0]
    for column in unbarred_columns:
        box_count = tableaux.np.sum(
            pair_a.ubr.real.astype(tableaux.np.int64) == column
        )
        largest_column = tableaux.np.max(unbarred_columns)
        arguments = [
            [column, box_count, minimum_n0, candidates[index],
             largest_column, len_barred_b]
            for index in range(candidates.length)
        ]
        next_candidates = tableaux.CandidateList(min_n0=minimum_n0)
        for argument in arguments:
            next_candidates += tableaux.process_iterate_cands_unbarred(argument)
        candidates = next_candidates
        stages.append(candidates)
    return stages


def evaluate(expression, *, leading_equals=False, leading_assignment=None):
    """Return the input, distribution, column stages and collected exact result."""
    root = parse(expression)
    backend = pair_backend()
    # Direct sums commonly repeat the same tensor product (for example
    # ``A = p ⊕ p`` followed by ``A ⊗ A``).  The legacy backend creates
    # a process pool for every call, so recomputing identical shape products
    # makes a four-term distribution appear to hang.  Coefficients and N0 are
    # applied below; the expensive tableau stages depend only on the shapes.
    multiplication_stages = {}
    lines = []

    def add(node, caption):
        svg = render_tokens(
            tokens(node),
            leading_equals=leading_equals,
            leading_assignment=leading_assignment,
        )
        if not lines or lines[-1]['svg'] != svg:
            lines.append({'svg': svg, 'caption': caption})

    # Preserve the exact written bracket layout on the first line.
    original = []
    term_iter = iter(expression.terms)
    for token in expression.syntax or tuple(t for i in range(len(expression.terms)) for t in (('sum', 'pair') if i else ('pair',))):
        if token == 'pair':
            term = next(term_iter)
            from pair_multiplication.drawing import Drawing, Cell, Label
            state = term.drawing()
            drawing = Drawing(tuple(Cell(c['row'], c['column'], c['dashed'], c['bullet'], tuple(Label(**label) for label in c['labels'])) for c in state['cells']), state['rows'], state['columns'], state['symbol'])
            original.append((term, drawing))
        else:
            original.append(token)
    lines.append({
        'svg': render_tokens(original or ['0'], leading_equals=leading_equals),
        'caption': 'Input',
    })
    monomials = expand(root)
    current = [join('tensor', (atom(term) for term in group)) for group in monomials]
    add(join('sum', current), 'Distribute tensor products over direct sums')
    results = []
    for index, group in enumerate(monomials):
        factors = list(group)
        partial = (factors.pop(0),)
        while factors:
            right = factors.pop(0)
            products = []
            for left_index, left in enumerate(partial):
                coefficient = left.coefficient * right.coefficient
                minimum = max(left.n0, right.n0)
                if not left.barred and not left.unbarred:
                    products.append(replace(right, coefficient=coefficient, n0=minimum, labels=()))
                    continue
                if not right.barred and not right.unbarred:
                    products.append(replace(left, coefficient=coefficient, n0=minimum, labels=()))
                    continue
                shape_product = (
                    left.barred, left.unbarred,
                    right.barred, right.unbarred,
                )
                if shape_product not in multiplication_stages:
                    multiplication_stages[shape_product] = (
                        _pair_multiply_verbosely(
                            backend,
                            (left.barred, left.unbarred),
                            (right.barred, right.unbarred),
                        )
                    )
                stages = multiplication_stages[shape_product]
                for column, stage in enumerate(stages, 1):
                    candidates = []
                    for candidate in stage.pairs:
                        term = PairTerm(tuple(map(int, candidate.br.get_partition())), tuple(map(int, candidate.ubr.get_partition())), coefficient, max(minimum, int(candidate.n0)))
                        candidates.append(atom(term, backend.draw_tableau(candidate)))
                    pending = remainder(right, column)
                    active = join('sum', candidates)
                    if pending:
                        active = join('tensor', (active, atom(PairTerm(n0=right.n0), pending)))
                    # Other branches stay visible while this branch is expanded.
                    branches = [atom(term) for term in products] + [active]
                    branches += [join('tensor', (atom(term), atom(right))) for term in partial[left_index+1:]]
                    current[index] = join('tensor', (join('sum', branches), *(atom(term) for term in factors)))
                    add(join('sum', current), f'Column {column}: labeled tableaux')
                if stages:
                    for candidate in stages[-1].pairs:
                        products.append(PairTerm(tuple(map(int, candidate.br.get_partition())), tuple(map(int, candidate.ubr.get_partition())), coefficient, max(minimum, int(candidate.n0))))
            partial = collect(products)
            current[index] = join('tensor', (join('sum', (atom(term) for term in partial)), *(atom(term) for term in factors)))
            add(join('sum', current), 'Remove tableau labels and collect equal pairs')
        results.extend(partial)
    final = PairExpression(collect(results))
    final_node = join('sum', (atom(term) for term in final.terms))
    final_svg = render_tokens(
        tokens(final_node),
        leading_equals=leading_equals,
        leading_assignment=leading_assignment,
    )
    if not lines or lines[-1]['svg'] != final_svg:
        lines.append({'svg': final_svg, 'caption': 'Collect the final direct sum'})
    return {'lines': lines, 'result': final.state(), 'error': ''}
