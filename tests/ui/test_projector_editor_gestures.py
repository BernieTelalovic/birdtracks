"""Real shipped canvas gestures connected to the Python command adapter."""

import base64
from copy import deepcopy
from fractions import Fraction
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
STATIC = Path(__file__).parents[2] / "src/birdtracks/projectors/static"


@pytest.fixture
def connected_canvas(tmp_path, request):
    from birdtracks import Antisymmetriser, Permutation, PermutationNode, Projector, ProjectorSum, Symmetriser
    from birdtracks.projectors.widget import projector_sum_widget

    p = Projector([Antisymmetriser((1, 2, 3)), Symmetriser((3, 4))], coefficient=Fraction(-2, 3))
    surface_kind = getattr(request, "param", "")
    if surface_kind and not surface_kind.startswith("surface:"):
        permutation = PermutationNode(Permutation.from_cycle(1, 2), support=(1, 2, 3))
        nodes = {
            "operator": [Antisymmetriser((1, 2, 3))],
            "trailing": [Antisymmetriser((1, 2, 3)), permutation],
            "interior": [Antisymmetriser((1, 2, 3)), permutation, Symmetriser((3, 4))],
            "pure": [permutation],
            "cleanup": [Symmetriser((1,2)),Antisymmetriser((2,3,4)),Symmetriser((1,2)),
                        PermutationNode(Permutation.from_cycle(2,3),support=(2,3,4)),
                        Antisymmetriser((3,4)),Symmetriser((1,2))],
            "layers": [Symmetriser((1,2)),Antisymmetriser((2,3,4)),Symmetriser((1,2)),
                       PermutationNode(Permutation.identity(),support=(2,)),
                       PermutationNode(Permutation.from_cycle(2,3),support=(2,3,4)),
                       Antisymmetriser((3,4)),
                       PermutationNode(Permutation.identity(),support=(2,)),Symmetriser((1,2))],
            "misaligned": [Symmetriser((1,2)),Antisymmetriser((3,4)),
                           PermutationNode(Permutation.from_cycle(2,3),support=(2,3,4)),
                           Antisymmetriser((3,4)),Symmetriser((1,2))],
        }["misaligned" if request.param.startswith("misaligned") else request.param]
        p = Projector(nodes, coefficient=Fraction(-2, 3))
    initial = ProjectorSum((p,))
    if surface_kind == "cleanup":
        p = p * (Fraction(-2,3) / p.coefficient)
        plain = Projector([Symmetriser((1,2)),Antisymmetriser((2,3,4)),Symmetriser((1,2))],coefficient=Fraction(1,3))
        initial = ProjectorSum((plain,p))
    canvas = projector_sum_widget(initial, shared_editor=True,
                                  session=tmp_path / "gestures", detangler=False, debug=True)
    child = canvas._term_editors[0]
    if surface_kind == "cleanup":
        child = next(e for e in canvas._term_editors if len(e.projector.nodes)==6)
    if surface_kind.startswith("misaligned"):
        dy = 0.35 if surface_kind == "misaligned-fractional" else 0
        child._editor_session.move({identity:position for identity,position in zip(child.editor_state["node_ids"],
            ({"x":1.5,"y":2},{"x":3.5,"y":4+dy},{"x":4.1,"y":3.5},
             {"x":4.7,"y":4+dy},{"x":5.5,"y":2}),strict=True)},base_revision=child.editor_state["revision"])
        child._publish_editor()
    document = None
    if surface_kind.startswith("surface:"):
        from tests.conformance.test_editor_surfaces import surface
        kind = surface_kind.split(":", 1)[1]
        child, canvas, _reopen, p = surface(kind, Fraction(-2, 3), tmp_path / "interface.whiteboard")
        document = getattr(child, "_conformance_document", None)
    requests = []
    with playwright.sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch()
        except playwright.Error as exc:
            pytest.skip(f"Chromium unavailable: {exc}")
        page = browser.new_page(viewport={"width": 1200, "height": 800})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def command(_source, request):
            requests.append(deepcopy(request))
            if "calculation_request" in request:
                child.expand_node_request = request["calculation_request"]
            else:
                child.editor_request = request
            reply = {key: value for key, value in child.get_state().items()
                     if not key.startswith("_") and key not in {"editor_request", "save_command", "local_undo_command"}}
            if document is not None:
                reply["document_blocks"] = ([block for block in document.blocks if block['id'] == 'line']
                                            if kind == 'parsed' else document.blocks)
            return reply

        page.expose_binding("pythonEditorCommand", command)
        page.set_content('<div class="birdtracks-projector-sum"><div id="canvas"></div></div>')
        page.add_style_tag(content=(STATIC / "projector-widget.css").read_text())
        state = {key: value for key, value in child.get_state().items() if not key.startswith("_")}
        source = base64.b64encode((STATIC / "projector-widget.js").read_bytes()).decode()
        board_source = base64.b64encode((STATIC / "whiteboard-widget.js").read_bytes()).decode()
        board_state = None
        if document is not None:
            page.add_style_tag(content=(STATIC / "whiteboard-widget.css").read_text())
            board_state = {"widget_role": "whiteboard", "title": "", "blocks": ([block for block in document.blocks if block['id'] == 'line']
                                                                                   if kind == 'parsed' else document.blocks),
                           "embedded_projector_ids": document.embedded_projector_ids,
                           "backend_projector_ids": document.backend_projector_ids,
                           "embedded_projectors": ["child"] * len(document.embedded_projector_ids),
                           "backend_projectors": ["child"] * len(document.backend_projector_ids)}
        page.evaluate("""async ({state, source, boardSource, boardState}) => {
          const values = structuredClone(state), listeners = new Map();
          window.model = {
            model_id: 'python-connected-canvas', get: key => values[key],
            set(key, value) {
              if (JSON.stringify(values[key]) === JSON.stringify(value)) return;
              values[key] = value;
              for (const fn of listeners.get('change:' + key) || []) fn({new:value});
            },
            on(names, fn) { for (const name of names.split(' ')) {
              if (!listeners.has(name)) listeners.set(name,new Set());
              listeners.get(name).add(fn);
            }},
            off(names, fn) { for (const name of names.split(' ')) listeners.get(name)?.delete(fn); },
            save_changes() {
              let request = values.editor_request;
              const calculation = values.expand_node_request;
              if (calculation?.revision && this.lastCalculation !== calculation.revision) {
                this.lastCalculation = calculation.revision;
                request = {calculation_request: structuredClone(calculation)};
              } else {
                if (!request?.request_id || this.lastSent === request.request_id) return;
                this.lastSent = request.request_id;
              }
              window.pythonEditorCommand(structuredClone(request)).then(reply => {
                for (const [key,value] of Object.entries(reply))
                  if (!['editor_state','editor_feedback','document_blocks'].includes(key)) model.set(key,value);
                model.set('editor_state',reply.editor_state);
                model.set('editor_feedback',reply.editor_feedback);
                if(reply.document_blocks) board.set('blocks',reply.document_blocks);
              });
            },
          };
          const module = await import('data:text/javascript;base64,'+source);
          let render=()=>module.default.render({model,el:document.querySelector('#canvas')});
          if(boardState){
            const boardModule=await import('data:text/javascript;base64,'+boardSource);
            const values=structuredClone(boardState), listeners=new Map();
            window.board={get:key=>values[key],set(key,value){
              if(JSON.stringify(values[key])===JSON.stringify(value)) return;
              values[key]=value; for(const fn of listeners.get('change:'+key)||[]) fn(this,value,{});
            },on(names,fn){for(const name of names.split(' ')){
              if(!listeners.has(name))listeners.set(name,new Set());listeners.get(name).add(fn);
            }},off(names,fn){for(const name of names.split(' '))listeners.get(name)?.delete(fn);},save_changes(){}};
            render=()=>boardModule.default.render({model:board,el:document.querySelector('#canvas'),
              host:{getModel:async()=>model,getWidget:async()=>({render:({el})=>module.default.render({model,el})})}});
          }
          window.cleanup = render();
          window.remount = () => {
            cleanup(); document.querySelector('#canvas').replaceChildren();
            window.cleanup=render();
          };
        }""", {"state": state, "source": source, "boardSource": board_source, "boardState": board_state})
        page.wait_for_selector('[aria-label="right-anchor:0"]', state='attached')
        yield page, canvas, child, requests, p
        page.evaluate("cleanup()")
        browser.close()
        assert not errors


