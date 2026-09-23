"""Browser gestures against the shipped widget module (optional Playwright)."""

import base64
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
STATIC = Path(__file__).parents[2] / "src/birdtracks/projectors/static"


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
        page.set_content('<div class="birdtracks-calculator-app birdtracks-projector-sum"><div id="widget"></div></div>')
        page.add_style_tag(content=(STATIC / "projector-widget.css").read_text())
        source = base64.b64encode((STATIC / "projector-widget.js").read_bytes()).decode()
        page.evaluate("""async source => {
          window.module = await import('data:text/javascript;base64,' + source);
          const values = {mode: 'create', group_id: 'test', widget_role: 'toolbar',
            create_kind: 'birdtracks', trace_enabled: false,
            pair_expression: {version: 1, kind: 'sum', terms: [
              {kind: 'pair', barred: [], unbarred: [], coefficient: '1', n0: '0'}]},
            pair_drawing_state: {}};
          const listeners = new Map();
          window.model = {
            get: name => values[name],
            set(name, value) { values[name] = value;
              for (const fn of listeners.get('change:' + name) || []) fn(); },
            on(names, fn) { for (const name of names.split(' ')) {
              if (!listeners.has(name)) listeners.set(name, new Set());
              listeners.get(name).add(fn); } },
            off(names, fn) { for (const name of names.split(' ')) listeners.get(name)?.delete(fn); },
            save_changes() {},
          };
          window.cleanup = window.module.default.render({model, el: document.querySelector('#widget')});
        }""", source)
        yield page
        page.evaluate("window.cleanup()")
        browser.close()
        assert not errors


def young(page):
    page.get_by_role("button", name="Switch to Young diagrams / tableaux", exact=True).click()


def test_app_pair_workspace_uses_embedded_padding(page):
    young(page)
    workspace = page.locator(".birdtracks-young-workspace")
    assert workspace.evaluate("el => getComputedStyle(el).paddingTop") == "0px"
    assert workspace.evaluate("el => getComputedStyle(el).paddingBottom") == "0px"


def test_pair_widget_role_renders_editor_without_calculator_toolbar(page):
    page.evaluate("""() => {
      window.cleanup();
      document.querySelector('#widget').replaceChildren();
      model.set('widget_role', 'pair');
      model.set('pair_expression', {version: 1, kind: 'sum', terms: [
        {kind: 'pair', barred: [], unbarred: [1], coefficient: '1', n0: '1'}]});
      window.cleanup = window.module.default.render({
        model, el: document.querySelector('#widget'),
      });
    }""")
    assert page.locator(".birdtracks-young-workspace").filter(visible=True).count() == 1
    assert page.locator(".birdtracks-creator-toolbar").count() == 0
    assert page.locator(".birdtracks-young-term").count() == 1


def term(page):
    return page.evaluate("model.get('pair_expression').terms[0]")


def point(page, row, column):
    return page.locator('[data-term-index="0"]').evaluate("""(svg, cell) => {
      const axis = Number(svg.querySelector('line').getAttribute('x1'));
      const p = new DOMPoint(axis + (cell[1] + .5) * 30, 45 + (cell[0] + .5) * 30)
        .matrixTransform(svg.getScreenCTM());
      return {x: p.x, y: p.y};
    }""", [row, column])


def click_cell(page, row, column, double=False):
    p = point(page, row, column)
    if double:
        page.mouse.dblclick(p["x"], p["y"])
    else:
        page.mouse.click(p["x"], p["y"])


def test_create_label_undo_and_switch(page):
    young(page)
    assert page.get_by_role("button", name="Insert negative term", exact=True).is_hidden()
    assert page.get_by_role("button", name="Add direct-sum term", exact=True).locator("svg circle").count() == 1
    click_cell(page, 0, 0)
    click_cell(page, 0, 1)
    assert term(page)["unbarred"] == [2]
    click_cell(page, 0, 0, double=True)
    page.get_by_role("textbox", name="Tableau integer label").fill("1")
    page.get_by_role("textbox", name="Tableau integer label").press("Enter")
    assert term(page)["unbarred"] == [2]  # Interior cells can be labeled without changing shape.
    assert term(page)["labels"][0]["value"] == "1"
    page.get_by_role("button", name="Undo", exact=True).click()
    assert term(page)["unbarred"] == [2]
    assert not term(page).get("labels")
    page.get_by_role("button", name="Switch to Birdtracks", exact=True).click()
    assert page.get_by_role("button", name="Insert negative term", exact=True).is_visible()
    young(page)
    assert term(page)["unbarred"] == [2]


