"""Focused browser checks for result ownership and unary sign formatting."""

import base64
from pathlib import Path

import pytest

playwright = pytest.importorskip('playwright.sync_api')
STATIC = Path(__file__).parents[2] / 'src/birdtracks/projectors/static'


@pytest.fixture
def result_page():
    with playwright.sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch()
        except playwright.Error as exc:
            pytest.skip(f'Chromium unavailable: {exc}')
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('http://projection.test/', lambda route: route.fulfill(
            content_type='text/html', body='<div id="widget"></div>'))
        page.goto('http://projection.test/')
        page.add_style_tag(content=(STATIC / 'whiteboard-widget.css').read_text())
        source = base64.b64encode((STATIC / 'whiteboard-widget.js').read_bytes()).decode()
        page.evaluate('''async source => {
          window.module = await import('data:text/javascript;base64,' + source);
          function model(values) {
            if(values.widget_role==='whiteboard')values.document_state={version:1,revision:0,blocks:structuredClone(values.blocks)};
            const listeners = new Map();
            return {
              get: key => values[key],
              set(key, value) {
                if (JSON.stringify(values[key]) === JSON.stringify(value)) return;
                values[key] = value;
                if(key==='blocks' && values.widget_role==='whiteboard')this.set('document_state',{
                  version:1,revision:values.document_state.revision+1,blocks:structuredClone(value)});
                for (const fn of [...(listeners.get('change:' + key) || [])]) fn(this,value,{});
              },
              on(names, fn) { for (const name of names.split(' ')) {
                if (!listeners.has(name)) listeners.set(name,new Set());
                listeners.get(name).add(fn);
              }},
              off(names, fn) { for (const name of names.split(' ')) listeners.get(name)?.delete(fn); },
              save_changes() {},
            };
          }
          window.makeModel = model;
          window.child = model({mode: 'evaluate', editor_state: {version: 1},
            graph: {nodes: [{index: 0,kind: 'antisymmetriser',labels: [1,2],
              input_labels: [1,2],output_labels: [1,2]}]},
            port_orders: {'0': {input: [1,2],output: [1,2]}}});
          window.board = model({widget_role: 'whiteboard', title: '',
            blocks: [{id: 'result', source: '= - \\\\frac{2}{3}R',read_only: true,
              backend_terms: [{id: 'result:backend:0',start: 15,end: 16,prefactor_owned: true}]}],
            backend_projector_ids: ['result:backend:0'], backend_projectors: ['child']});
          window.cleanup = module.default.render({model: board,
            el: document.querySelector('#widget'), signal: null,
            host: {getModel: async () => child,
              getWidget: async () => ({render: async ({el}) => {el.dataset.mounted='yes';}})}});
        }''', source)
        page.wait_for_selector('[data-mounted="yes"]', state='attached')
        yield page
        page.evaluate('cleanup()')
        browser.close()
        assert not errors


@pytest.mark.parametrize('source, expected', [
    (r'= - \frac{2}{3}R', r'= \frac{2}{3}R'),
    (r'= - 2R', r'= 2R'),
    (r'- \frac{2}{3}R', r'\frac{2}{3}R'),
    (r'P \def - 2R', r'P \def 2R'),
    (r'P := - 2R', r'P := 2R'),
    (r'X - \frac{2}{3}R', r'X + \frac{2}{3}R'),
    (r'= 2R', r'= -2R'),
])
def test_positive_unary_sign_is_omitted_but_binary_plus_is_kept(result_page, source, expected):
    assert result_page.evaluate(
        "source => module.flipProjectorTermSign(source,source.indexOf('R'))", source) == expected


def test_accepted_python_projection_is_not_recompensated_by_javascript(result_page):
    before = result_page.evaluate("board.get('blocks')[0].source")
    result_page.evaluate('''() => {
      child.set('port_orders', {'0': {input: [2,1],output: [1,2]}});
      child.set('graph', {nodes: [{index:0,kind:'antisymmetriser',labels:[1,2],
        input_labels:[2,1],output_labels:[1,2]}]});
    }''')
    assert result_page.evaluate("board.get('blocks')[0].source") == before
    result_page.evaluate('''() => board.set('blocks', [{...board.get('blocks')[0],
      source: '= \\\\frac{2}{3}R', backend_terms: [
        {id:'result:backend:0',start:13,end:14,prefactor_owned:true}]}])''')
    result_page.wait_for_selector('[data-mounted="yes"]', state='attached')
    assert result_page.evaluate("board.get('blocks')[0].source") == r'= \frac{2}{3}R'