def drag(page, side, source_label, destination_label, *, node=0):
    source = page.locator(f'[aria-label^="{side}:{node}:{source_label};"]')
    target = page.locator(f'[aria-label^="{side}:{node}:{destination_label};"]')
    a, b = source.bounding_box(), target.bounding_box()
    page.mouse.move(a["x"] + a["width"] / 2, a["y"] + a["height"] / 2)
    page.mouse.down()
    page.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, steps=5)
    page.mouse.up()


def move_hit(page, selector, dy, *, cancel=False):
    box = page.locator(selector).first.bounding_box()
    assert box
    x, y = box['x'] + box['width']/2, box['y'] + box['height']/2
    page.mouse.move(x,y)
    page.mouse.down()
    page.mouse.move(x,y+dy,steps=6)
    if cancel:
        page.evaluate("document.dispatchEvent(new PointerEvent('pointercancel',{bubbles:true}))")
    page.mouse.up()


@pytest.mark.parametrize("connected_canvas", ["cleanup"], indirect=True)
@pytest.mark.parametrize("full", [False, True])
def test_real_expansion_gesture_collects_mixed_terms_and_discards_zero(connected_canvas, full):
    page, canvas, child, requests, original = connected_canvas
    initial = canvas.current_projector_sum
    if full:
        page.locator('.birdtracks-node[data-node="2"] rect').dblclick()
    else:
        page.get_by_role('button',name='Recursively expand from the top line').nth(2).dispatch_event('pointerdown')
    page.wait_for_function("!!model.get('editor_rewrite')?.request_id")
    assert len(canvas._line_states)==2
    assert len(canvas._term_editors)==1
    assert canvas.current_projector_sum.collapse()==initial.collapse()
    assert not child.editor_feedback.get('error')