def test_drag_corner_and_edit_exact_integer(page):
    young(page)
    for row, col in [(0, 0), (0, 1), (1, 0)]:
        click_cell(page, row, col)
    start, end = point(page, 0, 1), point(page, 2, 0)
    page.mouse.move(**start)
    page.mouse.down()
    page.mouse.move(**end, steps=5)
    page.mouse.up()
    assert term(page)["unbarred"] == [1, 1, 1]
    panel = page.locator('[data-term-index="0"]')
    panel.click(modifiers=["Control"])
    coefficient = page.get_by_role("textbox", name="Prefactor")
    coefficient.fill("1/2")
    page.get_by_role("textbox", name="Prefactor").press("Enter")
    assert term(page)["coefficient"] == "1"
    coefficient.fill("-123456789012345678901234567890")
    page.get_by_role("textbox", name="Term N0").fill("5")
    page.get_by_role("textbox", name="Prefactor").press("Enter")
    assert term(page)["coefficient"] == "-123456789012345678901234567890"
    assert term(page)["n0"] == "5"
    page.get_by_role("button", name="Add direct-sum term", exact=True).click()
    assert page.locator(".birdtracks-young-term").count() == 2


def test_geometry_matches_standalone_renderer(page):
    from birdtracks.young_diagrams import PairTerm

    pytest.importorskip("pair_multiplication")
    value = PairTerm((3, 1), (2, 1), 1, 4)
    cells = page.evaluate("term => window.module.youngCells(term)", value.state())
    expected = sorted((c["row"], c["column"] - 3, c["bullet"]) for c in value.drawing()["cells"])
    assert sorted((c["row"], c["column"], c["side"] == "barred") for c in cells) == expected


def test_double_click_empty_position_adds_box_and_opens_label_editor(page):
    young(page)
    click_cell(page, 0, 0, double=True)
    assert term(page)["unbarred"] == [1]
    assert term(page)["barred"] == []
    assert page.get_by_role("textbox", name="Tableau integer label").is_visible()


def test_invalid_drag_and_low_n0_preserve_term(page):
    young(page)
    for row, col in [(0, 0), (0, 1), (1, 0)]:
        click_cell(page, row, col)
    before = term(page)
    start, end = point(page, 0, 0), point(page, 2, 0)
    page.mouse.move(**start)
    page.mouse.down()
    page.mouse.move(**end, steps=5)
    page.mouse.up()
    assert term(page) == before
    page.locator('[data-term-index="0"]').click(modifiers=["Control"])
    page.get_by_role("textbox", name="Term N0").fill("1")
    page.get_by_role("textbox", name="Prefactor").press("Enter")
    assert term(page) == before


def test_quick_clicks_on_different_cells_add_both_boxes(page):
    young(page)
    click_cell(page, 0, 0)
    target = point(page, 0, 1)
    event = {"clientX": target["x"], "clientY": target["y"], "detail": 2}
    # A browser may count this as the second click on the SVG, despite the
    # grid position changing. Dispatch one click, not Playwright's two-click gesture.
    page.locator('[data-term-index="0"]').dispatch_event("click", event)
    page.locator('[data-term-index="0"]').dispatch_event("dblclick", event)
    assert term(page)["unbarred"] == [2]
    assert term(page)["barred"] == []


def test_kernel_geometry_reply_during_click_does_not_drop_addition(page):
    young(page)
    target = point(page, 0, 0)
    page.mouse.move(**target)
    page.mouse.down()
    page.evaluate("model.set('pair_drawing_state', {expression:model.get('pair_expression'),drawings:[]})")
    page.mouse.up()
    assert term(page)["unbarred"] == [1]