@pytest.mark.parametrize('edge', ['top', 'bottom'])
def test_real_recursive_control_generates_an_exact_python_line(result_page, edge):
    from birdtracks import Antisymmetriser, Connection, NodePort, Projector, ProjectorSum, Symmetriser
    from birdtracks.projectors.whiteboard.projector_codec import projector_codec
    from birdtracks.projectors.whiteboard.widget import _result_source, whiteboard

    p = Projector([Symmetriser((1, 2)), Antisymmetriser((7, 8, 9))],
        connections=[Connection(NodePort(1, 7), NodePort(0, 2))],
        input_boundary={1: NodePort(0, 1), 2: NodePort(1, 7), 3: NodePort(1, 8), 4: NodePort(1, 9)},
        output_boundary={1: NodePort(0, 1), 2: NodePort(0, 2), 3: NodePort(1, 8), 4: NodePort(1, 9)})
    value = ProjectorSum((p,))
    source, terms = _result_source(value)
    board = whiteboard()
    board.blocks = [{'id': 'result', 'source': source, 'read_only': True,
        'calculation_group': 'group', 'calculation_step': 1,
        'calculation_value': projector_codec.encode(value), 'calculation_terms': terms}]
    child = board.backend_projectors[0]
    received = set()

    def command(_source, request):
        editor_request = request.get('editor_request')
        if editor_request and editor_request['request_id'] not in received:
            received.add(editor_request['request_id'])
            child.editor_request = editor_request
        return {key: value for key, value in child.get_state().items()
                if not key.startswith('_') and key not in {'editor_request', 'expand_node_request', 'save_command'}}

    result_page.expose_binding('pythonCommand', command)
    state = {key: value for key, value in child.get_state().items() if not key.startswith('_')}
    module = base64.b64encode((STATIC / 'projector-widget.js').read_bytes()).decode()
    result_page.add_style_tag(content=(STATIC / 'projector-widget.css').read_text())
    result_page.evaluate('''async ({state, source}) => {
      cleanup(); const el=document.querySelector('#widget'); el.replaceChildren();
      window.child=makeModel(state);
      child.save_changes=()=>window.pythonCommand({editor_request: child.get('editor_request'),
        }).then(reply=>{
        for(const [key,value] of Object.entries(reply)) if(!['editor_state','editor_feedback'].includes(key)) child.set(key,value);
        child.set('editor_state',reply.editor_state); child.set('editor_feedback',reply.editor_feedback);
        window.commandsDone=Number(window.commandsDone || 0)+1;
      });
      const module=await import('data:text/javascript;base64,'+source);
      window.cleanup=module.default.render({model:child,el});
    }''', {'state': state, 'source': module})
    result_page.get_by_role('button', name=f'Recursively expand from the {edge} line').nth(1).click()
    result_page.wait_for_function('Number(window.commandsDone || 0)>=2')
    assert board.blocks[-1]['calculation_step'] == 2
    assert projector_codec.decode(board.blocks[-1]['calculation_value']).collapse() == p.collapse()
    for item in board.blocks[-1]['calculation_terms']:
        rendered = projector_codec.decode(item['value'])
        assert rendered.coefficient == reconstruct_coefficient(rendered)


def reconstruct_coefficient(projector):
    from fractions import Fraction
    from birdtracks.projectors.layout import widget_graph

    coefficient = widget_graph(projector)['coefficient']
    return Fraction(int(coefficient['numerator']), int(coefficient['denominator']))