@pytest.mark.parametrize("connected_canvas", ["layers"], indirect=True)
def test_layer_bands_are_straight_and_crossings_stay_in_connectors(connected_canvas):
    page, canvas, child, requests, original = connected_canvas
    initial = deepcopy(child.editor_state)
    geometry = initial["graph"]["geometry"]
    columns = initial["graph"]["display"]["operator_columns"]
    assert columns == [[0], [1], [2], [5, 7]]
    xs = [initial["positions"][str(group[0])]["x"] for group in columns]
    assert all(b-a == pytest.approx(geometry["node_width"]+geometry["step"]) for a,b in zip(xs,xs[1:]))
    assert initial["graph"]["display"]["corridor_widths"] == [geometry["step"]] * 5

    def assert_straight_layers():
        assert page.locator('.birdtracks-node rect').count() == 5
        assert not page.evaluate("""() => {
          const bands=[...document.querySelectorAll('.birdtracks-node rect')].map(r=>({
            left:Number(r.getAttribute('x'))+0.04,
            right:Number(r.getAttribute('x'))+Number(r.getAttribute('width'))-0.04}));
          const bends=[];
          for(const path of document.querySelectorAll('.birdtracks-display-strand')){
            const length=path.getTotalLength();
            for(let d=0.02;d<length-0.02;d+=0.02){
              const a=path.getPointAtLength(d-0.01), b=path.getPointAtLength(d+0.01);
              if(bands.some(band=>a.x>band.left&&a.x<band.right&&b.x>band.left&&b.x<band.right)
                 && Math.abs(a.y-b.y)>0.001){bends.push(path.dataset.lineKey);break;}
            }
          }
          return bends;
        }""")

    assert_straight_layers()
    for node, side, a, b in ((5,"input",3,4),(5,"output",3,4),(1,"input",2,3),(1,"output",2,3)):
        revision = child.editor_state["revision"]
        drag(page,side,a,b,node=node)
        page.wait_for_function("r=>model.get('editor_state').revision>r",arg=revision)
        assert child.editor_state["positions"] == initial["positions"]
        assert_straight_layers()
        assert canvas.current_projector_sum.collapse() == original.collapse()
    page.screenshot(path='/tmp/birdtracks-layer-connectors.png')


@pytest.mark.parametrize("connected_canvas", ["misaligned", "misaligned-fractional"], indirect=True)
def test_misaligned_columns_route_outside_boxes_before_and_after_port_drags(connected_canvas):
    page, canvas, child, requests, original = connected_canvas
    positions = deepcopy(child.editor_state["positions"])
    def collisions():
        return page.evaluate("""() => {
          const boxes=[...document.querySelectorAll('.birdtracks-node rect')].map(rect=>({
            node:Number(rect.parentElement.dataset.node),x:Number(rect.getAttribute('x')),
            y:Number(rect.getAttribute('y')),w:Number(rect.getAttribute('width')),h:Number(rect.getAttribute('height'))}));
          const hits=[];
          for(const path of document.querySelectorAll('.birdtracks-display-strand')){
            const key=path.dataset.lineKey;
            const endpoints=key.split('->').map(e=>e.match(/^(?:input|output):(\\d+):/)).filter(Boolean).map(m=>Number(m[1]));
            const length=path.getTotalLength();
            for(let distance=0;distance<=length;distance+=0.02){
              const p=path.getPointAtLength(distance);
              for(const box of boxes)if(!endpoints.includes(box.node)
                &&p.x>box.x+0.04&&p.x<box.x+box.w-0.04&&p.y>box.y+0.04&&p.y<box.y+box.h-0.04){
                hits.push({key,node:box.node});distance=length+1;break;
              }
            }
          }
          return hits;
        }""")
    assert not collisions()
    for node,side in ((3,"input"),(3,"output"),(1,"input"),(1,"output")):
        revision = child.editor_state["revision"]
        drag(page,side,3,4,node=node)
        page.wait_for_function("r=>model.get('editor_state').revision>r",arg=revision)
        assert not collisions()
        assert child.editor_state["positions"] == positions
        assert canvas.current_projector_sum.collapse() == original.collapse()


