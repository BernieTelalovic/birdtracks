"""Browser checks for whiteboard/projector integration (optional Playwright)."""

import base64
from pathlib import Path

import pytest


playwright = pytest.importorskip("playwright.sync_api")
STATIC = Path(__file__).parents[2] / "src/birdtracks/projectors/static"


@pytest.mark.parametrize("prefactor", ["", "2"])
@pytest.mark.parametrize("saved_labels", [False, True])
def test_painted_line_survives_save_port_renumbering(page, prefactor, saved_labels):
    from birdtracks import Projector, Symmetriser, whiteboard
    from birdtracks.projectors.widget import projector_widget

    editor = projector_widget(Projector([Symmetriser((10, 11))]), embedded=True)
    source = base64.b64encode((STATIC / "projector-widget.js").read_bytes()).decode()
    state = {key: value for key, value in editor.get_state().items()
             if not key.startswith("_")}
    page.evaluate("""async ({state, source}) => {
      cleanup();
      for (const [key, value] of Object.entries(state)) childModel.set(key, value);
      window.projectorModule = await import('data:text/javascript;base64,' + source);
      document.querySelector('#widget').innerHTML =
        '<section class="birdtracks-whiteboard-section"><div id="canvas"></div></section>';
      document.querySelector('section')._birdtracksPaintbrush = {
        active: true, color: '#ff0000',
      };
      window.cleanup = projectorModule.default.render({model: childModel,
        el: document.querySelector('#canvas')});
    }""", {"state": state, "source": source})
    page.locator(
        '[data-line-key="right-anchor:0->input:0:10"].birdtracks-line-hit'
    ).dispatch_event('click', {"detail": 1})
    page.wait_for_timeout(350)
    page.evaluate("childModel.set('save_command', 1)")
    snapshot = page.evaluate("childModel.get('save_snapshot')")
    assert snapshot['line_colors'] == {'right-anchor:0->input:0:1': '#ff0000'}
    if saved_labels:
        # Existing diagrams may retain arbitrary labels before the expansion
        # gesture saves and renumbers them.
        snapshot.update(graph=editor.graph, port_orders=editor.port_orders,
                        boundary_orders=editor.boundary_orders,
                        line_colors={'right-anchor:0->input:0:10': '#ff0000'})

    document = whiteboard(debug=True)
    document.blocks = [{"id": "text-1", "source": prefactor + r"\birdtracks"}]
    document.simplify_request = {"line_id": "text-1", "action": "evaluate",
        "revision": 1, "snapshots": {"text-1:projector:0": snapshot}}
    assert document.blocks[0]['line_colors'] == snapshot['line_colors']
    child = document.backend_projectors[-1]
    child_state = {key: value for key, value in child.get_state().items()
                   if not key.startswith('_')}
    page.evaluate("""state => {
      cleanup();
      document.querySelector('#canvas').replaceChildren();
      for (const [key, value] of Object.entries(state)) childModel.set(key, value);
      window.cleanup = projectorModule.default.render({model: childModel,
        el: document.querySelector('#canvas')});
    }""", child_state)
    label = 10 if saved_labels else 1
    assert page.locator(f'[data-line-key="right-anchor:0->input:0:{label}"].birdtracks-line').evaluate(
        'el => el.style.stroke') == 'rgb(255, 0, 0)'
    assert page.locator(f'[data-line-key="output:0:{label}->left-anchor:0"].birdtracks-line').evaluate(
        'el => el.style.stroke') == ''
    page.evaluate("childModel.set('active_line', true)")
    page.locator('.birdtracks-symmetriser').first.dblclick()
    snapshot = page.evaluate("childModel.get('save_snapshot')")
    request = page.evaluate("childModel.get('expand_node_request')")
    child.graph = snapshot['graph']
    child.port_orders = snapshot['port_orders']
    child.boundary_orders = snapshot['boundary_orders']
    child.save_snapshot = snapshot
    child.expand_node_request = request
    result = document.blocks[-1]
    assert result['calculation_step'] == 2
    for key, descendant in zip(document.backend_projector_ids, document.backend_projectors):
        if not key.startswith(result['id'] + ':'):
            continue
        page.evaluate("""state => {
          cleanup();
          document.querySelector('#canvas').replaceChildren();
          for (const [key, value] of Object.entries(state)) childModel.set(key, value);
          window.cleanup = projectorModule.default.render({model: childModel,
            el: document.querySelector('#canvas')});
        }""", {key: value for key, value in descendant.get_state().items()
               if not key.startswith('_')})
        assert page.locator('.birdtracks-line[data-line-key^="right-anchor:0->"]').evaluate(
            'el => el.style.stroke') == 'rgb(255, 0, 0)'


def test_evaluate_display_keeps_disjoint_rightmost_operators_in_one_column(page):
    from birdtracks import (
        Antisymmetriser,
        Permutation,
        PermutationNode,
        Projector,
        Symmetriser,
    )
    from birdtracks.projectors.widget import projector_widget

    projector = Projector([
        Symmetriser((1, 2)),
        Antisymmetriser((3, 4)),
        PermutationNode(Permutation.identity(), support=(2,)),
        PermutationNode(Permutation.from_cycle(2, 3), support=(2, 3, 4)),
        Antisymmetriser((3, 4)),
        PermutationNode(Permutation.identity(), support=(2,)),
        Symmetriser((1, 2)),
    ])
    editor = projector_widget(projector, embedded=True)
    state = {
        key: value for key, value in editor.get_state().items()
        if not key.startswith("_")
    }
    source = base64.b64encode((STATIC / "projector-widget.js").read_bytes()).decode()
    page.add_style_tag(content=(STATIC / "projector-widget.css").read_text())
    page.evaluate(
        """async ({state, source}) => {
          cleanup();
          for (const [key, value] of Object.entries(state)) childModel.set(key, value);
          childModel.model_id = 'compiled-display-child';
          const projector = await import('data:text/javascript;base64,' + source);
          document.querySelector('#widget').innerHTML = '<div id="canvas"></div>';
          window.cleanup = projector.default.render({
            model: childModel, el: document.querySelector('#canvas'),
          });
        }""",
        {"state": state, "source": source},
    )

    positions = page.locator(".birdtracks-node").evaluate_all(
        """nodes => Object.fromEntries(nodes.map(node => [
          node.dataset.node,
          Number(node.querySelector('rect').getAttribute('x')),
        ]))"""
    )
    # Hidden permutation nodes stay in the exact graph, while its compiled
    # display plan places the visible exact nodes 4 and 6 in one column.
    assert positions["4"] == positions["6"]


@pytest.fixture
def page():
    with playwright.sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch()
        except playwright.Error as exc:
            pytest.skip(f"Chromium unavailable: {exc}")
        page = browser.new_page(viewport={"width": 1400, "height": 800})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route('http://whiteboard.test/', lambda route: route.fulfill(
            content_type='text/html', body='<div id="widget"></div>'))
        page.goto('http://whiteboard.test/')
        page.add_style_tag(content=(STATIC / "whiteboard-widget.css").read_text())
        source = base64.b64encode((STATIC / "whiteboard-widget.js").read_bytes()).decode()
        page.evaluate(
            """async source => {
              window.module = await import('data:text/javascript;base64,' + source);
              const values = {
                widget_role: 'whiteboard', title: '',
                blocks: [{id: 'text-1', source: '123.45\\\\birdtracks'}],
                embedded_projector_ids: ['text-1:projector:0'],
                embedded_projectors: ['child-1'],
              };
              const listeners = new Map();
              window.model = {
                get: name => values[name],
                set(name, value) {
                  values[name] = value;
                  for (const fn of listeners.get('change:' + name) || []) {
                    fn(this, value, {});
                  }
                },
                on(names, fn) {
                  for (const name of names.split(' ')) {
                    if (!listeners.has(name)) listeners.set(name, new Set());
                    listeners.get(name).add(fn);
                  }
                },
                off(names, fn) {
                  for (const name of names.split(' ')) listeners.get(name)?.delete(fn);
                },
                save_changes() {},
              };
              const childValues = {
                graph: {nodes: [{index: 0, kind: 'antisymmetriser',
                  labels: [1, 2], input_labels: [1, 2], output_labels: [1, 2]}]},
                port_orders: {'0': {input: [1, 2], output: [1, 2]}},
                mode: 'evaluate',
              };
              const childListeners = new Map();
              window.childModel = {
                get: name => childValues[name],
                set(name, value) {
                  childValues[name] = value;
                  for (const fn of childListeners.get('change:' + name) || []) fn({new: value});
                },
                on(names, fn) {
                  for (const name of names.split(' ')) {
                    if (!childListeners.has(name)) childListeners.set(name, new Set());
                    childListeners.get(name).add(fn);
                  }
                },
                off(names, fn) {
                  for (const name of names.split(' ')) childListeners.get(name)?.delete(fn);
                },
                save_changes() {},
              };
              window.cleanup = window.module.default.render({
                model, el: document.querySelector('#widget'), signal: null,
                host: {
                  getModel: async () => childModel,
                  getWidget: async () => ({render: async ({el}) => { el.dataset.fake = 'true'; }}),
                },
              });
            }""",
            source,
        )
        page.wait_for_timeout(50)
        assert page.evaluate("() => childModel.get('prefactor_owned')") is True
        yield page
        page.evaluate("window.cleanup()")
        browser.close()
        assert not errors


def test_embedded_projector_flips_numeric_prefactor_with_orientation(page):
    page.evaluate(
        """() => childModel.set('port_orders', {
          '0': {input: [2, 1], output: [1, 2]}
        })"""
    )
    assert page.evaluate("() => model.get('blocks')[0].source") == r"-123.45\birdtracks"

    page.evaluate(
        """() => childModel.set('port_orders', {
          '0': {input: [1, 2], output: [1, 2]}
        })"""
    )
    assert page.evaluate("() => model.get('blocks')[0].source") == r"123.45\birdtracks"


def test_embedded_projector_inserts_sign_without_numeric_prefactor(page):
    page.evaluate("""() => model.set('blocks', [{
      id: 'text-1', source: '\\\\birdtracks'
    }])""")
    page.wait_for_timeout(50)

    page.evaluate(
        """() => childModel.set('port_orders', {
          '0': {input: [2, 1], output: [1, 2]}
        })"""
    )
    assert page.evaluate("() => model.get('blocks')[0].source") == r"-\birdtracks"

    page.evaluate(
        """() => childModel.set('port_orders', {
          '0': {input: [1, 2], output: [1, 2]}
        })"""
    )
    assert page.evaluate("() => model.get('blocks')[0].source") == r"\birdtracks"


def test_lower_row_updates_keep_upper_projector_mounted(page):
    page.evaluate("""() => {
      window.upperCanvas = document.querySelector('.birdtracks-whiteboard-embedded-projector');
      window.upperRow = upperCanvas.closest('.birdtracks-whiteboard-block');
      upperCanvas.dataset.draggedPosition = '3';
      model.set('blocks', [...model.get('blocks'), {id: 'lower', source: 'x'}]);
      // Widget-list notifications can arrive separately from the block update.
      model.set('embedded_projectors', ['child-1']);
      model.set('embedded_projector_ids', ['text-1:projector:0']);
    }""")
    page.locator('[data-block-id="lower"] textarea').fill('xyz')
    page.locator('.birdtracks-whiteboard-title').click()
    page.evaluate("""() => {
      const blocks = structuredClone(model.get('blocks'));
      blocks[0].projector_snapshots = {'0': {revision: 42}};
      model.set('blocks', blocks);
    }""")
    assert page.evaluate("""() => upperRow.isConnected && upperCanvas.isConnected
      && upperCanvas === document.querySelector('.birdtracks-whiteboard-embedded-projector')
      && upperCanvas.dataset.draggedPosition === '3'""")


def test_moved_free_line_survives_click_away_and_lower_row_insert(page):
    from birdtracks import Antisymmetriser, Permutation, PermutationNode, Projector
    from birdtracks.projectors.widget import projector_widget

    child = projector_widget(Projector([
        Antisymmetriser((1, 2)),
        PermutationNode(Permutation.identity(), support=(3,)),
    ]), embedded=True)
    state = {key: value for key, value in child.get_state().items()
             if not key.startswith('_')}
    source = base64.b64encode((STATIC / 'projector-widget.js').read_bytes()).decode()
    page.add_style_tag(content=(STATIC / 'projector-widget.css').read_text())
    page.evaluate("""async ({state, source}) => {
      cleanup();
      for (const [key, value] of Object.entries(state)) childModel.set(key, value);
      childModel.model_id = 'real-child';
      const projector = await import('data:text/javascript;base64,' + source);
      model.set('blocks', [{id: 'upper', source: 'R', read_only: true,
        calculation_group: 'g', backend_terms: [{id: 'upper:backend:0', start: 0, end: 1}]}]);
      model.set('embedded_projector_ids', []);
      model.set('embedded_projectors', []);
      model.set('backend_projector_ids', ['upper:backend:0']);
      model.set('backend_projectors', ['child-1']);
      window.mounts = 0;
      window.cleanup = module.default.render({model, el: document.querySelector('#widget'),
        host: {getModel: async () => childModel,
          getWidget: async () => ({render: ({el}) => {
            mounts++;
            return projector.default.render({model: childModel, el});
          }})}});
    }""", {'state': state, 'source': source})
    handle = page.locator('.birdtracks-route-handle').first
    playwright.expect(handle).to_be_attached()
    before = page.evaluate("structuredClone(childModel.get('free_levels'))")
    box = handle.bounding_box()
    operator = page.locator('.birdtracks-antisymmetriser').first.bounding_box()
    page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    page.mouse.down()
    page.mouse.move(box['x'] + box['width'] / 2, operator['y'], steps=5)
    page.mouse.up()
    moved = page.evaluate("structuredClone(childModel.get('free_levels'))")
    assert moved != before
    page.locator('.birdtracks-whiteboard-title').click()
    page.evaluate("""() => model.set('blocks', [...model.get('blocks'),
      {id: 'lower', source: 'x'}])""")
    page.locator('[data-block-id="lower"] textarea').fill('xy')
    page.locator('.birdtracks-whiteboard-title').click()
    assert page.evaluate('mounts') == 1
    assert page.evaluate("childModel.get('free_levels')") == moved