def test_guide_dots_track_pair_without_extra_bottom_row(page):
    young(page)
    dots = page.locator(".birdtracks-young-grid")
    assert dots.count() == 2
    assert page.get_by_text("Click below to start", exact=True).count() == 0
    assert page.locator(".birdtracks-young-term").evaluate(
        "el => getComputedStyle(el).borderTopWidth"
    ) == "0px"
    assert page.locator(".birdtracks-calculator-app").evaluate(
        "el => getComputedStyle(el).borderTopWidth"
    ) == "0px"
    click_cell(page, 0, 0)
    assert dots.count() == 3
    click_cell(page, 0, 1)
    assert dots.count() == 4
    click_cell(page, 1, 0)
    assert dots.count() == 8
    page.get_by_role("button", name="Undo", exact=True).click()
    assert dots.count() == 4


def test_only_addable_cells_receive_the_hover_highlight(page):
    young(page)
    click_cell(page, 0, 0)
    valid = page.locator('[data-grid-row="0"][data-grid-column="1"]')
    invalid = page.locator('[data-grid-row="1"][data-grid-column="1"]')
    lower_row = page.locator('[data-grid-row="1"][data-grid-column="0"]')

    assert "birdtracks-young-cell-target-hidden" not in (valid.get_attribute("class") or "")
    assert "birdtracks-young-cell-target-hidden" in (invalid.get_attribute("class") or "")
    assert "birdtracks-young-cell-target-hidden" not in (
        lower_row.get_attribute("class") or ""
    )


@pytest.mark.parametrize("x_fraction", [0.05, 0.5, 0.95])
def test_empty_grid_cells_are_clickable_across_the_full_highlight(page, x_fraction):
    young(page)
    target = point(page, 0, 0)
    assert page.evaluate("p => document.elementFromPoint(p.x, p.y).classList.contains('birdtracks-young-cell-target')", target)
    page.locator('[data-grid-row="0"][data-grid-column="0"]').click(
        position={"x": 30 * x_fraction, "y": 15}
    )
    assert term(page)["unbarred"] == [1]


def test_right_click_deletes_boxes_and_antiboxes(page):
    young(page)
    click_cell(page, 0, 0)
    page.locator('.birdtracks-young-box[data-side="unbarred"]').click(button="right")
    playwright.expect(page.locator(".birdtracks-young-box")).to_have_count(0)
    assert term(page)["unbarred"] == []
    click_cell(page, 0, -1)
    assert term(page)["barred"] == [1]
    page.locator('.birdtracks-young-box[data-side="barred"]').click(button="right")
    playwright.expect(page.locator(".birdtracks-young-box")).to_have_count(0)
    assert term(page)["barred"] == []
    page.get_by_role("button", name="Undo", exact=True).click()
    assert term(page)["barred"] == [1]


def test_double_click_labels_without_delayed_deletion(page):
    young(page)
    click_cell(page, 0, 0)
    page.locator(".birdtracks-young-box").dblclick(delay=150)
    page.get_by_role("textbox", name="Tableau integer label").fill("7")
    page.get_by_role("textbox", name="Tableau integer label").press("Enter")
    page.wait_for_timeout(550)
    assert term(page)["barred"] == []
    assert term(page)["unbarred"] == [1]
    assert page.locator(".birdtracks-young-label").text_content() == "7"


def test_antibox_labels_are_barred_integers(page):
    young(page)
    click_cell(page, 0, -1)
    page.locator(".birdtracks-young-box").dblclick()
    entry = page.get_by_role("textbox", name="Tableau integer label")
    entry.fill("1/2")
    page.get_by_role("textbox", name="Tableau integer label").press("Enter")
    assert not term(page).get("labels")
    entry.fill("-123456789012345678901234567890")
    page.get_by_role("textbox", name="Tableau integer label").press("Enter")
    assert term(page)["labels"] == [{"side": "barred", "row": 0, "column": 0,
                                     "value": "-123456789012345678901234567890"}]
    assert page.locator(".birdtracks-young-label-bar").count() == 1
    assert page.locator(".birdtracks-young-antibox").count() == 0
    page.locator(".birdtracks-young-box").dblclick()
    entry.fill("")
    page.get_by_role("textbox", name="Tableau integer label").press("Enter")
    assert not term(page).get("labels")
    assert page.locator(".birdtracks-young-antibox").count() == 1