@pytest.mark.parametrize("connected_canvas", ["surface:widget", "surface:canvas", "surface:generated", "surface:inline", "surface:parsed", "surface:symbolic"], indirect=True)
def test_movement_and_routing_use_python_history_without_trait_writes(connected_canvas):
    page, value, child, requests, original = connected_canvas
    before = deepcopy(child.editor_state)
    move_hit(page,'.birdtracks-node[data-node="0"] rect',45)
    page.wait_for_function("revision=>model.get('editor_state').revision>revision",arg=before['revision'])
    assert requests[-1]['action'] == 'move'
    assert len(child._editor_session._undo) == 1
    assert value().collapse() == original.collapse()
    page.keyboard.press('Control+z')
    page.wait_for_function("revision=>model.get('editor_state').revision>revision",arg=before['revision']+1)
    assert child.editor_state['positions'] == before['positions']
    page.keyboard.press('Control+Shift+z')
    page.wait_for_function("revision=>model.get('editor_state').revision>revision",arg=before['revision']+2)
    state = deepcopy(child.editor_state)
    move_hit(page,'.birdtracks-route-handle',45)
    page.wait_for_function("revision=>model.get('editor_state').revision>revision",arg=state['revision'])
    assert requests[-1]['action'] == 'reroute'
    assert value().collapse() == original.collapse()
    accepted = deepcopy(child.editor_state)
    count = len(requests)
    move_hit(page,'.birdtracks-node[data-node="0"] rect',45,cancel=True)
    assert len(requests) == count
    assert child.editor_state == accepted
    page.evaluate('remount()')
    assert page.evaluate("model.get('editor_state').positions") == accepted['positions']


def test_recursive_control_uses_shared_rewrite_not_legacy_expansion(connected_canvas):
    page, canvas, child, requests, original = connected_canvas
    page.get_by_role('button',name='Recursively expand from the top line').first.dispatch_event('pointerdown')
    page.wait_for_function("!!model.get('editor_rewrite')?.request_id")
    assert requests[-1]['action'] == 'expand'
    assert not page.evaluate("model.get('expand_node_request')?.revision")
    assert canvas.current_projector_sum.collapse() == original.collapse()
    assert len(canvas._line_states) == 2


def test_python_replacement_reconciles_topology_and_undo_in_real_frontend(connected_canvas):
    from birdtracks import Antisymmetriser, Projector
    from birdtracks.projectors.whiteboard.projector_codec import projector_codec
    page, canvas, child, requests, original = connected_canvas
    old = deepcopy(child.editor_state)
    replacement = projector_codec.encode(Projector([Antisymmetriser((1,2,3)),Antisymmetriser((1,2,3))]))
    page.evaluate("""async replacement=>{
      const state=model.get('editor_state');
      const reply=await pythonEditorCommand({action:'replace',request_id:'ui-replacement',
        term_id:state.term_id,base_revision:state.revision,node_id:state.node_ids[0],replacement});
      model.set('editor_state',reply.editor_state);model.set('editor_feedback',reply.editor_feedback);
    }""",replacement)
    page.wait_for_selector('[data-node="2"] rect')
    assert child.editor_state['node_ids'][-1] == old['node_ids'][-1]
    assert canvas.current_projector_sum.collapse() == original.collapse()
    page.keyboard.press('Control+z')
    page.wait_for_function("model.get('editor_state').graph.nodes.length===2")
    assert child.editor_state['node_ids'] == old['node_ids']


def test_create_invalid_drop_restores_graph_and_valid_reconnection_commits_once(connected_canvas):
    page, canvas, child, requests, original = connected_canvas
    child.mode = 'create'
    page.evaluate("model.set('mode','create')")
    before = deepcopy(child.editor_state)
    endpoint = page.locator('[aria-label^="input:0:1;"]').bounding_box()
    x,y=endpoint['x']+endpoint['width']/2,endpoint['y']+endpoint['height']/2
    page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+100,y+100,steps=5);page.mouse.up()
    assert not requests
    assert child.editor_state == before
    assert page.locator('[aria-label^="input:0:1;"]').count() == 1
    drag(page,'input',1,2)
    page.wait_for_function("revision=>model.get('editor_state').revision>revision",arg=before['revision'])
    assert len(requests) == 1
    assert requests[0]['action'] == 'reconnect'
    assert not child.editor_feedback.get('error')
    assert child.editor_state['node_ids'] == before['node_ids']
    page.keyboard.press('Control+z')
    page.wait_for_function("revision=>model.get('editor_state').revision>revision",arg=before['revision']+1)
    assert canvas.current_projector_sum.collapse() == original.collapse()