def test_embedded_projector_recovers_orientation_change_while_unmounted(page):
    page.evaluate("""() => {
      document.querySelector('.birdtracks-whiteboard-rendered')
        ._birdtracksCleanupBlock();
      childModel.set('port_orders', {
        '0': {input: [2, 1], output: [1, 2]}
      });
      model.set('blocks', structuredClone(model.get('blocks')));
    }""")
    page.wait_for_timeout(50)

    assert page.evaluate("() => model.get('blocks')[0].source") == r"-123.45\birdtracks"


def test_prefactor_flip_combines_binary_and_unary_signs(page):
    cases = {
        r"= \frac{1}{2}R - \frac{1}{3}R": r"= \frac{1}{2}R + \frac{1}{3}R",
        r"= \frac{1}{2}R - -\frac{1}{3}R": r"= \frac{1}{2}R - \frac{1}{3}R",
        r"= \frac{1}{2}R + -\frac{1}{3}R": r"= \frac{1}{2}R + \frac{1}{3}R",
    }
    for source, expected in cases.items():
        assert page.evaluate(
            "source => window.module.flipNumericPrefactor(source, source.length - 1)",
            source,
        ) == expected


def test_backend_projector_recovers_shifted_placeholder_and_updates_sign(page):
    source = r"= -\frac{9}{16}R"
    page.evaluate(
        """source => {
          model.set('blocks', [{
            id: 'result', source, read_only: true, calculation_step: 1,
            backend_terms: [{
              id: 'result:backend:0', start: 14, end: 15,
              prefactor_owned: true,
            }],
          }]);
          model.set('backend_projector_ids', ['result:backend:0']);
          model.set('backend_projectors', ['child-1']);
        }""",
        source,
    )

    anchor = page.locator('[data-projector-id="result:backend:0"]')
    assert anchor.get_attribute('data-fake') == 'true'
    assert page.locator('[data-block-id="result"] .birdtracks-whiteboard-rendered').text_content() != source

    page.evaluate(
        """() => childModel.set('port_orders', {
          '0': {input: [2, 1], output: [1, 2]}
        })"""
    )
    assert page.evaluate("() => model.get('blocks')[0].source") == r"= \frac{9}{16}R"

    page.evaluate(
        """() => childModel.set('port_orders', {
          '0': {input: [1, 2], output: [1, 2]}
        })"""
    )
    assert page.evaluate("() => model.get('blocks')[0].source") == source


def test_whiteboard_paintbrush_palette_keeps_five_recent_colors(page):
    brush = page.get_by_role("button", name="Paintbrush color")
    assert brush.get_attribute("aria-pressed") == "true"
    panel = page.locator(".birdtracks-whiteboard-color-panel")
    playwright.expect(panel).to_be_hidden()
    brush.click()
    playwright.expect(panel).to_be_visible()
    color_input = panel.locator('input[type="color"]')
    assert color_input.get_attribute("aria-label") == "Choose color with a color wheel"
    assert color_input.evaluate("input => getComputedStyle(input).pointerEvents") == "auto"

    for value in range(1, 7):
        page.get_by_role("spinbutton", name="R color value").fill(str(value))
        page.get_by_role("spinbutton", name="G color value").fill("0")
        page.get_by_role("spinbutton", name="B color value").fill("0")
        page.keyboard.press("Tab")

    assert page.locator(".birdtracks-whiteboard-recent-color").count() == 5
    assert page.evaluate("model.get('recent_colors')") == [
        "#060000", "#050000", "#040000", "#030000", "#020000",
    ]
    assert brush.get_attribute("aria-pressed") == "true"
    page.locator(".birdtracks-whiteboard-title").click()
    playwright.expect(panel).to_be_hidden()
    assert brush.get_attribute("aria-pressed") == "true"
    brush.click()
    playwright.expect(panel).to_be_visible()
    assert brush.get_attribute("aria-pressed") == "true"


def test_whiteboard_toolbar_remains_visible_while_scrolling(page):
    heading = page.locator(".birdtracks-whiteboard-toolbar")
    page.locator(".birdtracks-whiteboard-blocks").evaluate(
        "blocks => { blocks.style.minHeight = '2000px'; }"
    )
    page.evaluate("window.scrollTo(0, 600)")
    page.wait_for_timeout(50)

    assert abs(heading.bounding_box()["y"]) <= 2


def test_wide_rendered_expression_scrolls_horizontally(page):
    rendered = page.locator(".birdtracks-whiteboard-rendered").first
    rendered.evaluate("""element => {
      const wide = document.createElement('span');
      wide.style.display = 'block';
      wide.style.width = '2000px';
      wide.textContent = 'wide expression';
      element.replaceChildren(wide);
    }""")

    assert rendered.evaluate(
        "element => getComputedStyle(element).overflowX"
    ) == "auto"
    assert rendered.evaluate("element => element.scrollWidth > element.clientWidth")


def test_shift_backspace_preserves_viewport_while_removing_result(page):
    leading = [
        {"id": f"text-{index}", "source": f"line {index}"}
        for index in range(1, 31)
    ]
    original = {
        "id": "source-line", "source": "expression", "read_only": True,
        "calculation_group": "calculation-1",
    }
    result = {
        "id": "result-line", "source": "= result", "read_only": True,
        "calculation_group": "calculation-1", "calculation_step": 1,
    }
    page.evaluate("blocks => model.set('blocks', blocks)", leading + [original, result])
    rendered_result = page.locator('[data-block-id="result-line"] .birdtracks-whiteboard-rendered')
    rendered_result.focus()
    scroll_y = page.evaluate("window.scrollY")
    leading_y = page.locator(
        '.birdtracks-whiteboard-block[data-block-id="text-20"]'
    ).bounding_box()["y"]
    page.keyboard.press("Shift+Backspace")
    page.evaluate(
        "blocks => model.set('blocks', blocks)",
        leading + [{"id": "source-line", "source": "expression"}],
    )
    page.wait_for_timeout(50)

    assert page.evaluate("window.scrollY") == pytest.approx(scroll_y, abs=1)
    assert page.locator(
        '.birdtracks-whiteboard-block[data-block-id="text-20"]'
    ).bounding_box()["y"] == pytest.approx(leading_y, abs=1)


def test_shift_enter_only_scrolls_when_result_needs_more_room(page):
    leading = [
        {"id": f"text-{index}", "source": f"line {index}"}
        for index in range(1, 21)
    ]
    source = {"id": "source-line", "source": "expression"}
    page.evaluate("blocks => model.set('blocks', blocks)", leading + [source])
    editor = page.locator('[data-block-id="source-line"] textarea')
    editor.scroll_into_view_if_needed()
    page.evaluate("window.scrollBy(0, -180)")
    editor.focus()
    scroll_y = page.evaluate("window.scrollY")
    source_y = page.locator(
        '.birdtracks-whiteboard-block[data-block-id="source-line"]'
    ).bounding_box()["y"]

    page.keyboard.press("Shift+Enter")
    page.evaluate(
        "blocks => model.set('blocks', blocks)",
        leading + [
            {**source, "read_only": True, "calculation_group": "calculation-1"},
            {"id": "result-line", "source": "= result", "read_only": True,
             "calculation_group": "calculation-1", "calculation_step": 1},
        ],
    )
    page.wait_for_timeout(50)

    assert page.evaluate("window.scrollY") == pytest.approx(scroll_y, abs=1)
    assert page.locator(
        '.birdtracks-whiteboard-block[data-block-id="source-line"]'
    ).bounding_box()["y"] == pytest.approx(source_y, abs=1)


def test_shift_enter_scrolls_new_result_minimally_into_view(page):
    leading = [
        {"id": f"text-{index}", "source": f"line {index}"}
        for index in range(1, 31)
    ]
    source = {"id": "source-line", "source": "expression"}
    page.evaluate("blocks => model.set('blocks', blocks)", leading + [source])
    editor = page.locator('[data-block-id="source-line"] textarea')
    editor.evaluate("el => el.scrollIntoView({block: 'end'})")
    editor.focus()
    scroll_y = page.evaluate("window.scrollY")

    page.keyboard.press("Shift+Enter")
    page.evaluate(
        "blocks => model.set('blocks', blocks)",
        leading + [{**source, "read_only": True, "calculation_group": "calculation-1"}],
    )
    page.wait_for_timeout(20)
    assert page.evaluate("window.scrollY") == pytest.approx(scroll_y, abs=1)
    page.evaluate(
        "blocks => model.set('blocks', blocks)",
        leading + [
            {**source, "read_only": True, "calculation_group": "calculation-1"},
            {"id": "result-line", "source": "= result", "read_only": True,
             "calculation_group": "calculation-1", "calculation_step": 1},
        ],
    )
    page.wait_for_timeout(50)

    result = page.locator(
        '.birdtracks-whiteboard-block[data-block-id="result-line"]'
    )
    bounds = result.bounding_box()
    assert page.evaluate("window.scrollY") > scroll_y
    assert bounds["y"] + bounds["height"] == pytest.approx(792, abs=1)

def test_calculation_scrolls_the_nearest_scroll_container(page):
    page.locator("#widget").evaluate(
        "el => { el.style.height = '420px'; el.style.overflowY = 'auto'; }"
    )
    leading = [
        {"id": f"text-{index}", "source": f"line {index}"}
        for index in range(1, 31)
    ]
    original = {
        "id": "source-line", "source": "expression", "read_only": True,
        "calculation_group": "calculation-1",
    }
    result = {
        "id": "result-line", "source": "= result", "read_only": True,
        "calculation_group": "calculation-1", "calculation_step": 1,
    }
    page.evaluate("blocks => model.set('blocks', blocks)", leading + [original, result])
    scroller = page.locator("#widget")
    scroller.evaluate("el => { el.scrollTop = 500; }")

    page.locator('[data-block-id="result-line"] .birdtracks-whiteboard-rendered').focus()
    scroll_top = scroller.evaluate("el => el.scrollTop")
    page.keyboard.press("Shift+Backspace")
    page.evaluate(
        "blocks => model.set('blocks', blocks)",
        leading + [{"id": "source-line", "source": "expression"}],
    )
    page.wait_for_timeout(50)

    assert scroller.evaluate("el => el.scrollTop") == pytest.approx(scroll_top, abs=1)


def test_shift_enter_waits_for_a_newer_calculation_step(page):
    leading = [
        {"id": f"text-{index}", "source": f"line {index}"}
        for index in range(1, 31)
    ]
    current = {
        "id": "step-1", "source": "= current", "read_only": True,
        "calculation_group": "calculation-1", "calculation_step": 1,
    }
    page.evaluate("blocks => model.set('blocks', blocks)", leading + [current])
    rendered = page.locator('[data-block-id="step-1"] .birdtracks-whiteboard-rendered')
    rendered.focus()
    scroll_y = page.evaluate("window.scrollY")
    page.keyboard.press("Shift+Enter")

    page.evaluate("blocks => model.set('blocks', blocks)", leading + [current])
    page.wait_for_timeout(20)
    assert page.evaluate("window.scrollY") == pytest.approx(scroll_y, abs=1)

    page.evaluate(
        "blocks => model.set('blocks', blocks)",
        leading + [current, {
            "id": "step-2", "source": "= next", "read_only": True,
            "calculation_group": "calculation-1", "calculation_step": 2,
        }],
    )
    page.wait_for_timeout(50)
    result = page.locator(
        '.birdtracks-whiteboard-block[data-block-id="step-2"]'
    ).bounding_box()
    assert result["y"] + result["height"] <= 792