def test_label_moves_with_cell_and_is_removed_on_delete(page):
    young(page)
    for row, col in [(0, 0), (0, 1), (1, 0)]:
        click_cell(page, row, col)
    click_cell(page, 0, 1, double=True)
    page.get_by_role("textbox", name="Tableau integer label").fill("3")
    page.get_by_role("textbox", name="Tableau integer label").press("Enter")
    start, end = point(page, 0, 1), point(page, 2, 0)
    page.mouse.move(**start)
    page.mouse.down()
    page.mouse.move(**end, steps=5)
    page.mouse.up()
    assert term(page)["labels"] == [{"side": "unbarred", "row": 2, "column": 0, "value": "3"}]
    page.locator('.birdtracks-young-box[data-row="2"][data-column="0"]').click(
        button="right"
    )
    playwright.expect(page.locator(".birdtracks-young-label")).to_have_count(0)
    assert not term(page).get("labels")


def test_interior_cell_click_keeps_partition_valid(page):
    young(page)
    click_cell(page, 0, 0)
    click_cell(page, 0, 1)
    page.locator('.birdtracks-young-box[data-column="0"]').click()
    playwright.expect(page.locator(".birdtracks-canvas-status")).to_have_count(0)
    assert term(page)["unbarred"] == [2]


def test_prefactor_deletes_term_and_undo_restores_it(page):
    young(page)
    click_cell(page, 0, 0)
    page.get_by_role("button", name="Add direct-sum term", exact=True).click()
    page.get_by_role("button", name="Prefactor of term 1", exact=True).click(button="right")
    assert page.locator(".birdtracks-young-term").count() == 1
    assert term(page)["unbarred"] == []
    page.get_by_role("button", name="Undo", exact=True).click()
    assert page.locator(".birdtracks-young-term").count() == 2
    assert term(page)["unbarred"] == [1]
    page.get_by_role("button", name="Prefactor of term 1", exact=True).click(modifiers=["Control"])
    assert page.get_by_role("textbox", name="Prefactor").is_visible()
    assert page.locator(".birdtracks-young-term").count() == 2


def test_delete_last_term_then_add_again(page):
    young(page)
    page.get_by_role("button", name="Prefactor of term 1", exact=True).click(button="right")
    assert page.evaluate("model.get('pair_expression').terms") == []
    assert page.locator(".birdtracks-young-zero").inner_text() == "0"
    page.get_by_role("button", name="Add direct-sum term", exact=True).click()
    click_cell(page, 0, 0)
    assert term(page)["unbarred"] == [1]


def test_direct_sum_lines_touch_the_circle(page):
    young(page)
    page.get_by_role("button", name="Add direct-sum term", exact=True).click()
    icons = page.locator(".birdtracks-direct-sum-icon")
    assert icons.count() == 2  # toolbar and expression separator
    assert icons.evaluate_all("""icons => icons.every(icon => {
      const circle = icon.querySelector('circle');
      const cx = Number(circle.getAttribute('cx')), cy = Number(circle.getAttribute('cy'));
      const r = Number(circle.getAttribute('r'));
      return [...icon.querySelectorAll('line')].every(line => [1,2].every(i =>
        Math.hypot(Number(line.getAttribute('x'+i))-cx, Number(line.getAttribute('y'+i))-cy) === r));
    })""")


def test_prefactor_double_click_edits_in_place_and_right_click_deletes(page):
    young(page)
    prefactor = page.get_by_role("button", name="Prefactor of term 1", exact=True)
    prefactor.click()
    assert page.locator(".birdtracks-young-term").count() == 1
    bounds = page.locator(".birdtracks-young-prefactor-value").bounding_box()
    prefactor.dblclick()
    entry = page.get_by_role("textbox", name="Prefactor", exact=True)
    edited_bounds = entry.bounding_box()
    assert abs(edited_bounds["x"] - bounds["x"]) < 1
    assert abs(edited_bounds["y"] - bounds["y"]) < 1
    entry.fill("12")
    page.get_by_role("textbox", name="Term N0").fill("4")
    page.locator(".birdtracks-creator-toolbar").click(position={"x": 2, "y": 2})
    assert term(page)["coefficient"] == "12"
    assert term(page)["n0"] == "4"
    prefactor.click(button="right")
    assert page.locator(".birdtracks-young-term").count() == 0