@pytest.mark.parametrize("connected_canvas", ["surface:widget", "surface:canvas", "surface:generated", "surface:inline", "surface:parsed", "surface:symbolic"], indirect=True)
def test_identical_drag_sequences_use_one_shared_transaction_on_every_surface(connected_canvas):
    page, value, child, requests, original = connected_canvas
    for side, source_label, target_label in [("input", 1, 2), ("output", 1, 2),
                                             ("input", 2, 3), ("input", 1, 2), ("output", 2, 1)]:
        old = deepcopy(child.editor_state)
        count = len(requests)
        history = len(child._editor_session._undo)
        drag(page, side, source_label, target_label)
        page.wait_for_function("revision=>model.get('editor_state').revision>revision", arg=old['revision'])
        assert len(requests) == count + 1
        assert requests[-1]['action'] == 'reorder'
        assert len(child._editor_session._undo) == history + 1
        assert value().collapse() == original.collapse()
        page.keyboard.press('Control+z')
        page.wait_for_function("revision=>model.get('editor_state').revision===revision", arg=old['revision'] + 2)
        assert child.editor_state['port_orders'] == old['port_orders']
        assert value().collapse() == original.collapse()
        page.keyboard.press('Control+Shift+z')
        page.wait_for_function("revision=>model.get('editor_state').revision===revision", arg=old['revision'] + 3)
        accepted = deepcopy(child.editor_state)
        ports = page.locator('[aria-label^="input:0:"]').evaluate_all("nodes=>nodes.map(n=>[n.getAttribute('aria-label'),n.getAttribute('cy')])")
        page.evaluate("old=>{for(const key of ['graph','port_orders','positions','free_levels','boundary_orders','line_colors'])model.set(key,old[key]);}", old)
        page.evaluate("old=>model.set('editor_state',old)", old)
        assert page.evaluate("model.get('editor_state').revision") == accepted['revision']
        page.evaluate('remount()')
        page.wait_for_selector(f'[aria-label^="{side}:0:{target_label};"]', state='attached')
        assert child.editor_state == accepted
        assert page.locator('[aria-label^="input:0:"]').evaluate_all("nodes=>nodes.map(n=>[n.getAttribute('aria-label'),n.getAttribute('cy')])") == ports


@pytest.mark.parametrize("connected_canvas", ["surface:widget", "surface:canvas", "surface:generated", "surface:inline", "surface:parsed", "surface:symbolic"], indirect=True)
def test_delayed_reorder_and_remount_keep_shared_save_order_on_every_surface(connected_canvas):
    page, value, child, requests, original = connected_canvas
    before = deepcopy(child.editor_state)
    page.evaluate("""() => {
      const send=pythonEditorCommand;
      window.pythonEditorCommand=async request=>{
        const reply=await send(request);
        if(request.action==='reorder') await new Promise(resolve=>window.releaseMigrationAck=resolve);
        return reply;
      };
    }""")
    drag(page, 'input', 1, 2)
    page.wait_for_function("typeof releaseMigrationAck==='function'")
    page.evaluate("model.set('save_command',1); remount(); releaseMigrationAck()")
    page.wait_for_function("model.get('saved_revision')>=1")
    assert [request['action'] for request in requests] == ['reorder', 'save']
    accepted = deepcopy(child.editor_state)
    page.evaluate("old=>model.set('editor_state',old)", before)
    assert page.evaluate("model.get('editor_state').revision") == accepted['revision']
    assert child.configuration.state()['editor_state']['state']['revision'] == accepted['revision']
    assert value().collapse() == original.collapse()