def test_workspace_renders_switchable_document_tabs_and_new_tab(page):
    page.evaluate("""async () => {
      cleanup();
      const makeModel = values => {
        const listeners = new Map();
        return {
          get: name => values[name],
          set(name, value) {
            values[name] = value;
            for (const fn of listeners.get('change:' + name) || []) fn({new: value});
          },
          on(names, fn) {
            for (const name of names.split(' ')) {
              if (!listeners.has(name)) listeners.set(name, new Set());
              listeners.get(name).add(fn);
            }
          },
          off(names, fn) {
            for (const name of names.split(' ')) listeners.get(name)?.delete(fn);
          },
          save_changes() {},
        };
      };
      window.workspaceDocuments = {
        'doc-1': makeModel({widget_role: 'whiteboard', title: 'One',
          blocks: [{id: 'text-1', source: 'first'}]}),
        'doc-2': makeModel({widget_role: 'whiteboard', title: 'Two',
          blocks: [{id: 'text-1', source: 'second'}]}),
      };
      window.workspaceModel = makeModel({widget_role: 'workspace',
        documents: ['doc-1', 'doc-2'], active_index: 0, new_document_request: 0});
      const host = {
        getModel: async reference => workspaceDocuments[reference],
      };
      window.cleanup = await module.default.render({model: workspaceModel,
        el: document.querySelector('#widget'), signal: null, host});
    }""")

    tabs = page.locator(".birdtracks-whiteboard-tab")
    assert tabs.count() == 3
    assert page.locator(".birdtracks-whiteboard-title").input_value() == "One"
    page.get_by_role("button", name="Two", exact=True).click()
    playwright.expect(page.locator(".birdtracks-whiteboard-title")).to_have_value("Two")
    assert page.evaluate("workspaceModel.get('active_index')") == 1
    page.locator("textarea").first.focus()
    page.keyboard.press("Shift+Enter")
    request = page.evaluate(
        "workspaceDocuments['doc-2'].get('simplify_request')"
    )
    assert request["line_id"] == "text-1"
    assert request["action"] == "evaluate"
    page.get_by_role("button", name="New whiteboard").click()
    assert page.evaluate("workspaceModel.get('new_document_request')") == 1
    page.get_by_role("button", name="Close Two").click()
    assert page.evaluate("workspaceModel.get('close_document_request')") == 1
    assert page.evaluate("workspaceModel.get('close_document_revision')") == 1


def test_whiteboard_header_controls_capture_state_and_share_one_row(page, tmp_path):
    heading = page.locator(".birdtracks-whiteboard-heading")
    brush = page.get_by_role("button", name="Paintbrush color")
    save = page.get_by_role("button", name="Save", exact=True)
    load = page.get_by_role("button", name="Load", exact=True)
    export = page.get_by_role("button", name="Export to LaTeX")
    title = page.get_by_role("textbox", name="Whiteboard session name")
    boxes = [item.bounding_box() for item in (brush, save, load, export, title)]
    centers = [box["y"] + box["height"] / 2 for box in boxes]
    assert max(centers) - min(centers) < 1
    assert heading.locator(":scope > .birdtracks-whiteboard-edit-bar > button").count() == 4
    assert title.bounding_box()["width"] < heading.bounding_box()["width"] / 2
    assert export.is_enabled()

    page.evaluate("""() => childModel.on('change:save_command', change => {
      childModel.set('save_snapshot', {
        revision: change.new, line_colors: childModel.get('line_colors') || {},
      });
    })""")
    page.evaluate("() => childModel.set('line_colors', {'saved-line': '#9141ac'})")
    save.click()
    assert page.evaluate("() => model.get('save_request')") == 1
    assert page.evaluate(
        "() => model.get('blocks')[0].projector_snapshots['0'].revision"
    ) == 1
    assert page.evaluate("() => model.get('blocks')[0].line_colors") == {
        "saved-line": "#9141ac",
    }
    export.click()
    dialog = page.get_by_role("dialog", name="LaTeX export options")
    playwright.expect(dialog).to_be_visible()
    page.get_by_label("Include preamble").check()
    page.get_by_label("Pad boxes and antiboxes to the term's N₀").check()
    page.get_by_label("Include equation line alignment").check()
    dialog.get_by_role("button", name="Export", exact=True).click()
    assert page.evaluate("() => model.get('export_request')") == 1
    assert page.evaluate("() => model.get('export_options')") == {
        "include_preamble": True,
        "include_colors": True,
        "pad_to_n0": True,
        "include_equation_alignment": True,
    }
    assert page.evaluate(
        "() => JSON.parse(localStorage.getItem('birdtracks.whiteboard.latex-export-options'))"
    ) == page.evaluate("() => model.get('export_options')")
    uploaded = tmp_path / "loaded.whiteboard"
    uploaded.write_text('{"version": 2}', encoding="utf-8")
    heading.locator('input[type="file"]').set_input_files(uploaded)
    page.wait_for_function("model.get('load_document_request')?.name === 'loaded.whiteboard'")


def test_export_options_follow_last_export_across_open_whiteboards(page):
    page.evaluate("""() => {
      const second = document.createElement('div');
      second.id = 'second-whiteboard';
      document.body.appendChild(second);
      const values = {
        widget_role: 'whiteboard', title: 'Second',
        blocks: [{id: 'second-line', source: ''}],
        embedded_projector_ids: [], embedded_projectors: [],
      };
      const listeners = new Map();
      window.secondModel = {
        get: name => values[name],
        set(name, value) {
          values[name] = value;
          for (const fn of listeners.get('change:' + name) || []) fn(this, value, {});
        },
        on(names, fn) {
          for (const name of names.split(' ')) {
            if (!listeners.has(name)) listeners.set(name, new Set());
            listeners.get(name).add(fn);
          }
        },
        off(names, fn) {
          for (const name of names.split(' ')) listeners.get(name)?.delete(fn);
        },
        save_changes() {},
      };
      window.cleanupSecond = module.default.render({
        model: secondModel, el: second, signal: null,
        host: {getModel: async () => childModel,
          getWidget: async () => ({render: async () => {}})},
      });
    }""")
    first = page.locator("#widget")
    second = page.locator("#second-whiteboard")

    first.get_by_role("button", name="Export to LaTeX").click()
    first.get_by_label("Include preamble").check()
    first.get_by_label("Include all colour labels").uncheck()
    first.get_by_label("Pad boxes and antiboxes to the term's N₀").check()
    first.get_by_role("dialog").get_by_role("button", name="Export", exact=True).click()

    second.get_by_role("button", name="Export to LaTeX").click()
    assert second.get_by_label("Include preamble").is_checked()
    assert not second.get_by_label("Include all colour labels").is_checked()
    assert second.get_by_label("Pad boxes and antiboxes to the term's N₀").is_checked()
    assert not second.get_by_label("Include equation line alignment").is_checked()
    second.get_by_label("Include preamble").uncheck()
    second.get_by_label("Include equation line alignment").check()
    second.get_by_role("dialog").get_by_role("button", name="Export", exact=True).click()

    first.get_by_role("button", name="Export to LaTeX").click()
    assert not first.get_by_label("Include preamble").is_checked()
    assert not first.get_by_label("Include all colour labels").is_checked()
    assert first.get_by_label("Pad boxes and antiboxes to the term's N₀").is_checked()
    assert first.get_by_label("Include equation line alignment").is_checked()
    page.evaluate("cleanupSecond()")


def test_whiteboard_math_source_disables_browser_spellcheck(page):
    assert page.locator(".birdtracks-whiteboard-source").first.evaluate(
        "editor => editor.spellcheck"
    ) is False


def test_embedded_pair_marker_mounts_an_inline_pair_anchor(page):
    page.evaluate(r"""() => {
      model.set('embedded_projector_ids', []);
      model.set('embedded_projectors', []);
      model.set('embedded_pair_ids', ['text-1:pair:0']);
      model.set('embedded_pairs', ['child-1']);
      model.set('blocks', [{id: 'text-1', source: '2_4\\pair'}]);
    }""")
    page.wait_for_timeout(20)
    assert page.locator(".birdtracks-whiteboard-embedded-pair").count() == 1
    assert page.locator(".birdtracks-whiteboard-embedded-pair").evaluate(
        "el => getComputedStyle(el).minHeight"
    ) == "0px"
    rendered = page.locator('[data-block-id="text-1"] .birdtracks-whiteboard-rendered')
    assert "2_4" not in (rendered.text_content() or "")
    assert page.evaluate("() => model.get('blocks')[0].source") == r"2_4\pair"


def test_recreated_last_pair_remains_content_sized(page):
    pair_source = base64.b64encode((STATIC / 'projector-widget.js').read_bytes()).decode()
    page.add_style_tag(content=(STATIC / 'projector-widget.css').read_text())
    page.evaluate(r'''async source => {
      cleanup();
      childModel.set('widget_role', 'pair');
      childModel.set('read_only', false);
      childModel.set('pair_cell_styles', {});
      childModel.set('pair_drawing_state', {});
      childModel.set('pair_expression', {version: 1, kind: 'sum', terms: [
        {kind: 'pair', barred: [1], unbarred: [], coefficient: '1', n0: '1'},
      ]});
      const pair = await import('data:text/javascript;base64,' + source);
      model.set('embedded_projector_ids', []);
      model.set('embedded_projectors', []);
      model.set('embedded_pair_ids', [
        'pair-line:pair:0', 'pair-line:pair:1', 'pair-line:pair:2',
      ]);
      model.set('embedded_pairs', ['pair-0', 'pair-1', 'pair-2']);
      model.set('blocks', [
        {id: 'before', source: 'A', line_id: 'before'},
        {id: 'pair-line', source: 'B\\def \\pair\\oplus\\pair\\oplus\\pair',
          line_id: 'pair-line'},
        {id: 'after', source: 'C', line_id: 'after'},
      ]);
      window.cleanup = module.default.render({
        model, el: document.querySelector('#widget'), signal: null,
        host: {getModel: async () => childModel,
          getWidget: async () => {
            await new Promise(resolve => setTimeout(resolve, 30));
            return {render: ({el}) => {
              const widgetHost = document.createElement('div');
              widgetHost.style.width = '360px';
              el.appendChild(widgetHost);
              return pair.default.render({model: childModel, el: widgetHost});
            }};
          }},
      });
    }''', pair_source)
    editor = page.locator('[data-block-id="pair-line"] textarea')
    editor.focus()
    editor.press('End')
    page.wait_for_timeout(80)
    initial_caret_gap = page.evaluate("""() => {
      const block = document.querySelector('[data-block-id="pair-line"]');
      const pair = [...block.querySelectorAll('.birdtracks-whiteboard-embedded-pair')].at(-1);
      const term = pair.querySelector('.birdtracks-young-term').getBoundingClientRect();
      const caret = block.querySelector('.birdtracks-whiteboard-caret').getBoundingClientRect();
      return caret.left - term.right;
    }""")
    assert initial_caret_gap == pytest.approx(0, abs=1)

    two_pairs = r'B\def \pair\oplus\pair'
    three_pairs = two_pairs + r'\oplus\pair\oplus'

    editor.fill(two_pairs)
    page.evaluate("""() => {
      model.set('embedded_pair_ids', ['pair-line:pair:0', 'pair-line:pair:1']);
      model.set('embedded_pairs', ['pair-0', 'pair-1']);
    }""")
    editor.fill(three_pairs)
    page.evaluate("""() => {
      model.set('embedded_pair_ids', [
        'pair-line:pair:0', 'pair-line:pair:1', 'pair-line:pair:2',
      ]);
      model.set('embedded_pairs', ['pair-0', 'pair-1', 'pair-recreated']);
    }""")
    for _ in range(3):
        page.get_by_role('button', name='Save', exact=True).click()
    page.wait_for_timeout(50)

    geometry = page.locator(
        '[data-block-id="pair-line"] .birdtracks-whiteboard-embedded-pair'
    ).last.evaluate("""pair => {
      const term = pair.querySelector('.birdtracks-young-term');
      const workspace = pair.querySelector('.birdtracks-young-workspace');
      const pairBox = pair.getBoundingClientRect();
      const termBox = term.getBoundingClientRect();
      return {pairWidth: pairBox.width, workspaceWidth: workspace.getBoundingClientRect().width,
        termWidth: termBox.width, rightPadding: pairBox.right - termBox.right};
    }""")
    trailing_operator_gap = page.evaluate("""() => {
      const block = document.querySelector('[data-block-id="pair-line"]');
      const pair = [...block.querySelectorAll('.birdtracks-whiteboard-embedded-pair')].at(-1);
      const term = pair.querySelector('.birdtracks-young-term').getBoundingClientRect();
      const operator = [...block.querySelectorAll('.birdtracks-whiteboard-pair-operator')]
        .at(-1).getBoundingClientRect();
      return operator.left - term.right;
    }""")
    assert geometry['pairWidth'] == pytest.approx(geometry['termWidth'], abs=1)
    assert geometry['workspaceWidth'] == pytest.approx(geometry['termWidth'], abs=1)
    assert geometry['rightPadding'] == pytest.approx(0, abs=1)
    assert trailing_operator_gap < 10