def test_label_edits_inside_cell_and_applies_on_blur(page):
    young(page)
    click_cell(page, 0, -1)
    cell = page.locator(".birdtracks-young-box")
    bounds = cell.bounding_box()
    cell.dblclick()
    entry = page.get_by_role("textbox", name="Tableau integer label")
    edited_bounds = entry.bounding_box()
    assert edited_bounds["x"] >= bounds["x"]
    assert edited_bounds["x"] + edited_bounds["width"] <= bounds["x"] + bounds["width"]
    entry.fill("8")
    page.locator(".birdtracks-creator-toolbar").click(position={"x": 2, "y": 2})
    assert term(page)["labels"][0]["value"] == "8"
    assert page.locator(".birdtracks-young-label-bar").count() == 1


def test_lower_grid_rows_add_boxes_and_antiboxes(page):
    young(page)
    click_cell(page, 1, 0)  # Starting in the lower guide row aligns the first box.
    assert term(page)["unbarred"] == [1]
    click_cell(page, 1, 0)
    assert term(page)["unbarred"] == [1, 1]
    click_cell(page, 2, -1)
    assert term(page)["barred"] == [1]
    click_cell(page, 3, -1)
    assert term(page)["barred"] == [1, 1]


def test_divider_extends_half_a_box_past_pair(page):
    young(page)
    click_cell(page, 0, 0)
    click_cell(page, 1, -1)
    assert page.locator(".birdtracks-young-axis").evaluate("""axis => {
      const cells = [...axis.closest('svg').querySelectorAll('.birdtracks-young-box')];
      const top = Math.min(...cells.map(c => Number(c.getAttribute('y'))));
      const bottom = Math.max(...cells.map(c => Number(c.getAttribute('y')) + Number(c.getAttribute('height'))));
      return Number(axis.getAttribute('y1')) === top - 15 && Number(axis.getAttribute('y2')) === bottom + 15;
    }""")


def test_new_bottom_antibox_row_preserves_existing_label_position(page):
    young(page)
    page.evaluate("""model.set('pair_expression', {version:1,kind:'sum',terms:[
      {kind:'pair',barred:[1],unbarred:[],coefficient:'1',n0:'1',
       labels:[{side:'barred',row:0,column:0,value:'9'}]}]})""")
    before = page.locator(".birdtracks-young-label").bounding_box()
    click_cell(page, 1, -1)
    assert term(page)["barred"] == [1, 1]
    assert term(page)["labels"][0]["row"] == 1
    after = page.locator(".birdtracks-young-label").bounding_box()
    assert after["y"] == before["y"]


@pytest.mark.parametrize('x_fraction', [0.25, 0.5, 0.75])
def test_permutation_first_double_click_after_evaluate(page, x_fraction):
    from birdtracks import Projector, PermutationNode, Permutation
    from birdtracks.projectors.widget import projector_widget

    widget = projector_widget(Projector(
        [PermutationNode(Permutation.identity(), support=[1])],
        in_direction='right', out_direction='left',
    ), mode='evaluate')
    values = {k: v for k, v in widget.get_state().items() if not k.startswith('_')}
    page.evaluate("""values => {
      cleanup(); document.querySelector('#widget').replaceChildren();
      const listeners = new Map();
      window.model = {model_id:'permutation', get:n=>values[n],
        set(n,v) { if (values[n] === v) return; values[n]=v;
          for(const f of listeners.get('change:'+n)||[])f(); },
        on(ns,f) { for(const n of ns.split(' ')) { if(!listeners.has(n))listeners.set(n,new Set()); listeners.get(n).add(f); } },
        off(ns,f) { for(const n of ns.split(' '))listeners.get(n)?.delete(f); },save_changes() {}};
      window.cleanup=window.module.default.render({model,el:document.querySelector('#widget')});
      model.set('mode', 'create');
    }""", values)
    page.wait_for_timeout(50)
    p = page.locator('#widget .birdtracks-canvas-viewport svg').evaluate("""(svg, fraction) => {
      const g=model.get('graph').geometry;
      const x=g.left_boundary + (g.right_boundary-g.left_boundary)*fraction;
      return new DOMPoint(x, g.top_margin + g.level_spacing*.3)
        .matrixTransform(svg.getScreenCTM()).toJSON();
    }""", x_fraction)
    page.mouse.dblclick(p['x'], p['y'], delay=100)
    assert page.locator('.birdtracks-symmetriser').count() == 1
    page.evaluate("document.querySelector('.birdtracks-save-button').click()")
    graph = page.evaluate("model.get('graph')")
    assert len(graph['external_inputs']) == 2
    assert len(graph['nodes']) == 1