@pytest.mark.parametrize("connected_canvas", ["surface:symbolic"], indirect=True)
def test_symbolic_drag_uses_python_compiled_factor_preview(connected_canvas):
    page, _value, child, requests, _original = connected_canvas
    accepted = deepcopy(child.editor_state)
    blocks = page.evaluate("board.get('blocks')")
    prefix = page.locator('.birdtracks-whiteboard-embedded-projector').locator('xpath=preceding-sibling::span[1]')
    assert '−' in prefix.inner_text()
    a = page.locator('[aria-label^="input:0:1;"]').bounding_box()
    b = page.locator('[aria-label^="input:0:2;"]').bounding_box()
    page.mouse.move(a['x'] + a['width']/2, a['y'] + a['height']/2)
    page.mouse.down()
    page.mouse.move(b['x'] + b['width']/2, b['y'] + b['height']/2, steps=5)
    assert '−' not in prefix.inner_text()
    assert page.evaluate("board.get('blocks')") == blocks
    assert child.editor_state == accepted
    assert requests == []
    page.mouse.up()
    page.wait_for_function("model.get('editor_state').revision===1")
    assert '−' not in prefix.inner_text()
    assert page.evaluate("board.get('blocks')[0].calculation_terms[0].scalar_terms") == blocks[0]['calculation_terms'][0]['scalar_terms']


@pytest.mark.parametrize("connected_canvas", ["operator", "trailing", "interior", "pure"], indirect=True)
def test_evaluate_bounds_ignore_hidden_positions_and_preserve_visible_placement(connected_canvas):
    page, canvas, child, _requests, _p = connected_canvas
    accepted = deepcopy(child.editor_state)
    value = canvas.current_projector_sum
    geometry = accepted["graph"]["geometry"]
    def right():
        return float(page.locator('[aria-label="right-anchor:0"]').get_attribute("cx"))
    assert right() == pytest.approx(geometry["right_boundary"])
    paths = page.locator(".birdtracks-display-strand").evaluate_all("nodes => nodes.map(n => n.getAttribute('d'))")
    drawing = {key: deepcopy(accepted[key])
               for key in ("positions", "free_levels", "boundary_orders", "line_colors")}
    for node in accepted["graph"]["nodes"]:
        if node["kind"] == "permutation":
            drawing["positions"][str(node["index"])]["x"] = 30
    page.evaluate("""drawing => {
      const state=model.get('editor_state');
      model.set('editor_request',{request_id:'hidden-placement',action:'presentation',
        term_id:state.term_id,base_revision:state.revision,presentation:drawing});
      model.save_changes();
    }""", drawing)
    page.wait_for_function("model.get('editor_feedback').request_id === 'hidden-placement'")
    assert "error" not in child.editor_feedback
    assert right() == pytest.approx(geometry["right_boundary"])
    assert page.locator(".birdtracks-display-strand").evaluate_all("nodes => nodes.map(n => n.getAttribute('d'))") == paths
    visible = [n for n in accepted["graph"]["nodes"] if n["kind"] != "permutation"]
    if visible:
        index = str(visible[-1]["index"])
        drawing["positions"][index]["x"] = 8
        page.evaluate("""drawing => {
          const state=model.get('editor_state');
          model.set('editor_request',{request_id:'visible-placement',action:'presentation',
            term_id:state.term_id,base_revision:state.revision,presentation:drawing});
          model.save_changes();
        }""", drawing)
        page.wait_for_function("model.get('editor_feedback').request_id === 'visible-placement'")
        assert "error" not in child.editor_feedback
        assert right() == pytest.approx(8 + geometry["node_width"] / 2 + geometry["step"] / 2)
    page.evaluate("remount()")
    expected_right = (8 + geometry["node_width"] / 2 + geometry["step"] / 2
                      if visible else geometry["right_boundary"])
    assert right() == pytest.approx(expected_right)
    assert child.editor_state["positions"] == drawing["positions"]
    assert child.editor_state["graph"]["display"] == accepted["graph"]["display"]
    assert canvas.current_projector_sum == value


def test_real_gesture_python_sign_undo_redo_save_and_reload(connected_canvas):
    page, canvas, child, requests, p = connected_canvas
    initial = deepcopy(child.editor_state)
    drag(page, "input", 1, 2)
    page.wait_for_function("model.get('editor_state').revision === 1")
    assert requests[-1]["action"] == "reorder"
    assert requests[-1]["changes"] == {initial["node_ids"][0]: {"input": [2, 1, 3], "output": [1, 2, 3]}}
    assert child.editor_state["display"]["sign"] == ""
    assert page.locator('.birdtracks-term-sign').count() == 0
    assert page.locator('.birdtracks-coefficient-minus').count() == 0
    assert canvas.current_projector_sum.collapse() == p.collapse()
    accepted = deepcopy(child.editor_state)
    page.keyboard.press('Control+z')
    page.wait_for_function("model.get('editor_state').revision === 2")
    assert child.editor_state["port_orders"] == initial["port_orders"]
    assert page.locator('.birdtracks-term-sign').count() == 1
    page.get_by_role('button', name='Redo last edit', exact=True).click()
    page.wait_for_function("model.get('editor_state').revision === 3")
    assert child.editor_state["port_orders"] == accepted["port_orders"]
    page.evaluate("model.set('save_command',1)")
    page.wait_for_function("model.get('saved_revision') >= 1")
    from birdtracks.projectors.canvas_session import ProjectorCanvasSession
    reopened = ProjectorCanvasSession.load(canvas.session.path).open(detangler=False)
    restored = reopened._term_editors[0]
    assert restored.editor_state["node_ids"] == accepted["node_ids"]
    assert restored.editor_state["strand_ids"] == accepted["strand_ids"]
    assert restored.editor_state["port_orders"] == accepted["port_orders"]
    assert restored.editor_state["positions"] == accepted["positions"]
    assert reopened.current_projector_sum.collapse() == p.collapse()
    page.screenshot(path='/tmp/birdtracks-port-editor-gesture.png')