def test_clicking_anywhere_in_an_empty_pair_cell_adds_a_box(page):
    pair_source = base64.b64encode((STATIC / "projector-widget.js").read_bytes()).decode()
    page.evaluate(
        """async source => {
          window.pairModule = await import('data:text/javascript;base64,' + source);
          const values = {
            widget_role: 'pair', read_only: false,
            pair_expression: {version: 1, kind: 'sum', terms: [
              {kind: 'pair', barred: [], unbarred: [], coefficient: '1', n0: '0'},
            ]}, pair_drawing_state: {},
          };
          const listeners = new Map();
          window.pairModel = {
            get: name => values[name],
            set(name, value) {
              values[name] = value;
              for (const fn of listeners.get('change:' + name) || []) fn({new: value});
            },
            on(names, fn) {
              for (const name of names.split(' ')) {
                if (!listeners.has(name)) listeners.set(name, new Set());
                listeners.get(name).add(fn);
              }
            },
            off() {}, save_changes() {},
          };
          const host = document.createElement('div');
          document.querySelector('.birdtracks-whiteboard-section').appendChild(host);
          window.pairCleanup = pairModule.default.render({model: pairModel, el: host});
        }""",
        pair_source,
    )
    target = page.locator(
        '.birdtracks-young-cell-target[data-grid-row="0"][data-grid-column="0"]'
    ).first
    empty = {
        "version": 1,
        "kind": "sum",
        "terms": [
            {"kind": "pair", "barred": [], "unbarred": [],
             "coefficient": "1", "n0": "0"},
        ],
    }
    for x_fraction in (0.05, 0.5, 0.95):
        for y_fraction in (0.05, 0.5, 0.95):
            page.evaluate("state => pairModel.set('pair_expression', state)", empty)
            target.scroll_into_view_if_needed()
            bounds = target.bounding_box()
            assert bounds is not None
            page.mouse.click(
                bounds["x"] + bounds["width"] * x_fraction,
                bounds["y"] + bounds["height"] * y_fraction,
            )
            assert page.evaluate(
                "() => pairModel.get('pair_expression').terms[0].unbarred"
            ) == [1]


def test_paintbrush_colours_pair_boxes_before_and_after_shift_enter(page):
    pair_source = base64.b64encode((STATIC / "projector-widget.js").read_bytes()).decode()
    page.evaluate(
        """async source => {
          window.pairModule = await import('data:text/javascript;base64,' + source);
          const values = {
            widget_role: 'pair', read_only: false,
            pair_expression: {version: 1, kind: 'sum', terms: [
              {kind: 'pair', barred: [], unbarred: [1], coefficient: '1', n0: '1'},
            ]}, pair_drawing_state: {},
          };
          const listeners = new Map();
          window.pairModel = {
            get: name => values[name],
            set(name, value) {
              values[name] = value;
              for (const fn of listeners.get('change:' + name) || []) fn({new: value});
            },
            on(names, fn) {
              for (const name of names.split(' ')) {
                if (!listeners.has(name)) listeners.set(name, new Set());
                listeners.get(name).add(fn);
              }
            },
            off() {}, save_changes() {},
          };
          const section = document.querySelector('.birdtracks-whiteboard-section');
          section._birdtracksPaintbrush.active = true;
          section._birdtracksPaintbrush.color = '#ff0000';
          const host = document.createElement('div');
          section.appendChild(host);
          window.pairCleanup = pairModule.default.render({model: pairModel, el: host});
        }""",
        pair_source,
    )
    page.locator('.birdtracks-young-box').first.click()
    assert page.locator('.birdtracks-young-box').first.evaluate(
        'el => el.style.fill'
    ) == 'rgb(255, 0, 0)'

    calculation_svg = (
        '<svg class="birdtracks-pair-evaluation-line">'
        '<g data-cell="0:0"><rect width="30" height="30" fill="white"/>'
        '<text x="15" y="15">1</text></g>'
        '<g data-cell="1:0"><rect x="40" width="30" height="30" fill="white"/>'
        '<text x="55" y="15">1</text></g></svg>'
    )
    page.locator('textarea').first.press('Shift+Enter')
    page.evaluate(
        "svg => model.set('blocks', [{id: 'text-1', source: '= 1', read_only: true, calculation_svg: svg}])",
        calculation_svg,
    )
    page.wait_for_timeout(20)
    result_boxes = page.locator('.birdtracks-pair-evaluation-line [data-cell] rect')
    result_boxes.first.click(position={"x": 5, "y": 5})
    assert result_boxes.evaluate_all("items => items.map(item => item.style.fill)") == [
        "rgb(255, 0, 0)",
        "",
    ]


def test_paintbrush_colours_only_one_term_in_a_pair_sum(page):
    pair_source = base64.b64encode((STATIC / "projector-widget.js").read_bytes()).decode()
    page.evaluate(
        """async source => {
          const pairModule = await import('data:text/javascript;base64,' + source);
          const values = {
            widget_role: 'pair', read_only: false,
            pair_expression: {version: 1, kind: 'sum', syntax: ['pair', 'sum', 'pair'],
              terms: [0, 1].map(() => ({kind: 'pair', barred: [], unbarred: [1],
                coefficient: '1', n0: '1'}))},
            pair_drawing_state: {}, pair_cell_styles: {},
          };
          const listeners = new Map();
          const pairModel = {
            get: name => values[name],
            set(name, value) { values[name] = value;
              for (const fn of listeners.get('change:' + name) || []) fn({new: value}); },
            on(names, fn) { for (const name of names.split(' ')) {
              if (!listeners.has(name)) listeners.set(name, new Set());
              listeners.get(name).add(fn); } },
            off() {}, save_changes() {},
          };
          const section = document.querySelector('.birdtracks-whiteboard-section');
          section._birdtracksPaintbrush.active = true;
          section._birdtracksPaintbrush.color = '#ff0000';
          const host = document.createElement('div');
          section.appendChild(host);
          pairModule.default.render({model: pairModel, el: host});
        }""",
        pair_source,
    )
    boxes = page.locator('.birdtracks-young-box')
    boxes.first.click()
    assert boxes.evaluate_all("items => items.map(item => item.style.fill)") == [
        "rgb(255, 0, 0)",
        "",
    ]


def test_pair_operators_use_inline_circle_icons_while_typing(page):
    result = page.evaluate(
        """source => {
          const target = document.createElement('div');
          module.renderLatex(source, target);
          return {
            operators: [...target.querySelectorAll(
              '.birdtracks-whiteboard-pair-operator'
            )].map(item => ({
              operation: item.getAttribute('aria-label'),
              lines: item.querySelectorAll('line').length,
              circles: item.querySelectorAll('circle').length,
            })),
            text: target.textContent,
          };
        }""",
        r"a \oplus b \otimes c",
    )

    assert result == {
        "operators": [
            {"operation": "Direct sum", "lines": 2, "circles": 1},
            {"operation": "Tensor product", "lines": 2, "circles": 1},
        ],
        "text": "abc",
    }


def test_adjacent_pair_editors_show_implicit_tensor_icon(page):
    page.evaluate(
        """() => model.set('blocks', [
          {id: 'pair-line', source: '\\\\pair  \\\\pair', line_id: 'pair-line'},
        ])"""
    )

    operator = page.get_by_label("Tensor product")
    assert operator.count() == 1
    assert operator.locator("circle").count() == 1
    assert operator.locator("line").count() == 2


def test_long_pair_result_wraps_at_terms_and_reflows_on_resize(page):
    page.evaluate(
        """() => model.set('blocks', [{
          id: 'long-result', source: '', read_only: true, calculation_step: 1,
          calculation_svg: '<svg class="birdtracks-pair-evaluation-line" '
            + 'width="1820" height="40" viewBox="0 0 1820 40" '
            + 'data-natural-width="1820" data-line-height="40">'
            + '<g data-pair-token="equals" data-token-x="2" data-token-width="20"></g>'
            + '<g data-pair-token="pair" data-token-x="24" data-token-width="580"></g>'
            + '<g data-pair-token="sum" data-token-x="606" data-token-width="22"></g>'
            + '<g data-pair-token="pair" data-token-x="630" data-token-width="580"></g>'
            + '<g data-pair-token="sum" data-token-x="1212" data-token-width="22"></g>'
            + '<g data-pair-token="pair" data-token-x="1236" data-token-width="580"></g>'
            + '</svg>',
        }])"""
    )
    page.wait_for_timeout(30)

    rendered = page.locator('[data-block-id="long-result"] .birdtracks-whiteboard-rendered')
    svg = rendered.locator("svg")
    assert float(svg.get_attribute("height")) > 40
    assert rendered.evaluate("el => getComputedStyle(el).overflowX") == "hidden"
    assert svg.locator('[data-token-x="1212"]').get_attribute("transform").startswith(
        "translate(-"
    )

    page.locator("#widget").evaluate("el => el.style.width = '2200px'")
    page.wait_for_timeout(30)
    assert svg.get_attribute("height") == "40"
    assert svg.locator('[data-token-x="1212"]').get_attribute("transform") is None


def test_whiteboard_keeps_a_trailing_typing_row(page):
    assert page.locator(".birdtracks-whiteboard-block").count() == 2
    assert page.locator(".birdtracks-whiteboard-block.trailing-blank").count() == 1
    trailing = page.locator(".trailing-blank textarea")
    trailing.type("next")
    page.wait_for_timeout(20)
    assert page.evaluate("() => model.get('blocks').at(-1).source") == "next"
    assert page.locator(".birdtracks-whiteboard-block.trailing-blank").count() == 1


def test_whiteboard_blank_space_focuses_the_nearest_editable_line(page):
    blocks = page.locator(".birdtracks-whiteboard-blocks")
    box = blocks.bounding_box()
    assert box is not None

    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] - 10)

    playwright.expect(page.locator(".trailing-blank textarea")).to_be_focused()


def test_clicked_calculation_line_emphasizes_its_connection_segment(page):
    page.evaluate("""() => model.set('blocks', [
      {id:'source',source:'A',line_id:'g',calculation_group:'g'},
      {id:'result',source:'= A',read_only:true,calculation_group:'g',calculation_step:1},
    ])""")
    result = page.locator('.birdtracks-whiteboard-block[data-block-id="result"]')

    result.locator(".birdtracks-whiteboard-rendered").click()

    playwright.expect(result.locator(".birdtracks-whiteboard-rendered")).to_be_focused()
    indicator = result.evaluate("""element => {
      const style = getComputedStyle(element, '::before');
      return {width: style.width, background: style.backgroundColor};
    }""")
    assert indicator == {"width": "3px", "background": "rgb(71, 85, 105)"}


def test_trace_calculation_segment_can_be_selected_and_restored(page):
    page.evaluate(r"""() => model.set('blocks', [
      {id:'trace',source:'\\tr\\left(P\\right)',read_only:true,calculation_group:'trace'},
      {id:'result',source:'= N',read_only:true,calculation_group:'trace',
       calculation_step:1,calculation_scalar:true},
    ])""")
    trace = page.locator('.birdtracks-whiteboard-block[data-block-id="trace"]')

    trace.locator(".birdtracks-whiteboard-rendered").click()

    playwright.expect(trace.locator(".birdtracks-whiteboard-rendered")).to_be_focused()
    indicator = trace.evaluate("""element => {
      const style = getComputedStyle(element, '::before');
      return {width: style.width, background: style.backgroundColor};
    }""")
    assert indicator == {"width": "3px", "background": "rgb(71, 85, 105)"}
    page.keyboard.press("Shift+Backspace")
    assert page.evaluate("model.get('simplify_request')") == {
        "line_id": "trace", "action": "restore", "revision": 1, "snapshots": {},
    }


def test_enter_saves_embedded_projector_state(page):
    page.evaluate("""() => childModel.on('change:save_command', () => {
      childModel.set('save_snapshot', {revision: 1, sentinel: 'drawn'});
    })""")
    editor = page.locator('[data-block-id="text-1"] textarea')
    editor.focus()
    editor.press("End")
    editor.press("Enter")
    assert page.evaluate("() => childModel.get('save_command')") == 1
    assert page.evaluate(
        "() => model.get('blocks')[0].projector_snapshots['0'].sentinel"
    ) == "drawn"
    page.wait_for_timeout(50)
    page.evaluate("() => model.set('blocks', structuredClone(model.get('blocks')))")
    playwright.expect(page.locator("textarea").nth(1)).to_be_focused()
    page.keyboard.type("next")
    assert page.evaluate("() => model.get('blocks')[1].source") == "next"


def test_enter_saves_embedded_pair_state(page):
    expression = {
        "version": 1,
        "kind": "sum",
        "terms": [{
            "kind": "pair", "barred": [1], "unbarred": [2],
            "coefficient": "1", "n0": "2",
        }],
    }
    page.evaluate(r"""expression => {
      childModel.set('pair_expression', expression);
      model.set('embedded_projector_ids', []);
      model.set('embedded_projectors', []);
      model.set('embedded_pair_ids', ['text-1:pair:0']);
      model.set('embedded_pairs', ['child-1']);
      model.set('blocks', [{id: 'text-1', source: '\\pair'}]);
    }""", expression)
    page.wait_for_timeout(20)

    editor = page.locator('[data-block-id="text-1"] textarea')
    editor.focus()
    editor.press("End")
    editor.press("Enter")

    assert page.evaluate(
        "() => model.get('blocks')[0].pair_snapshots['0']"
    ) == expression