def test_leftmost_operator_input_ports_can_be_permuted_in_create_mode(page):
    from birdtracks import Projector, Symmetriser
    from birdtracks.projectors.widget import projector_widget

    widget = projector_widget(Projector([Symmetriser({1, 2})]), mode='create')
    values = {k: v for k, v in widget.get_state().items() if not k.startswith('_')}
    page.evaluate("""values => {
      cleanup(); document.querySelector('#widget').replaceChildren();
      const listeners = new Map();
      window.model = {model_id:'leftmost', get:n=>values[n],
        set(n,v) { values[n]=v; for(const f of listeners.get('change:'+n)||[])f(); },
        on(ns,f) { for(const n of ns.split(' ')) { if(!listeners.has(n))listeners.set(n,new Set()); listeners.get(n).add(f); } },
        off(ns,f) { for(const n of ns.split(' '))listeners.get(n)?.delete(f); },save_changes(){}};
      window.cleanup=window.module.default.render({model,el:document.querySelector('#widget')});
    }""", values)
    input_ports = page.evaluate("""() => [...document.querySelectorAll('.birdtracks-creator-port')]
      .map(port => ({endpoint: JSON.parse(decodeURIComponent(port.dataset.endpoint)),
        box: port.getBoundingClientRect()}))
      .filter(item => item.endpoint.type === 'port' && item.endpoint.side === 'input')""")
    assert len(input_ports) == 2
    source, target = input_ports
    page.mouse.move(source['box']['x'] + source['box']['width'] / 2,
                    source['box']['y'] + source['box']['height'] / 2)
    page.mouse.down()
    page.mouse.move(target['box']['x'] + target['box']['width'] / 2,
                    target['box']['y'] + target['box']['height'] / 2, steps=4)
    page.mouse.up()
    page.locator('.birdtracks-save-button').evaluate("button => button.click()")
    graph = page.evaluate("model.get('graph')")
    assert graph['nodes'][0]['input_labels'] == [2, 1]


def test_birdtrack_fraction_edits_in_place(page):
    pytest.importorskip("anywidget")
    from fractions import Fraction
    from birdtracks import Projector, Symmetriser
    from birdtracks.projectors.widget import projector_widget

    widget = projector_widget(Projector([Symmetriser({1, 2})], coefficient=Fraction(2, 3)), mode="create")
    values = {key: value for key, value in widget.get_state().items() if not key.startswith("_")}
    page.evaluate("""values => {
      window.cleanup(); document.querySelector('#widget').replaceChildren();
      const listeners = new Map();
      window.model = {model_id:'fraction', get:n=>values[n],
        set(n,v) { values[n]=v; for(const f of listeners.get('change:'+n)||[])f(); },
        on(ns,f) { for(const n of ns.split(' ')) { if(!listeners.has(n))listeners.set(n,new Set()); listeners.get(n).add(f); } },
        off(ns,f) { for(const n of ns.split(' '))listeners.get(n)?.delete(f); },save_changes() {}};
      window.cleanup=window.module.default.render({model,el:document.querySelector('#widget')});
    }""", values)
    denominator = page.locator(".birdtracks-fraction-number").last
    bounds = denominator.bounding_box()
    denominator.dblclick()
    entry = page.get_by_role("textbox", name="Denominator", exact=True)
    assert abs(entry.bounding_box()["x"] - bounds["x"]) < 1
    entry.fill("5")
    page.locator("body").click(position={"x": 1000, "y": 600})
    assert page.evaluate("model.get('graph').coefficient.denominator") == "5"


