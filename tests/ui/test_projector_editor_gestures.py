"""Real shipped canvas gestures connected to the Python command adapter."""

import base64
from copy import deepcopy
from fractions import Fraction
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
STATIC = Path(__file__).parents[2] / "src/birdtracks/projectors/static"


@pytest.fixture
def connected_canvas(tmp_path):
    from birdtracks import Antisymmetriser, Projector, ProjectorSum, Symmetriser
    from birdtracks.projectors.widget import projector_sum_widget

    p = Projector([Antisymmetriser((1, 2, 3)), Symmetriser((3, 4))], coefficient=Fraction(-2, 3))
    canvas = projector_sum_widget(ProjectorSum((p,)), shared_editor=True,
                                  session=tmp_path / "gestures", detangler=False, debug=True)
    child = canvas._term_editors[0]
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
            child.editor_request = request
            return {key: value for key, value in child.get_state().items()
                    if not key.startswith("_") and key not in {"editor_request", "save_command", "local_undo_command"}}

        page.expose_binding("pythonEditorCommand", command)
        page.set_content('<div class="birdtracks-projector-sum"><div id="canvas"></div></div>')
        page.add_style_tag(content=(STATIC / "projector-widget.css").read_text())
        state = {key: value for key, value in child.get_state().items() if not key.startswith("_")}
        source = base64.b64encode((STATIC / "projector-widget.js").read_bytes()).decode()
        page.evaluate("""async ({state, source}) => {
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
              const request = values.editor_request;
              if (!request?.request_id || this.lastSent === request.request_id) return;
              this.lastSent = request.request_id;
              window.pythonEditorCommand(structuredClone(request)).then(reply => {
                for (const [key,value] of Object.entries(reply))
                  if (!['editor_state','editor_feedback'].includes(key)) model.set(key,value);
                model.set('editor_state',reply.editor_state);
                model.set('editor_feedback',reply.editor_feedback);
              });
            },
          };
          const module = await import('data:text/javascript;base64,'+source);
          window.cleanup = module.default.render({model,el:document.querySelector('#canvas')});
          window.remount = () => {
            cleanup(); document.querySelector('#canvas').replaceChildren();
            window.cleanup=module.default.render({model,el:document.querySelector('#canvas')});
          };
        }""", {"state": state, "source": source})
        yield page, canvas, child, requests, p
        page.evaluate("cleanup()")
        browser.close()
        assert not errors


def drag(page, side, source_label, destination_label):
    source = page.locator(f'[aria-label^="{side}:0:{source_label};"]')
    target = page.locator(f'[aria-label^="{side}:0:{destination_label};"]')
    a, b = source.bounding_box(), target.bounding_box()
    page.mouse.move(a["x"] + a["width"] / 2, a["y"] + a["height"] / 2)
    page.mouse.down()
    page.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, steps=5)
    page.mouse.up()


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
    page.get_by_role('button', name='Redo port reorder', exact=True).click()
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