def test_connected_lines_have_one_continuous_group_indicator(page):
    page.evaluate("""() => model.set('blocks', [
      {id:'a',source:'A',line_id:'group'},
      {id:'b',source:'&+B',line_id:'group'},
      {id:'c',source:'C',line_id:'other'},
    ])""")
    assert page.locator('.connected-line').count() == 2
    assert page.locator('.birdtracks-whiteboard-block[data-block-id="a"]').get_attribute(
        'data-connection-group'
    ) == 'group'
    assert not page.locator('.birdtracks-whiteboard-block[data-block-id="c"]').evaluate(
        "el => el.classList.contains('connected-line')"
    )
    assert page.locator('.birdtracks-whiteboard-block[data-block-id="c"]').evaluate(
        "el => el.classList.contains('connection-break')"
    )


def test_arrows_cross_editable_and_calculated_lines(page):
    page.evaluate("""() => model.set('blocks', [
      {id:'a',source:'abcd'},
      {id:'b',source:'= 2',read_only:true,calculation_group:'g',calculation_step:1},
      {id:'c',source:'xyz'},
    ])""")
    editors = page.locator('textarea')
    editors.first.focus()
    editors.first.press('ArrowDown')
    calculated = page.locator('[data-block-id="b"] .birdtracks-whiteboard-rendered')
    playwright.expect(calculated).to_be_focused()
    calculated.press('Shift+Enter')
    assert page.evaluate("model.get('simplify_request').line_id") == 'b'
    calculated.press('ArrowDown')
    last_editor = page.locator('[data-block-id="c"] textarea')
    playwright.expect(last_editor).to_be_focused()
    last_editor.press('Home')
    last_editor.press('ArrowLeft')
    playwright.expect(calculated).to_be_focused()
    calculated.press('ArrowUp')
    playwright.expect(editors.first).to_be_focused()


def test_shift_enter_after_remount_sends_a_new_request(page):
    page.evaluate("""() => {
      model.set('simplify_request', {line_id:'text-1', action:'evaluate', revision:7, snapshots:{}});
      cleanup();
      window.cleanup = window.module.default.render({
        model, el:document.querySelector('#widget'), signal:null,
      });
    }""")
    page.locator('textarea').first.focus()
    page.keyboard.press('Shift+Enter')
    assert page.evaluate("model.get('simplify_request').revision") == 8


def test_shift_enter_shows_calculation_pending_until_the_backend_responds(page):
    editor = page.locator('textarea').first
    editor.focus()
    editor.press('Shift+Enter')

    pending = page.locator('[data-block-id="text-1"] .birdtracks-whiteboard-calculation-pending')
    playwright.expect(pending).to_be_visible()
    page.evaluate("""() => model.set('calculation_feedback', {
      line_id: 'text-1', action: 'completed', revision: 1,
    })""")
    assert pending.is_hidden()


def test_calculation_error_replaces_pending_status_with_ephemeral_log(page):
    editor = page.locator('textarea').first
    editor.focus()
    editor.press('Shift+Enter')

    page.evaluate("""() => model.set('calculation_feedback', {
      line_id: 'text-1', action: 'rejected', reason: 'bad expression',
      traceback: 'Traceback (most recent call last):\\nValueError: bad expression',
      revision: 1,
    })""")

    status = page.locator('[data-block-id="text-1"] .birdtracks-whiteboard-calculation-pending')
    playwright.expect(status).to_be_visible()
    assert status.locator('span').text_content() == 'Error'
    assert page.get_by_role('button', name='Cancel calculation').is_hidden()
    log = page.get_by_role('link', name='Open log')
    playwright.expect(log).to_be_visible()
    log.click()
    request = page.evaluate("() => model.get('open_error_log_request')")
    assert request["line_id"] == "text-1"
    assert request["revision"] > 0


def test_cancelling_a_pending_calculation_keeps_the_source_line(page):
    editor = page.locator('textarea').first
    editor.focus()
    editor.press('Shift+Enter')
    page.get_by_role('button', name='Cancel calculation').click()

    assert page.locator('[data-block-id="text-1"] .birdtracks-whiteboard-calculation-pending').is_hidden()
    assert page.evaluate("() => model.get('blocks')[0].source") == '123.45\\birdtracks'
    assert not page.evaluate("() => model.get('blocks')[0].read_only")


def test_shift_enter_includes_a_prior_definition_snapshot(page):
    snapshot = {"revision": 1, "graph": {"sentinel": True}}
    page.evaluate("""snapshot => {
      model.set('embedded_projector_ids', ['definition:projector:0']);
      model.set('embedded_projectors', ['child-1']);
      model.set('blocks', [
        {id: 'definition', source: 'A\\\\def \\\\birdtracks',
         projector_snapshots: {'0': snapshot}},
        {id: 'trace', source: '\\\\tr(A)'},
      ]);
    }""", snapshot)

    page.locator('[data-block-id="trace"] textarea').press('Shift+Enter')

    assert page.evaluate(
        "() => model.get('simplify_request').snapshots['definition:projector:0']"
    ) == snapshot


def test_result_rebuild_keeps_keyboard_focus(page):
    editor = page.locator('textarea').first
    editor.focus()
    editor.press('Shift+Enter')
    page.evaluate("""() => model.set('blocks', [
      {id:'text-1',source:'x',read_only:true,calculation_group:'g'},
      {id:'result',source:'= 2',read_only:true,calculation_group:'g',calculation_step:1},
    ])""")
    result = page.locator('[data-block-id="result"] .birdtracks-whiteboard-rendered')
    playwright.expect(result).to_be_focused()
    page.keyboard.press('Shift+Enter')
    assert page.evaluate("model.get('simplify_request').line_id") == 'result'


def test_calculation_equals_align_and_allow_surrounding_text(page):
    page.evaluate(r"""() => model.set('blocks', [
      {id:'original',source:'x',read_only:true,calculation_group:'g'},
      {id:'step1',source:'= 1 + 2',read_only:true,calculation_group:'g',calculation_step:1},
      {id:'step2',source:'= 3',read_only:true,calculation_group:'g',calculation_step:2},
    ])""")
    page.wait_for_timeout(50)
    equals = page.locator('mo').filter(has_text='=')
    assert equals.count() == 2
    assert equals.nth(0).bounding_box()['x'] == pytest.approx(equals.nth(1).bounding_box()['x'])
    result = page.locator('[data-block-id="step2"] .birdtracks-whiteboard-rendered')
    result.focus()
    result.press('Enter')
    playwright.expect(page.locator('textarea').last).to_be_focused()
    page.keyboard.type('below')
    result = page.locator('[data-block-id="step1"] .birdtracks-whiteboard-rendered')
    result.focus()
    result.press('Control+Enter')
    playwright.expect(page.locator('textarea').first).to_be_focused()
    page.keyboard.type('above')
    blocks = page.evaluate("model.get('blocks')")
    assert blocks[0]['source'] == 'above'
    assert blocks[-1]['source'] == 'below'
    assert not blocks[0].get('read_only')
    assert not blocks[-1].get('read_only')


def test_def_projector_source_remains_valid_after_leaving_embedded_editor(page):
    page.evaluate(
        """() => model.set('blocks', [
          {id: 'text-1', source: 'A\\\\def \\\\birdtracks', line_id: 'text-1'},
        ])"""
    )
    page.wait_for_timeout(50)
    assert page.locator(".birdtracks-whiteboard-invalid-source").count() == 0

    page.locator(".birdtracks-whiteboard-embedded-projector").dispatch_event(
        "pointerdown"
    )
    page.locator("textarea").first.click()
    page.wait_for_timeout(50)
    assert page.locator(".birdtracks-whiteboard-invalid-source").count() == 0


def test_leaving_embedded_projector_keeps_topology_editable(page):
    anchor = page.locator(".birdtracks-whiteboard-embedded-projector").first
    anchor.dispatch_event("pointerdown")
    assert page.evaluate("() => childModel.get('mode')") == "create"

    editor = page.locator("textarea").first
    editor.click()
    editor.press("Home")
    page.wait_for_timeout(50)

    assert page.evaluate("() => childModel.get('mode')") == "create"


def test_unchanged_source_blur_does_not_cancel_embedded_click(page):
    anchor = page.locator(".birdtracks-whiteboard-embedded-projector").first
    anchor.evaluate(
        """element => {
          element.style.width = '40px';
          element.addEventListener('click', () => { window.embeddedClicked = true; });
        }"""
    )
    page.locator("textarea").first.focus()

    anchor.click()

    assert page.evaluate("() => window.embeddedClicked") is True


def test_clicking_away_commits_embedded_projector_state(page):
    page.evaluate("""() => childModel.on('change:save_command', () => {
      childModel.set('save_snapshot', {
        graph: {nodes: [{kind: 'symmetriser', labels: [1, 2]}]},
        port_orders: {'0': {input: [1, 2], output: [1, 2]}},
        boundary_orders: {left: [1, 2], right: [1, 2]},
      });
    })""")
    anchor = page.locator(".birdtracks-whiteboard-embedded-projector").first
    anchor.dispatch_event("pointerdown")

    page.locator(".birdtracks-whiteboard-title").dispatch_event("pointerdown")

    snapshot = page.evaluate(
        "() => model.get('blocks')[0].projector_snapshots['0']"
    )
    assert snapshot["graph"]["nodes"][0]["kind"] == "symmetriser"


def test_real_projector_survives_text_click_and_evaluation_snapshot(page):
    from birdtracks.projectors.widget import _blank_creator_widget

    child = _blank_creator_widget(embedded=True)
    state = child.get_state()
    state["widget_role"] = "embedded"
    state["group_id"] = "whiteboard-test"
    source = base64.b64encode((STATIC / "projector-widget.js").read_bytes()).decode()
    page.add_style_tag(content=(STATIC / "projector-widget.css").read_text())
    page.evaluate(
        """async ({state, source}) => {
          cleanup();
          for (const [key, value] of Object.entries(state)) childModel.set(key, value);
          childModel.model_id = 'real-child';
          const projector = await import('data:text/javascript;base64,' + source);
          model.set('blocks', [{id: 'text-1', source: 'A\\\\def 2\\\\birdtracks'}]);
          window.realCleanup = null;
          window.cleanup = window.module.default.render({
            model, el: document.querySelector('#widget'), signal: null,
            host: {
              getModel: async () => childModel,
              getWidget: async () => ({render: async ({el}) => {
                realCleanup = projector.default.render({model: childModel, el});
              }}),
            },
          });
        }""",
        {"state": {key: value for key, value in state.items() if not key.startswith("_")},
         "source": source},
    )
    page.wait_for_timeout(100)
    page.evaluate("""() => {
      const brush = document.querySelector('.birdtracks-whiteboard-section')._birdtracksPaintbrush;
      brush.active = true;
      brush.color = '#ff0000';
    }""")
    insertion_point = page.locator('.birdtracks-line-hit').first.evaluate("""path => {
      const point = path.getPointAtLength(path.getTotalLength() / 2)
        .matrixTransform(path.getScreenCTM());
      const control = path.closest('svg').querySelector('.birdtracks-add-line-control-hit');
      const plus = new DOMPoint(
        Number(control.getAttribute('cx')), Number(control.getAttribute('cy')),
      ).matrixTransform(control.getScreenCTM());
      return {x: point.x, y: point.y + 0.8 * (plus.y - point.y)};
    }""")
    page.mouse.dblclick(insertion_point["x"], insertion_point["y"])
    assert page.locator('.birdtracks-symmetriser').count() == 1
    page.evaluate("""() => {
      const blocks = structuredClone(model.get('blocks'));
      blocks[0].line_colors = {'right-anchor:0->left-anchor:0': '#ff0000'};
      model.set('blocks', blocks);
    }""")
    assert page.locator('.birdtracks-symmetriser').count() == 1
    page.locator('.birdtracks-symmetriser').first.click(button='right')
    assert page.locator('.birdtracks-symmetriser').count() == 0
    between_lines = page.locator('.birdtracks-level-guide').evaluate_all("""guides => {
      const points = guides.slice(0, 2).map(line => new DOMPoint(
        (Number(line.getAttribute('x1')) + Number(line.getAttribute('x2'))) / 2,
        Number(line.getAttribute('y1')),
      ).matrixTransform(line.getScreenCTM()));
      return {x: points[0].x, y: points[0].y + 0.8 * (points[1].y - points[0].y)};
    }""")
    page.mouse.dblclick(between_lines["x"], between_lines["y"])
    assert page.locator('.birdtracks-symmetriser').count() == 1
    operator_y = page.locator('.birdtracks-symmetriser').get_attribute('y')
    guide_ys = page.locator('.birdtracks-level-guide').evaluate_all(
        "guides => guides.slice(0, 2).map(line => Number(line.getAttribute('y1')))"
    )
    assert float(operator_y) < sum(guide_ys) / 2
    page.locator('.birdtracks-symmetriser').first.click(button='right')
    assert page.locator('.birdtracks-symmetriser').count() == 0
    page.evaluate("""() => document.dispatchEvent(new CustomEvent('birdtracks-projector-tool', {
      detail: {groupId: 'whiteboard-test', action: 'add-symmetriser'}
    }))""")
    assert page.locator('.birdtracks-symmetriser').count() == 1
    editor = page.locator('textarea').first
    editor.click()
    editor.press('Home')
    assert page.locator('.birdtracks-symmetriser').count() == 1
    assert page.evaluate("() => childModel.get('mode')") == 'create'
    assert page.locator('.birdtracks-add-line-control').first.is_visible()
    assert page.locator('.birdtracks-canvas-viewport').evaluate(
        "el => getComputedStyle(el).overflowY"
    ) == 'visible'
    page.locator('.birdtracks-whiteboard-embedded-projector').dispatch_event('pointerdown')
    assert page.locator('.birdtracks-add-line-control').first.is_visible()
    page.keyboard.press('Shift+Enter')
    snapshot = page.evaluate("() => model.get('simplify_request').snapshots['text-1:projector:0']")
    assert snapshot['graph']['nodes'][0]['kind'] == 'symmetriser'
    from birdtracks import whiteboard

    document = whiteboard(debug=True)
    document.blocks = [
        {"id": "text-1", "source": r"A\def 2\birdtracks"},
        {"id": "text-2", "source": r"\birdtracks"},
    ]
    document.simplify_request = page.evaluate("() => model.get('simplify_request')")
    assert document.blocks[1]['calculation_step'] == 1
    assert document.embedded_projectors[0].mode == 'evaluate'
    assert document.embedded_projectors[1].mode == 'create'
    # A snapshot-save response can rebuild/refocus the editable source before
    # the kernel's calculation response arrives. Exercise both deliveries.
    editor.focus()
    page.keyboard.press('Shift+Enter')
    page.evaluate("() => model.set('blocks', structuredClone(model.get('blocks')))")
    playwright.expect(page.locator('textarea').first).to_be_focused()
    page.evaluate("""blocks => {
      document.querySelector('textarea').dispatchEvent(new Event('focus'));
      model.set('blocks', blocks);
    }""", list(document.blocks))
    playwright.expect(page.locator('textarea').first).to_be_disabled()
    page.wait_for_function("childModel.get('mode') === 'evaluate'")
    controls = page.get_by_role('button', name='Recursively expand from the top line')
    playwright.expect(controls.first).to_be_visible()
    document.simplify_request = {"action": "restore", "line_id": "text-1", "revision": 2}
    assert len(document.blocks) == 2
    assert document.embedded_projectors[0].mode == 'create'
    assert page.locator('.birdtracks-whiteboard-invalid-source').count() == 0
    page.evaluate("() => realCleanup?.()")