def test_brackets_tensor_and_resizing(page):
    young(page)
    panel = page.locator('[data-term-index="0"]').bounding_box()
    page.mouse.move(panel["x"] + 1, panel["y"] + panel["height"] / 2)
    page.get_by_role("button", name="Add left bracket", exact=True).click()
    panel = page.locator('[data-term-index="0"]').bounding_box()
    page.mouse.move(panel["x"] + panel["width"] - 1, panel["y"] + panel["height"] / 2)
    page.keyboard.press("]")
    page.get_by_role("button", name="Add tensor-product factor", exact=True).click()
    assert page.evaluate("model.get('pair_expression').syntax") == ["(", "pair", ")", "tensor", "pair"]
    brackets = page.locator(".birdtracks-young-bracket")
    assert brackets.count() == 2
    assert brackets.first.bounding_box()["height"] == 30
    page.evaluate("""() => {
      const next = structuredClone(model.get('pair_expression'));
      next.terms[1].unbarred = [1, 1, 1]; next.terms[1].n0 = '3';
      model.set('pair_expression', next);
    }""")
    assert brackets.first.bounding_box()["height"] == 90
    bounds = brackets.first.bounding_box()
    diagram = page.locator('[data-term-index="1"]').bounding_box()
    assert abs(bounds["y"] + bounds["height"] / 2 - diagram["y"] - diagram["height"] / 2) < 1
    page.locator('[aria-label="Left bracket"]').click(button="right")
    assert brackets.count() == 1
    page.get_by_role("button", name="Undo", exact=True).click()
    assert brackets.count() == 2
    page.get_by_role("button", name="Switch to Birdtracks", exact=True).click()
    assert page.get_by_role("button", name="Add left bracket", exact=True).is_hidden()


def test_tools_append_regardless_of_mouse_and_selection(page):
    young(page)
    page.get_by_role("button", name="Add direct-sum term", exact=True).click()
    first = page.locator('[data-term-index="0"]').bounding_box()
    page.mouse.click(first['x'] + 1, first['y'] + 1)
    page.mouse.move(first['x'] + 1, first['y'] + first['height'] / 2)
    assert page.locator('.birdtracks-young-insertion-marker').is_hidden()
    page.keyboard.press('[')
    page.get_by_role('button', name='Add tensor-product factor', exact=True).click()
    page.keyboard.press(']')
    page.get_by_role('button', name='Add direct-sum term', exact=True).click()
    assert page.evaluate("model.get('pair_expression').syntax") == [
        'pair', 'sum', '(', 'pair', 'tensor', 'pair', ')', 'sum', 'pair']


def test_drag_term_across_brackets_and_undo(page):
    young(page)
    page.evaluate("""() => {
      const next = structuredClone(model.get('pair_expression'));
      next.terms = ['2', '3', '5'].map(coefficient => ({...structuredClone(next.terms[0]), coefficient}));
      next.terms[0].unbarred = [1]; next.terms[0].n0 = '4';
      next.terms[0].labels = [{side: 'unbarred', row: 0, column: 0, value: '7'}];
      next.syntax = ['pair', 'sum', '(', 'pair', 'sum', 'pair', ')'];
      model.set('pair_expression', next);
    }""")
    original = page.evaluate("model.get('pair_expression')")
    source = page.locator('[aria-label="Prefactor of term 1"]').bounding_box()
    target = page.locator('[aria-label="Right bracket"]').bounding_box()
    page.mouse.move(source['x'] + source['width'] / 2, source['y'] + source['height'] / 2)
    page.mouse.down()
    page.mouse.move(target['x'] + 1, target['y'] + target['height'] / 2, steps=12)
    page.mouse.up()
    moved = page.evaluate("model.get('pair_expression')")
    assert moved['syntax'] == ['(', 'pair', 'sum', 'pair', 'sum', 'pair', ')']
    assert [term['coefficient'] for term in moved['terms']] == ['3', '5', '2']
    assert moved['terms'][2] == original['terms'][0]
    # Pull the same term back out, to the right of the closing bracket.
    source = page.locator('[aria-label="Prefactor of term 3"]').bounding_box()
    target = page.locator('[aria-label="Right bracket"]').bounding_box()
    page.mouse.move(source['x'] + source['width'] / 2, source['y'] + source['height'] / 2)
    page.mouse.down()
    page.mouse.move(target['x'] + target['width'] - 1, target['y'] + target['height'] / 2, steps=12)
    page.mouse.up()
    assert page.evaluate("model.get('pair_expression').syntax") == ['(', 'pair', 'sum', 'pair', ')', 'sum', 'pair']
    page.get_by_role('button', name='Undo', exact=True).click()
    assert page.evaluate("model.get('pair_expression')") == moved
    page.get_by_role('button', name='Undo', exact=True).click()
    assert page.evaluate("model.get('pair_expression')") == original