@pytest.mark.parametrize("side", ["input", "output"])
@pytest.mark.parametrize("finish", ["commit", "cancel", "reject"])
@pytest.mark.parametrize("prior_swap", [False, True])
def test_drag_sign_preview_is_local_and_resolves_once(connected_canvas, side, finish, prior_swap):
    page, canvas, child, requests, p = connected_canvas
    if prior_swap:
        drag(page, "output" if side == "input" else "input", 1, 2)
        page.wait_for_function("model.get('editor_state').revision === 1")
        requests.clear()
    accepted = deepcopy(child.editor_state)
    configured = deepcopy(child.configuration.state())
    value = canvas.current_projector_sum
    points = [page.locator(f'[aria-label^="{side}:0:{label};"]').bounding_box()
              for label in (1, 2, 3)]
    if finish == "commit":
        page.evaluate("""() => {
          const send=window.pythonEditorCommand;
          window.pythonEditorCommand=async request=>{
            const reply=await send(request);
            await new Promise(resolve=>window.releasePreviewAck=resolve);
            return reply;
          };
        }""")
    elif finish == "reject":
        page.evaluate("""() => {
          const send=window.pythonEditorCommand;
          window.pythonEditorCommand=request=>send({...request,base_revision:-1});
        }""")
    page.mouse.move(points[0]['x'] + points[0]['width']/2,
                    points[0]['y'] + points[0]['height']/2)
    page.mouse.down()
    for slot, sign_count in [(1, 0), (2, 1), (0, 1), (1, 0)]:
        if prior_swap:
            sign_count = 1 - sign_count
        point = points[slot]
        page.mouse.move(point['x'] + point['width']/2,
                        point['y'] + point['height']/2, steps=5)
        assert page.locator('.birdtracks-term-sign').count() == sign_count
        assert page.locator('.birdtracks-coefficient-minus').count() == 0
        assert requests == []
        assert child.editor_state == accepted
        assert child.configuration.state() == configured
        assert canvas.current_projector_sum == value
        assert page.evaluate("model.get('editor_state')") == accepted
        assert page.evaluate("model.get('port_orders')") == accepted['port_orders']
    if finish == "cancel":
        page.evaluate("document.dispatchEvent(new PointerEvent('pointercancel'))")
    page.mouse.up()
    if finish == "commit":
        page.wait_for_function("typeof window.releasePreviewAck === 'function'")
        assert page.locator('.birdtracks-term-sign').count() == (1 if prior_swap else 0)
        assert page.evaluate("model.get('editor_state').revision") == accepted['revision']
        page.evaluate("releasePreviewAck()")
        page.wait_for_function("revision => model.get('editor_state').revision === revision", arg=accepted['revision'] + 1)
        assert child.editor_state['display']['sign'] == ('-' if prior_swap else '')
        assert page.locator('.birdtracks-term-sign').count() == (1 if prior_swap else 0)
        assert len(requests) == 1
        assert child.editor_state['can_undo']
    else:
        if finish == "reject":
            page.wait_for_function("Boolean(model.get('editor_feedback').error)")
        assert page.locator('.birdtracks-term-sign').count() == (0 if prior_swap else 1)
        assert child.editor_state == accepted
        assert child.configuration.state() == configured
        assert len(requests) == (1 if finish == "reject" else 0)
    assert canvas.current_projector_sum.collapse() == p.collapse()


def test_output_even_reorder_and_save_queued_behind_python(connected_canvas):
    page, canvas, child, requests, p = connected_canvas
    drag(page, 'output', 1, 3)
    # Save is requested before the asynchronous Python response is installed.
    page.evaluate("model.set('save_command',1)")
    page.wait_for_function("model.get('saved_revision') >= 1")
    assert [r["action"] for r in requests] == ['reorder', 'save']
    assert child.editor_state["port_orders"]["0"]["output"] == [2, 3, 1]
    assert child.editor_state["display"]["sign"] == '-'
    assert canvas.current_projector_sum.collapse() == p.collapse()