def test_enter_splits_lines_and_ampersand_continues_the_previous_line(page):
    editor = page.locator("textarea").first
    editor.click()
    editor.press("End")
    editor.press("Enter")
    playwright.expect(page.locator("textarea").nth(1)).to_be_focused()
    page.evaluate(
        "() => model.set('blocks', structuredClone(model.get('blocks')))"
    )
    playwright.expect(page.locator("textarea").nth(1)).to_be_focused()
    page.keyboard.type("&+x")

    blocks = page.evaluate("() => model.get('blocks')")
    assert [block["source"] for block in blocks] == [r"123.45\birdtracks", "&+x"]
    assert blocks[0]["line_id"] == blocks[1]["line_id"]

    editor = page.locator("textarea").nth(1)
    editor.press("End")
    editor.press("Enter")
    playwright.expect(page.locator("textarea").nth(2)).to_be_focused()
    page.keyboard.type("y")

    blocks = page.evaluate("() => model.get('blocks')")
    assert [block["source"] for block in blocks] == [
        r"123.45\birdtracks", "&+x", "y"
    ]
    assert blocks[1]["line_id"] != blocks[2]["line_id"]


def test_enter_in_the_middle_uses_the_line_being_split_as_previous(page):
    editor = page.locator("textarea").first
    editor.click()
    editor.press("End")
    editor.press("Enter")
    page.wait_for_timeout(50)
    page.keyboard.type("&+x")

    editor = page.locator("textarea").nth(1)
    editor.click()
    editor.press("Home")
    editor.press("ArrowRight")
    editor.press("Enter")
    page.wait_for_timeout(50)
    page.keyboard.type("&y")

    blocks = page.evaluate("() => model.get('blocks')")
    assert blocks[1]["line_id"] == blocks[2]["line_id"]


def test_backspace_at_start_merges_with_previous_block(page):
    page.evaluate(
        """() => model.set('blocks', [
          {id: 'text-1', source: 'A', line_id: 'text-1'},
          {id: 'text-2', source: '', line_id: 'text-2'},
        ])"""
    )
    editor = page.locator("textarea").nth(1)
    editor.click()
    editor.press("Backspace")
    page.wait_for_timeout(50)

    assert page.evaluate("() => model.get('blocks')") == [
        {"id": "text-1", "source": "A", "line_id": "text-1"},
    ]
    assert page.locator("textarea").first.evaluate(
        "el => [el.selectionStart, el.selectionEnd]"
    ) == [1, 1]


def test_backspace_on_trailing_empty_line_moves_to_line_above(page):
    trailing = page.locator(".trailing-blank textarea")
    trailing.click()
    trailing.press("Backspace")

    previous = page.locator('[data-block-id="text-1"] textarea')
    playwright.expect(previous).to_be_focused()
    assert previous.evaluate("el => el.selectionStart") == len(r"123.45\birdtracks")


def test_backspace_deletes_first_empty_line_and_focuses_active_line_below(page):
    page.evaluate("""() => model.set('blocks', [
      {id:'empty',source:'',line_id:'empty'},
      {id:'active',source:'A',line_id:'active'},
    ])""")
    page.locator('[data-block-id="empty"] textarea').press("Backspace")

    assert page.evaluate("model.get('blocks')") == [
        {"id": "active", "source": "A", "line_id": "active"},
    ]
    active = page.locator('[data-block-id="active"] textarea')
    playwright.expect(active).to_be_focused()
    assert active.evaluate("el => el.selectionStart") == 0


def test_deleting_projector_discards_its_saved_canvas(page):
    page.evaluate(
        """() => {
          const blocks = structuredClone(model.get('blocks'));
          blocks[0].projector_snapshots = {'0': {sentinel: 'deleted canvas'}};
          model.set('blocks', blocks);
        }"""
    )
    editor = page.locator("textarea").first
    editor.click()
    editor.press("End")
    editor.press("Backspace")

    block = page.evaluate("() => model.get('blocks')[0]")
    assert block["source"] == "123.45"
    assert "projector_snapshots" not in block


def test_deleted_pair_is_not_resaved_from_a_stale_mount(page):
    page.evaluate(r"""() => {
      model.set('embedded_projector_ids', []);
      model.set('embedded_projectors', []);
      model.set('embedded_pair_ids', ['text-1:pair:0']);
      model.set('embedded_pairs', ['child-1']);
      childModel.set('pair_expression', {version: 1, kind: 'sum', terms: [
        {kind: 'pair', barred: [1], unbarred: [], coefficient: '1', n0: '1'},
      ]});
      model.set('blocks', [{id: 'text-1', source: '\\pair', line_id: 'text-1',
        pair_snapshots: {
          '0': {version: 1, kind: 'sum', terms: []},
          '1': {version: 1, kind: 'sum', terms: []},
        }}]);
    }""")
    page.wait_for_timeout(50)
    assert page.locator('.birdtracks-whiteboard-embedded-pair').count() == 1

    page.get_by_role('button', name='Save', exact=True).click()
    assert list(page.evaluate("model.get('blocks')[0].pair_snapshots")) == ['0']

    editor = page.locator('[data-block-id="text-1"] textarea')
    editor.fill('x')
    page.wait_for_timeout(20)
    assert page.locator('.birdtracks-whiteboard-embedded-pair').count() == 0

    for _ in range(3):
        page.get_by_role('button', name='Save', exact=True).click()
    block = page.evaluate("model.get('blocks')[0]")
    assert block['source'] == 'x'
    assert 'pair_snapshots' not in block


def test_deleting_wide_projector_resets_render_scroll_before_alignment(page):
    rendered = page.locator(
        ".birdtracks-whiteboard-block:not(.trailing-blank) "
        ".birdtracks-whiteboard-rendered"
    ).first
    rendered.evaluate(
        """element => {
          element.style.width = '80px';
          const spacer = document.createElement('span');
          spacer.style.display = 'inline-block';
          spacer.style.width = '500px';
          element.appendChild(spacer);
          element.scrollLeft = 200;
        }"""
    )
    assert rendered.evaluate("element => element.scrollLeft") > 0

    editor = page.locator("textarea").first
    editor.click()
    editor.press("End")
    editor.press("Backspace")

    assert rendered.evaluate("element => element.scrollLeft") == 0


def test_continuation_lines_align_with_equals_and_ampersand(page):
    page.evaluate(
        """() => model.set('blocks', [
          {id: 'text-1', source: 'P = x', line_id: 'text-1'},
          {id: 'text-2', source: '&+y', line_id: 'text-1'},
          {id: 'text-3', source: '&+z', line_id: 'text-1'},
        ])"""
    )
    page.wait_for_timeout(50)
    positions = page.evaluate(
        """() => {
          const blocks = ['text-1', 'text-2', 'text-3'].map(id =>
            document.querySelector(`.birdtracks-whiteboard-block[data-block-id="${id}"]`));
          const elementAt = (block, value) => [...block.querySelectorAll('[data-source-start]')]
            .find(element => element.textContent === value);
          return blocks.map((block, index) => {
            if (index > 0) {
              return elementAt(block, '+').getBoundingClientRect().left;
            }
            return elementAt(block, 'x').getBoundingClientRect().left;
          });
        }"""
    )
    assert positions[1] == pytest.approx(positions[0], abs=1)
    assert positions[2] == pytest.approx(positions[1], abs=1)
    assert "&" not in (page.locator(
        ".birdtracks-whiteboard-block:not(.trailing-blank)"
    ).nth(1).text_content() or "")


def test_pair_alignment_ignores_retained_horizontal_scroll(page):
    page.evaluate(
        r"""() => {
          model.set('embedded_projector_ids', []);
          model.set('embedded_projectors', []);
          model.set('embedded_pair_ids', ['pair-line:pair:0']);
          model.set('embedded_pairs', ['child-1']);
          model.set('blocks', [
            {id: 'base-line', source: 'P = x', line_id: 'base-line'},
            {id: 'pair-line', source: '&\\pair', line_id: 'base-line'},
          ]);
        }"""
    )
    page.wait_for_timeout(50)
    pair_line = page.locator('[data-block-id="pair-line"]')
    rendered = pair_line.locator('.birdtracks-whiteboard-rendered')
    rendered.evaluate(
        """element => {
          const pair = element.querySelector('.birdtracks-whiteboard-embedded-pair');
          pair.style.width = '2000px';
          element.style.width = '160px';
          element.scrollLeft = 600;
        }"""
    )
    before = rendered.evaluate("element => parseFloat(element.style.paddingLeft)")

    # A save acknowledgement retains this row and reruns alignment.
    page.evaluate(
        """() => {
          const blocks = structuredClone(model.get('blocks'));
          blocks[1].pair_snapshots = {'0': {version: 1, kind: 'sum', terms: []}};
          model.set('blocks', blocks);
        }"""
    )
    page.wait_for_timeout(50)
    assert rendered.evaluate(
        "element => parseFloat(element.style.paddingLeft)"
    ) == pytest.approx(before, abs=1)

    # Inserting an earlier row reorders the retained pair row and aligns it again.
    page.evaluate(
        """() => model.set('blocks', [
          {id: 'inserted', source: 'Q', line_id: 'inserted'},
          ...structuredClone(model.get('blocks')),
        ])"""
    )
    page.wait_for_timeout(50)
    assert rendered.evaluate(
        "element => parseFloat(element.style.paddingLeft)"
    ) == pytest.approx(before, abs=1)


def test_pair_calculation_alignment_ignores_retained_horizontal_scroll(page):
    page.evaluate(
        r"""() => {
          model.set('embedded_projector_ids', []);
          model.set('embedded_projectors', []);
          model.set('embedded_pair_ids', ['pair-result:pair:0']);
          model.set('embedded_pairs', ['child-1']);
          model.set('blocks', [
            {id: 'source', source: 'P', line_id: 'source', calculation_group: 'group'},
            {id: 'first-result', source: '= a', read_only: true,
              calculation_group: 'group', calculation_step: 1},
            {id: 'pair-result', source: '= \\pair', read_only: true,
              calculation_group: 'group', calculation_step: 2},
          ]);
        }"""
    )
    page.wait_for_timeout(50)
    rendered = page.locator(
        '[data-block-id="pair-result"] .birdtracks-whiteboard-rendered'
    )
    rendered.evaluate(
        """element => {
          const pair = element.querySelector('.birdtracks-whiteboard-embedded-pair');
          pair.style.width = '2000px';
          element.style.width = '160px';
          element.scrollLeft = 600;
        }"""
    )
    before = rendered.evaluate("element => parseFloat(element.style.paddingLeft)")

    page.evaluate(
        """() => {
          const blocks = structuredClone(model.get('blocks'));
          blocks[2].pair_snapshots = {'0': {version: 1, kind: 'sum', terms: []}};
          model.set('blocks', blocks);
        }"""
    )
    page.wait_for_timeout(50)
    assert rendered.evaluate(
        "element => parseFloat(element.style.paddingLeft)"
    ) == pytest.approx(before, abs=1)