@pytest.mark.parametrize('operator', ['Add tensor-product factor', 'Add direct-sum term'])
def test_open_bracket_wraps_pending_constructor(page, operator):
    young(page)
    click_cell(page, 0, 0)
    page.get_by_role('button', name=operator, exact=True).click()
    before = page.evaluate("model.get('pair_expression')")
    page.keyboard.press('(')
    state = page.evaluate("model.get('pair_expression')")
    expected_operator = 'tensor' if 'tensor' in operator else 'sum'
    assert state['syntax'] == ['pair', expected_operator, '(', 'pair']
    assert state['terms'] == before['terms']
    page.keyboard.press('(')
    page.keyboard.press(')')
    assert page.evaluate("model.get('pair_expression').syntax") == ['pair', expected_operator, '(', '(', 'pair', ')']
    for _ in range(3):
        page.get_by_role('button', name='Undo', exact=True).click()
    assert page.evaluate("model.get('pair_expression')") == before


def test_pair_evaluation_reveals_one_clean_line_at_a_time(page):
    from birdtracks.pair_evaluation import evaluate
    from birdtracks.young_diagrams import PairExpression, PairTerm
    pair = PairTerm(unbarred=(1,), n0=1)
    expression = PairExpression((pair, pair), ('pair', 'tensor', 'pair'))
    result = evaluate(expression)
    young(page)
    page.evaluate("state => model.set('pair_expression', state)", expression.state())
    page.get_by_role('button', name='Evaluate mode', exact=True).click()
    page.evaluate("state => model.set('pair_evaluation', state)", result)
    host = page.locator('.birdtracks-pair-evaluation')
    assert host.is_visible()
    assert page.locator('.birdtracks-young-workspace').is_hidden()
    assert host.locator('.birdtracks-pair-evaluation-line').count() == 1
    assert host.locator('.birdtracks-young-grid, .birdtracks-young-axis').count() == 0
    for count in range(2, len(result['lines']) + 1):
        page.get_by_role('button', name='Next pair simplification step').click()
        assert host.locator('.birdtracks-pair-evaluation-line').count() == count
    assert page.get_by_role('button', name='Next pair simplification step').count() == 0
    page.get_by_role('button', name='Create mode', exact=True).click()
    assert host.is_hidden()
    assert page.evaluate("model.get('pair_expression')") == expression.state()


def test_double_click_axis_creates_singleton(page):
    young(page)
    page.locator('.birdtracks-young-axis').dispatch_event('dblclick')
    assert term(page)['singleton'] is True
    assert term(page)['barred'] == term(page)['unbarred'] == []
    assert page.locator('.birdtracks-young-singleton-control circle').count() == 1
    assert page.locator('.birdtracks-young-grid').count() > 0
    assert page.locator('.birdtracks-young-axis').evaluate("line => getComputedStyle(line).visibility") == 'visible'
    page.get_by_role('button', name='Undo', exact=True).click()
    assert 'singleton' not in term(page)
    assert page.locator('.birdtracks-young-grid').count() > 0
    page.locator('.birdtracks-young-axis').dispatch_event('dblclick')
    page.locator('.birdtracks-young-axis').dispatch_event('dblclick')
    assert 'singleton' not in term(page)


@pytest.mark.parametrize('column,side', [(0, 'unbarred'), (-1, 'barred')])
def test_singleton_can_grow_with_guides(page, column, side):
    young(page)
    page.locator('.birdtracks-young-axis').dispatch_event('dblclick')
    click_cell(page, 0, column)
    assert term(page)[side] == [1]
    assert 'singleton' not in term(page)
    assert page.locator('.birdtracks-young-grid').count() > 0
    assert page.locator('.birdtracks-young-axis').evaluate("line => getComputedStyle(line).visibility") == 'visible'
    page.get_by_role('button', name='Undo', exact=True).click()
    assert term(page)['singleton'] is True
    assert page.locator('.birdtracks-young-axis').evaluate("line => getComputedStyle(line).visibility") == 'visible'