def test_rejected_and_delayed_commands_do_not_replace_the_drawing(connected_canvas):
    page, _canvas, child, _requests, _p = connected_canvas
    old = deepcopy(child.editor_state)
    drag(page, 'output', 1, 2)
    page.wait_for_function("model.get('editor_state').revision === 1")
    accepted = deepcopy(child.editor_state)
    page.evaluate("old => model.set('editor_state',old)", old)
    assert float(page.locator('[aria-label^="output:0:2;"]').get_attribute('cy')) < float(page.locator('[aria-label^="output:0:1;"]').get_attribute('cy'))
    child.editor_request = {"request_id": "stale", "action": "undo", "term_id": old["term_id"], "base_revision": 0}
    assert 'stale' in child.editor_feedback['error']
    assert child.editor_state == accepted


def test_manual_drawing_and_cancelled_gesture_survive_reorder(connected_canvas):
    page, _canvas, child, requests, _p = connected_canvas
    drawing = {key: deepcopy(child.editor_state[key])
               for key in ('positions', 'free_levels', 'boundary_orders', 'line_colors')}
    drawing['positions']['0']['x'] += 1.25
    drawing['positions']['0']['y'] += 0.2
    page.evaluate("""drawing => {
      const state=model.get('editor_state');
      model.set('editor_request',{request_id:'manual-placement',action:'presentation',
        term_id:state.term_id,base_revision:state.revision,presentation:drawing});
      model.save_changes();
    }""",drawing)
    page.wait_for_function("model.get('editor_state').revision === 1")
    rectangle = page.locator('.birdtracks-antisymmetriser')
    position = [rectangle.get_attribute('x'), rectangle.get_attribute('y')]
    drag(page,'input',1,2)
    page.wait_for_function("model.get('editor_state').revision === 2")
    assert [rectangle.get_attribute('x'),rectangle.get_attribute('y')] == position
    assert child.editor_state['positions'] == drawing['positions']
    assert child.editor_state['free_levels'] == drawing['free_levels']
    a=page.locator('[aria-label^="output:0:1;"]').bounding_box()
    b=page.locator('[aria-label^="output:0:2;"]').bounding_box()
    before=deepcopy(child.editor_state)
    count=len(requests)
    page.mouse.move(a['x']+a['width']/2,a['y']+a['height']/2)
    page.mouse.down()
    page.mouse.move(b['x']+b['width']/2,b['y']+b['height']/2,steps=5)
    page.evaluate("document.dispatchEvent(new PointerEvent('pointercancel'))")
    page.mouse.up()
    assert child.editor_state == before
    assert len(requests) == count


def test_same_model_remount_does_not_reuse_successful_request_ids(connected_canvas):
    page, canvas, child, requests, p = connected_canvas
    drag(page,'input',1,2)
    page.wait_for_function("model.get('editor_state').revision === 1")
    first_request=requests[-1]['request_id']
    page.evaluate('remount()')
    drag(page,'output',1,2)
    page.wait_for_function("model.get('editor_state').revision === 2")
    assert requests[-1]['request_id'] != first_request
    assert child.editor_state['display']['sign'] == '-'
    assert canvas.current_projector_sum.collapse() == p.collapse()


@pytest.mark.parametrize('feedback_before_remount', [False, True])
def test_result_view_remount_keeps_save_queued_behind_reorder(connected_canvas, feedback_before_remount):
    page, canvas, child, requests, p = connected_canvas
    page.evaluate("""() => {
      const send=window.pythonEditorCommand;
      window.pythonEditorCommand=async request=>{
        const reply=await send(request);
        if(request.action==='reorder') await new Promise(resolve=>window.releaseReorder=resolve);
        return reply;
      };
    }""")
    drag(page, "input", 1, 2)
    page.wait_for_function("typeof window.releaseReorder === 'function'")
    if feedback_before_remount:
        page.evaluate("model.set('save_command', 1); cleanup(); releaseReorder()")
        page.wait_for_function("model.get('editor_state').revision === 1")
        page.evaluate('remount()')
    else:
        page.evaluate("model.set('save_command', 1); remount(); releaseReorder()")
    page.wait_for_function("model.get('saved_revision') >= 1", timeout=3000)
    assert [r['action'] for r in requests] == ['reorder', 'save']
    assert child.editor_state['revision'] == 1
    assert canvas.current_projector_sum.collapse() == p.collapse()