def test_continuation_line_stays_aligned_when_projector_is_typed(page):
    page.evaluate(
        """() => model.set('blocks', [
          {id: 'text-1', source: 'P = x', line_id: 'text-1'},
          {id: 'text-2', source: '&', line_id: 'text-1'},
        ])"""
    )
    editor = page.locator('[data-block-id="text-2"] textarea')
    editor.click()
    editor.press("End")
    editor.type(r"\birdtracks")
    page.wait_for_timeout(50)
    positions = page.evaluate(
        """() => {
          const first = document.querySelector('.birdtracks-whiteboard-block[data-block-id="text-1"]');
          const second = document.querySelector('.birdtracks-whiteboard-block[data-block-id="text-2"]');
          const rightHandSide = [...first.querySelectorAll('[data-source-start]')]
            .find(element => element.textContent === 'x');
          const projector = second.querySelector(
            '.birdtracks-whiteboard-embedded-projector'
          );
          return [
            rightHandSide.getBoundingClientRect().left,
            projector.getBoundingClientRect().left,
          ];
        }"""
    )
    assert positions[1] == pytest.approx(positions[0], abs=1)


def test_fraction_denominator_can_be_clicked_for_editing(page):
    page.evaluate(
        """() => model.set('blocks', [
          {id: 'text-1', source: '\\\\frac{1}{2}', line_id: 'text-1'},
        ])"""
    )
    page.wait_for_timeout(50)
    fraction_parts = page.evaluate(
        """() => {
          const fraction = document.querySelector('mfrac');
          return [...fraction.children].map(element => {
            const box = element.getBoundingClientRect();
            return {x: box.left + box.width / 2, y: box.top + box.height / 2};
          });
        }"""
    )
    numerator = page.evaluate(
        """() => {
          const element = document.querySelector('mfrac').children[0];
          const box = element.getBoundingClientRect();
          return {x: box.left + box.width / 2, y: box.top + box.height / 2};
        }"""
    )
    page.mouse.click(numerator["x"], numerator["y"])
    selection = page.locator("textarea").first.evaluate(
        "el => [el.selectionStart, el.selectionEnd]"
    )
    assert 6 <= selection[0] <= 7
    assert selection[0] == selection[1]

    page.locator("textarea").first.evaluate("el => el.blur()")
    page.wait_for_timeout(20)
    page.mouse.click(fraction_parts[1]["x"], fraction_parts[1]["y"])
    selection = page.locator("textarea").first.evaluate(
        "el => [el.selectionStart, el.selectionEnd]"
    )
    assert 8 <= selection[0] <= 10
    assert selection[0] == selection[1]


def test_clicking_again_in_active_fraction_keeps_source_editing(page):
    page.evaluate(
        """() => model.set('blocks', [
          {id: 'text-1', source: '\\\\frac{1}{2}', line_id: 'text-1'},
        ])"""
    )
    page.wait_for_timeout(50)
    numerator = page.evaluate(
        """() => {
          const element = document.querySelector('mfrac').children[0];
          const box = element.getBoundingClientRect();
          return {x: box.left + box.width / 2, y: box.top + box.height / 2};
        }"""
    )
    page.mouse.click(numerator["x"], numerator["y"])
    source = page.locator(".birdtracks-whiteboard-fraction-source")
    assert source.count() == 1

    source_box = source.bounding_box()
    assert source_box is not None
    page.mouse.click(
        source_box["x"] + source_box["width"] * 0.75,
        source_box["y"] + source_box["height"] / 2,
    )
    page.wait_for_timeout(20)
    assert page.locator(".birdtracks-whiteboard-fraction-source").count() == 1
    assert page.locator("mfrac").count() == 0


def test_caret_tracks_the_full_advance_after_a_last_operator(page):
    editor = page.locator("textarea").first
    editor.click()
    editor.press("End")
    page.keyboard.type("+")
    page.wait_for_timeout(50)
    first = page.evaluate(
        """() => {
          const editor = document.querySelector('textarea');
          const caret = document.querySelector('.birdtracks-whiteboard-caret');
          const symbol = [...document.querySelectorAll('[data-source-end]')]
            .filter(element => Number(element.dataset.sourceEnd) === editor.selectionStart)
            .sort((left, right) => (
              (Number(left.dataset.sourceEnd) - Number(left.dataset.sourceStart))
              - (Number(right.dataset.sourceEnd) - Number(right.dataset.sourceStart))
            ))[0];
          return {
            caret: caret.getBoundingClientRect().left,
            symbol: symbol.getBoundingClientRect().right,
            expected: symbol.getBoundingClientRect().right
              + Number.parseFloat(symbol.getAttribute('rspace'))
              * Number.parseFloat(getComputedStyle(symbol).fontSize),
          };
        }"""
    )
    assert first["caret"] == pytest.approx(first["expected"], abs=1)

    page.keyboard.type("x")
    page.wait_for_timeout(50)
    second = page.evaluate(
        """() => {
          const editor = document.querySelector('textarea');
          const caret = document.querySelector('.birdtracks-whiteboard-caret');
          const symbol = [...document.querySelectorAll('[data-source-end]')]
            .filter(element => Number(element.dataset.sourceEnd) === editor.selectionStart)
            .sort((left, right) => (
              (Number(left.dataset.sourceEnd) - Number(left.dataset.sourceStart))
              - (Number(right.dataset.sourceEnd) - Number(right.dataset.sourceStart))
            ))[0];
          return {
            caret: caret.getBoundingClientRect().left,
            symbol: symbol.getBoundingClientRect().right,
          };
        }"""
    )
    assert second["caret"] == pytest.approx(second["symbol"], abs=1)


def test_clicking_a_symbol_places_caret_on_its_left_or_right_edge(page):
    page.evaluate(
        """() => model.set('blocks', [
          {id: 'text-1', source: 'a+b', line_id: 'text-1'},
        ])"""
    )
    page.wait_for_timeout(50)
    plus = page.evaluate(
        """() => {
          const element = [...document.querySelectorAll('[data-source-start]')]
            .find(element => element.textContent === '+');
          const box = element.getBoundingClientRect();
          return {
            left: box.left,
            right: box.right,
            y: box.top + box.height / 2,
          };
        }"""
    )
    page.mouse.click(plus["left"] + 1, plus["y"])
    left = page.locator("textarea").first.evaluate(
        "el => [el.selectionStart, document.querySelector('.birdtracks-whiteboard-caret').getBoundingClientRect().left]"
    )
    assert left[0] == 1
    assert left[1] == pytest.approx(plus["left"], abs=1)

    page.mouse.click(plus["right"] - 1, plus["y"])
    right = page.locator("textarea").first.evaluate(
        "el => [el.selectionStart, document.querySelector('.birdtracks-whiteboard-caret').getBoundingClientRect().left]"
    )
    assert right[0] == 2
    assert right[1] == pytest.approx(plus["right"], abs=1)


def test_caret_aligns_after_operators_with_next_symbol(page):
    page.evaluate(
        """() => model.set('blocks', [
          {id: 'text-1', source: 'a=b+c-d', line_id: 'text-1'},
        ])"""
    )
    page.wait_for_timeout(50)
    positions = page.evaluate(
        """() => {
          const editor = document.querySelector('textarea');
          editor.focus();
          return [2, 4, 6].map(index => {
            editor.setSelectionRange(index, index);
            editor.dispatchEvent(new Event('select'));
            const caret = document.querySelector('.birdtracks-whiteboard-caret');
            const next = [...document.querySelectorAll('[data-source-start]')]
              .find(element => Number(element.dataset.sourceStart) === index);
            return {
              index,
              caret: caret.getBoundingClientRect().left,
              next: next.getBoundingClientRect().left,
            };
          });
        }"""
    )
    for position in positions:
        assert position["caret"] == pytest.approx(position["next"], abs=1)


@pytest.mark.parametrize('source', ['a = ', 'a + ', 'a - ', r'a + \frac{12}{34}'])
def test_caret_uses_visible_geometry_after_spaces_and_in_fraction(page, source):
    page.evaluate("source => model.set('blocks', [{id: 'text-1', source}])", source)
    editor = page.locator('textarea').first
    editor.focus()
    editor.press('End')
    if 'frac' in source:
        editor.press('ArrowLeft')
    assert page.locator('.birdtracks-whiteboard-caret:not([hidden])').is_visible()
    assert editor.evaluate('el => el.style.caretColor') == 'transparent'
    page.keyboard.type('5')
    metrics = editor.evaluate("""editor => {
      const caret = document.querySelector('.birdtracks-whiteboard-caret');
      const index = editor.selectionStart;
      const element = [...document.querySelectorAll('[data-source-start]')]
        .filter(el => Number(el.dataset.sourceStart) < index
          && Number(el.dataset.sourceEnd) >= index)
        .sort((a, b) => (Number(a.dataset.sourceEnd) - Number(a.dataset.sourceStart))
          - (Number(b.dataset.sourceEnd) - Number(b.dataset.sourceStart)))[0];
      const range = document.createRange();
      range.setStart(element.firstChild, index - Number(element.dataset.sourceStart));
      range.collapse(true);
      return {hidden: caret.hidden, native: editor.style.caretColor,
        actual: caret.getBoundingClientRect().left,
        expected: range.getBoundingClientRect().left};
    }""")
    assert not metrics['hidden']
    assert metrics['native'] == 'transparent'
    assert metrics['actual'] == pytest.approx(metrics['expected'], abs=1)


def test_trace_command_renders_upright(page):
    metrics = page.evaluate(
        """() => {
          const target = document.createElement('div');
          module.renderLatex('\\\\tr', target);
          const trace = target.querySelector('[data-source-start]');
          return {
            text: trace.textContent,
            variant: trace.getAttribute('mathvariant'),
          };
        }"""
    )
    assert metrics == {"text": "tr", "variant": "normal"}


def test_invalid_source_stays_editable_and_explains_error_on_hover(page):
    source = r"\unknown"
    page.evaluate(
        """source => model.set('blocks', [
          {id: 'text-1', source, line_id: 'text-1'},
        ])""",
        source,
    )
    page.wait_for_timeout(50)
    invalid = page.locator(".birdtracks-whiteboard-invalid-source")
    assert invalid.text_content() == source
    assert invalid.get_attribute("title") == "unsupported command \\unknown"
    assert page.locator(".birdtracks-whiteboard-rendered:not(.trailing-blank .birdtracks-whiteboard-rendered)").first.text_content() == source

    editor = page.locator("textarea").first
    editor.click()
    editor.press("End")
    editor.press("Backspace")
    assert editor.input_value() == r"\unknow"
    assert invalid.text_content() == r"\unknow"


def test_invalid_projector_source_recovers_after_deleting_stray_brace(page):
    source = r"A\def \birdtracks{"
    page.evaluate(
        """source => model.set('blocks', [
          {id: 'text-1', source, line_id: 'text-1'},
        ])""",
        source,
    )
    page.wait_for_timeout(50)
    assert page.locator(".birdtracks-whiteboard-invalid-source").count() == 1
    assert page.locator(".birdtracks-whiteboard-embedded-projector").count() == 1

    editor = page.locator("textarea").first
    editor.click()
    editor.press("End")
    editor.press("Backspace")
    assert editor.input_value() == r"A\def \birdtracks"
    assert page.locator(".birdtracks-whiteboard-invalid-source").count() == 0


def test_fraction_shows_source_while_editing_and_mathml_outside(page):
    source = r"\frac{1}{2} + x"
    inside = page.evaluate(
        """source => {
          const target = document.createElement('div');
          module.renderLatex(source, target, 0, source.indexOf('1'));
          return {text: target.textContent, fractions: target.querySelectorAll('mfrac').length};
        }""",
        source,
    )
    assert inside["text"].startswith(r"\frac{1}{2}")
    assert inside["fractions"] == 0

    outside = page.evaluate(
        """source => {
          const target = document.createElement('div');
          module.renderLatex(source, target, 0, source.length);
          return {text: target.textContent, fractions: target.querySelectorAll('mfrac').length};
        }""",
        source,
    )
    assert outside["fractions"] == 1
    assert "\\frac" not in outside["text"]

    incomplete = r"\frac{1}{"
    assert page.evaluate(
        """source => {
          const target = document.createElement('div');
          module.renderLatex(source, target, 0, source.length);
          return target.textContent;
        }""",
        incomplete,
    ) == incomplete

    assert page.evaluate(
        """source => module.flipNumericPrefactor(
          source, source.indexOf('birdtracks') - 1
        )""",
        r"\frac{1}{2}\birdtracks",
    ) == r"-\frac{1}{2}\birdtracks"