@pytest.mark.parametrize('source_kind', ['rational', 'unit', 'explicit', 'binary'])
@pytest.mark.parametrize('finish', ['commit', 'cancel', 'reject'])
@pytest.mark.parametrize('initially_negative', [False, True])
def test_whiteboard_owned_sign_previews_without_source_writes_or_remounts(result_page, source_kind, finish, initially_negative):
    from copy import deepcopy
    from fractions import Fraction
    from birdtracks import Antisymmetriser, Projector, ProjectorSum
    from birdtracks.projectors.whiteboard.projector_codec import projector_codec
    from birdtracks.projectors.whiteboard.widget import _result_source, whiteboard

    coefficient = Fraction(1) if source_kind == 'unit' else Fraction(2, 3)
    p = Projector([Antisymmetriser((1, 2, 3))],
                  coefficient=-coefficient if initially_negative else coefficient)
    value = ProjectorSum((p,))
    source, terms = _result_source(value)
    board = whiteboard()
    board.blocks = [{'id': 'result', 'source': source, 'read_only': True,
                     'calculation_group': 'group', 'calculation_step': 1,
                     'calculation_value': projector_codec.encode(value), 'calculation_terms': terms}]
    child = board.backend_projectors[0]
    initial = deepcopy(child.editor_state)
    requests = []

    def command(_source, request):
        requests.append(request)
        child.editor_request = request
        return {'child': {key: value for key, value in child.get_state().items()
                          if not key.startswith('_')}, 'blocks': board.blocks}

    result_page.expose_binding('previewCommand', command)
    state = {key: value for key, value in child.get_state().items() if not key.startswith('_')}
    blocks = deepcopy(board.blocks)
    if source_kind == 'binary':
        blocks[0]['source'] = 'X - ' + source[4:] if initially_negative else 'X + ' + source[2:]
        blocks[0]['backend_terms'][0]['start'] = blocks[0]['source'].index('R')
        blocks[0]['backend_terms'][0]['end'] = blocks[0]['source'].index('R') + 1
    if source_kind == 'explicit':
        blocks = [{'id': 'result', 'source': source.replace('R', r'\birdtracks'), 'read_only': True}]
    canvas_source = base64.b64encode((STATIC / 'projector-widget.js').read_bytes()).decode()
    result_page.add_style_tag(content=(STATIC / 'projector-widget.css').read_text())
    result_page.evaluate('''async ({state, blocks, canvasSource, explicit, reject}) => {
      cleanup(); document.querySelector('#widget').replaceChildren();
      window.child=makeModel(state);
      window.board=makeModel({widget_role:'whiteboard',title:'',blocks,
        backend_projector_ids:explicit ? [] : ['result:backend:0'],
        backend_projectors:explicit ? [] : ['child'],
        embedded_projector_ids:explicit ? ['result:projector:0'] : [],
        embedded_projectors:explicit ? ['child'] : []});
      child.save_changes=()=>{
        const request=child.get('editor_request');
        if(!request?.request_id || child.lastSent===request.request_id) return;
        child.lastSent=request.request_id;
        previewCommand({...request,...(reject ? {base_revision:-1} : {})}).then(reply=>{
          for(const [key,value] of Object.entries(reply.child))
            if(!['editor_request','editor_state','editor_feedback'].includes(key)) child.set(key,value);
          child.set('editor_state',reply.child.editor_state);
          child.set('editor_feedback',reply.child.editor_feedback);
          if(!reject) board.set('blocks',reply.blocks);
        });
      };
      const canvas=await import('data:text/javascript;base64,'+canvasSource);
      window.mountCount=0;
      window.cleanup=module.default.render({model:board,el:document.querySelector('#widget'),
        host:{getModel:async()=>child,getWidget:async()=>({render:({el})=>{
          mountCount++; return canvas.default.render({model:child,el});
        }})}});
    }''', {'state': state, 'blocks': blocks, 'canvasSource': canvas_source,
           'explicit': source_kind == 'explicit', 'reject': finish == 'reject'})
    result_page.wait_for_selector('[aria-label^="input:0:1;"]', state='attached')
    assert result_page.evaluate("child.get('prefactor_owned')")
    prefix = result_page.locator('.birdtracks-whiteboard-embedded-projector').locator('xpath=preceding-sibling::span[1]')
    before_text = prefix.inner_text()
    assert ('−' in before_text) == initially_negative
    before_blocks = result_page.evaluate("board.get('blocks')")
    mounts = result_page.evaluate('mountCount')
    result_page.locator('.birdtracks-whiteboard-embedded-projector').first.click(position={'x':2,'y':2})
    points = [result_page.locator(f'[aria-label^="input:0:{i};"]').bounding_box() for i in (1, 2, 3)]
    result_page.mouse.move(points[0]['x'] + points[0]['width']/2, points[0]['y'] + points[0]['height']/2)
    result_page.mouse.down()
    for slot, odd in [(1, True), (2, False), (1, True)]:
        point = points[slot]
        result_page.mouse.move(point['x'] + point['width']/2, point['y'] + point['height']/2, steps=5)
        assert ('−' in prefix.inner_text()) == (initially_negative != odd)
        assert result_page.evaluate("board.get('blocks')") == before_blocks
        assert result_page.evaluate('mountCount') == mounts
        assert child.editor_state == initial
        assert requests == []
    if finish == 'cancel':
        result_page.evaluate("document.dispatchEvent(new PointerEvent('pointercancel'))")
    result_page.mouse.up()
    if finish == 'commit':
        result_page.wait_for_function("child.get('editor_state').revision === 1")
        assert child.editor_state['display']['sign'] == ('' if initially_negative else '-')
        assert ('−' in prefix.inner_text()) == (not initially_negative)
    else:
        if finish == 'reject':
            result_page.wait_for_function("Boolean(child.get('editor_feedback').error)")
        assert prefix.inner_text() == before_text
        assert result_page.evaluate("board.get('blocks')") == before_blocks
        assert child.editor_state == initial