def test_fraction_numbers_match_inline_number_size_and_alignment(page):
    metrics = page.evaluate(
        """source => {
          const target = document.createElement('div');
          target.className = 'birdtracks-whiteboard-rendered';
          target.style.font = '24px Georgia';
          target.innerHTML = '';
          module.renderLatex(source, target);
          document.body.appendChild(target);
          const numbers = [...target.querySelectorAll('mn')];
          const fraction = target.querySelector('mfrac');
          const math = target.querySelector('math');
          return {
            outside: numbers[0].getBoundingClientRect().height,
            numerator: numbers[1].getBoundingClientRect().height,
            denominator: numbers[2].getBoundingClientRect().height,
            verticalAlign: getComputedStyle(math).verticalAlign,
            fractionTop: fraction.getBoundingClientRect().top,
            fractionBottom: fraction.getBoundingClientRect().bottom,
            lineTop: target.getBoundingClientRect().top,
            lineBottom: target.getBoundingClientRect().bottom,
          };
        }""",
        r"3 \frac{1}{2}",
    )
    assert metrics["numerator"] == pytest.approx(metrics["outside"], abs=1)
    assert metrics["denominator"] == pytest.approx(metrics["outside"], abs=1)
    assert metrics["verticalAlign"] == "middle"
    assert metrics["fractionTop"] > metrics["lineTop"]
    assert metrics["fractionBottom"] < metrics["lineBottom"]


@pytest.mark.parametrize('kind, command', [('projector', r'\birdtracks'), ('pair', r'\pair')])
def test_object_caret_uses_widget_edges_and_clicks_stay_put(page, kind, command):
    page.evaluate(r'''({kind, command}) => {
      model.set('blocks', [{id: 'text-1', source: command + ' + x ' + command}]);
      for (const anchor of document.querySelectorAll('.birdtracks-whiteboard-embedded-projector')) {
        anchor.style.width = '180px';
        anchor.style.height = '100px';
        anchor.innerHTML = '<span style="margin:30px">internal label</span>';
      }
    }''', {'kind': kind, 'command': command})
    editor = page.locator('textarea').first
    editor.focus()
    editor.evaluate('(el) => el.setSelectionRange(0, 0)')
    editor.press('ArrowRight')
    assert editor.evaluate('el => el.selectionStart') == len(command)
    geometry = page.evaluate('''() => ({
      edge: document.querySelector('.birdtracks-whiteboard-embedded-projector').getBoundingClientRect().right,
      caret: document.querySelector('.birdtracks-whiteboard-caret').getBoundingClientRect().left,
    })''')
    assert geometry['caret'] == pytest.approx(geometry['edge'], abs=1)
    editor.press('ArrowLeft')
    assert editor.evaluate('el => el.selectionStart') == 0
    plus_locator = page.locator('mo').filter(has_text='+').first
    playwright.expect(plus_locator).to_be_visible()
    plus = plus_locator.bounding_box()
    for _ in range(3):
        page.mouse.click(plus['x'] + 1, plus['y'] + plus['height'] / 2)
        assert editor.evaluate('el => el.selectionStart') == len(command) + 1
    page.keyboard.type('z')
    assert editor.input_value() == command + ' z+ x ' + command


@pytest.mark.parametrize('source', [r'a\oplus b\otimes c', r'{a\oplus b}\otimes c',
                                    r'\frac{a\oplus b}{c\otimes d}'])
def test_pair_icon_geometry_is_consistent_in_nested_latex(page, source):
    result = page.evaluate('''source => {
      const target = document.createElement('div');
      module.renderLatex(source, target);
      return [...target.querySelectorAll('.birdtracks-whiteboard-pair-operator')].map(icon => {
        const circle = icon.querySelector('circle');
        const radius = Number(circle.getAttribute('r'));
        return [...icon.querySelectorAll('line')].flatMap(line => [1, 2].map(end =>
          Math.hypot(Number(line.getAttribute('x' + end)) - 14,
            Number(line.getAttribute('y' + end)) - 14) - radius));
      });
    }''', source)
    assert len(result) == 2
    for endpoints in result:
        assert endpoints == pytest.approx([0, 0, 0, 0])


def test_reopened_projector_can_add_a_line_on_first_click(page, tmp_path):
    from birdtracks import Projector, Symmetriser, whiteboard
    from birdtracks.projectors.widget import projector_widget

    saved = projector_widget(Projector([Symmetriser((1, 2))]), embedded=True)
    path = tmp_path / 'reopened'
    document = whiteboard(path, debug=True)
    document.blocks = [{'id': 'text-1', 'source': r'\birdtracks'}]
    document.embedded_projectors[0].save_snapshot = {
        'revision': 1, **{key: getattr(saved, key) for key in (
            'graph', 'positions', 'port_orders', 'free_levels',
            'boundary_orders', 'effective_coefficient')},
    }
    reopened = whiteboard(path, debug=True)
    child = reopened.embedded_projectors[0]
    state = {key: value for key, value in child.get_state().items() if not key.startswith('_')}
    page.add_style_tag(content=(STATIC / 'projector-widget.css').read_text())
    source = base64.b64encode((STATIC / 'projector-widget.js').read_bytes()).decode()
    page.evaluate('''async ({state, source}) => {
      cleanup();
      for (const [key, value] of Object.entries(state)) childModel.set(key, value);
      childModel.set('mode', 'evaluate');
      const projector = await import('data:text/javascript;base64,' + source);
      model.set('blocks', [{id: 'text-1', source: '\\\\birdtracks'}]);
      window.cleanup = module.default.render({model, el: document.querySelector('#widget'),
        host: {getModel: async () => childModel,
          getWidget: async () => ({render: ({el}) => projector.default.render({model: childModel, el})})}});
    }''', {'state': state, 'source': source})
    control = page.locator('.birdtracks-add-line-control').first
    playwright.expect(control).to_be_visible()
    before = page.evaluate("childModel.get('graph').boundary_labels.length")
    control.click()
    page.evaluate("childModel.set('save_command', 1)")
    assert page.evaluate("childModel.get('save_snapshot').graph.boundary_labels.length") == before + 1


@pytest.mark.parametrize('command', [r'\birdtracks', r'\pair'])
def test_objects_select_and_delete_as_one_symbol(page, command):
    page.evaluate("source => model.set('blocks', [{id: 'text-1', source}])", 'x' + command + ' y')
    editor = page.locator('textarea').first
    editor.focus()
    editor.evaluate('el => el.setSelectionRange(1, 1)')
    editor.press('Shift+ArrowRight')
    assert editor.evaluate('el => [el.selectionStart, el.selectionEnd]') == [1, 1 + len(command)]
    editor.press('ArrowLeft')
    editor.press('Backspace')
    assert editor.input_value() == command + ' y'
    editor.press('Delete')
    assert editor.input_value() == ' y'


@pytest.mark.parametrize('leading', ['', r'A\oplus', r'A\otimes'])
def test_typing_pair_prefactor_updates_one_inline_coefficient(page, leading):
    from birdtracks import whiteboard
    from birdtracks.young_diagrams import PairExpression, PairTerm

    document = whiteboard(debug=True)
    document.blocks = [{'id': 'text-1', 'source': leading + r'\pair'}]
    child = document.embedded_pairs[0]
    child.pair_expression = PairExpression((PairTerm(unbarred=(2, 1), n0=3),)).state()
    state = {key: value for key, value in child.get_state().items() if not key.startswith('_')}
    source = base64.b64encode((STATIC / 'projector-widget.js').read_bytes()).decode()
    page.add_style_tag(content=(STATIC / 'projector-widget.css').read_text())
    page.evaluate(r'''async ({state, source, initialSource}) => {
      cleanup();
      for (const [key, value] of Object.entries(state)) childModel.set(key, value);
      const pair = await import('data:text/javascript;base64,' + source);
      model.set('embedded_projector_ids', []);
      model.set('embedded_projectors', []);
      model.set('embedded_pair_ids', ['text-1:pair:0']);
      model.set('embedded_pairs', ['pair-1']);
      model.set('blocks', [{id: 'text-1', source: initialSource}]);
      window.cleanup = module.default.render({model, el: document.querySelector('#widget'),
        host: {getModel: async () => childModel,
          getWidget: async () => ({render: ({el}) => pair.default.render({model: childModel, el})})}});
    }''', {'state': state, 'source': source, 'initialSource': leading + r'\pair'})
    editor = page.locator('textarea').first
    editor.focus()
    editor.evaluate('(el, index) => el.setSelectionRange(index, index)', len(leading))
    page.keyboard.type('2')
    assert editor.input_value() == leading + r'2\pair'
    document.blocks = page.evaluate("model.get('blocks')")
    page.evaluate("state => childModel.set('pair_expression', state)", child.pair_expression)
    rendered = page.locator('[data-block-id="text-1"] .birdtracks-whiteboard-rendered')
    assert rendered.locator('mo, mn').count() == 0
    assert rendered.locator('.birdtracks-young-prefactor-value').all_text_contents() == ['2']
    assert child.pair_expression['terms'][0]['unbarred'] == [2, 1]


def test_projector_ctrl_state_clears_when_editor_stops_keyup(page):
    from birdtracks import Projector, Symmetriser
    from birdtracks.projectors.widget import projector_widget

    child = projector_widget(Projector([Symmetriser((1, 2))]), embedded=True, mode='create')
    state = {key: value for key, value in child.get_state().items() if not key.startswith('_')}
    source = base64.b64encode((STATIC / 'projector-widget.js').read_bytes()).decode()
    page.add_style_tag(content=(STATIC / 'projector-widget.css').read_text())
    page.evaluate('''async ({state, source}) => {
      cleanup();
      for (const [key, value] of Object.entries(state)) childModel.set(key, value);
      const projector = await import('data:text/javascript;base64,' + source);
      const host = document.querySelector('#widget');
      host.replaceChildren();
      window.cleanup = projector.default.render({model: childModel, el: host});
      const input = document.createElement('input');
      input.id = 'nested-editor';
      input.addEventListener('keyup', event => event.stopPropagation());
      host.appendChild(input);
    }''', {'state': state, 'source': source})
    page.locator('#nested-editor').focus()
    page.keyboard.down('Control')
    assert page.locator('svg.ctrl-active').count() == 1
    assert page.get_by_role('button', name='Remove bottom line', exact=True).count() == 1
    page.keyboard.up('Control')
    assert page.locator('svg.ctrl-active').count() == 0
    control = page.get_by_role('button', name='Add bottom line', exact=True)
    assert control.count() == 1
    bounds = control.bounding_box()
    page.mouse.click(bounds['x'] + bounds['width'] / 2, bounds['y'] + bounds['height'] / 2)
    page.evaluate("childModel.set('save_command', 1)")
    assert len(page.evaluate("childModel.get('save_snapshot').graph.nodes[0].labels")) == 3
    page.keyboard.down('Control')
    page.evaluate("window.dispatchEvent(new Event('blur'))")
    assert page.locator('svg.ctrl-active').count() == 0
    assert page.get_by_role('button', name='Add bottom line', exact=True).count() == 1
    page.keyboard.up('Control')


@pytest.mark.parametrize('typed, completed', [
    (r'\op', r'\oplus '), (r'\ot', r'\otimes '), (r'\d', r'\def '),
    (r'\oplus', r'\oplus '), (r'\otimes', r'\otimes '), (r'\def', r'\def '),
])
def test_operator_completion_inserts_a_trailing_space(page, typed, completed):
    page.evaluate("() => model.set('blocks', [{id: 'text-1', source: ''}])")
    editor = page.locator('textarea').first
    editor.fill(typed)
    editor.press('End')
    editor.press('Tab')
    assert editor.input_value() == completed
    page.keyboard.type('2')
    assert editor.input_value() == completed + '2'


@pytest.mark.parametrize('kind', ['symmetriser', 'antisymmetriser'])
@pytest.mark.parametrize('edge', ['top', 'bottom'])
@pytest.mark.parametrize('size', [2, 3])
def test_two_line_tear_sends_the_double_click_request(page, kind, edge, size):
    from birdtracks import Antisymmetriser, Projector, Symmetriser
    from birdtracks.projectors.widget import projector_widget

    operator = Symmetriser if kind == 'symmetriser' else Antisymmetriser
    child = projector_widget(Projector([operator(tuple(range(1, size + 1)))]), embedded=True)
    state = {key: value for key, value in child.get_state().items() if not key.startswith('_')}
    source = base64.b64encode((STATIC / 'projector-widget.js').read_bytes()).decode()
    page.add_style_tag(content=(STATIC / 'projector-widget.css').read_text())
    page.evaluate('''async ({state, source}) => {
      cleanup();
      for (const [key, value] of Object.entries(state)) childModel.set(key, value);
      childModel.set('active_line', true);
      const projector = await import('data:text/javascript;base64,' + source);
      const host = document.querySelector('#widget');
      host.replaceChildren();
      window.cleanup = projector.default.render({model: childModel, el: host});
    }''', {'state': state, 'source': source})
    page.get_by_role('button', name=f'Recursively expand from the {edge} line').dispatch_event('pointerdown')
    tear = page.evaluate("({...childModel.get('expand_node_request'), revision: 0})")
    page.locator(f'.birdtracks-{kind}').first.dblclick()
    full = page.evaluate("({...childModel.get('expand_node_request'), revision: 0})")
    if size == 2:
        assert tear == full
        assert 'recursive_edge' not in tear
    else:
        assert tear == {**full, 'recursive_edge': edge}
