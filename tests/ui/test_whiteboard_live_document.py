"""Shipped frontend connected to the actual Python document and child editors."""

import base64
from copy import deepcopy
from fractions import Fraction
from pathlib import Path

import pytest

playwright = pytest.importorskip('playwright.sync_api')
STATIC = Path(__file__).parents[2]/'src/birdtracks/projectors/static'


@pytest.fixture
def live_document(tmp_path, request):
    from birdtracks import Antisymmetriser, Projector, Symmetriser, whiteboard
    from birdtracks.projectors.widget import projector_widget

    path = tmp_path/'live.whiteboard'
    board = whiteboard(path,debug=True)
    kind = getattr(request,'param','source')
    source = 'x'
    block = {'id':'line','source':source}
    if kind == 'diagram':
        source = r'P\def \birdtracks'
        p = Projector([Antisymmetriser((1,2)), Symmetriser((3,))],coefficient=Fraction(-2,3))
        block = {'id':'line','source':source,'projector_snapshots':{'0':projector_widget(p).configuration.state()}}
    elif kind == 'pair':
        source = r'B\def \pair'
        block = {'id':'line','source':source}
    board.blocks = [block]
    calls = []

    def state():
        owners = (*board.embedded_projectors,*board.backend_projectors,*board.embedded_pairs)
        return {'board':board.get_state(), 'children':{f'anywidget:{e.model_id}':e.get_state() for e in owners}}

    with playwright.sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch()
        except playwright.Error as exc:
            pytest.skip(f'Chromium unavailable: {exc}')
        page = browser.new_page(viewport={'width':1200,'height':800})
        errors = []
        page.on('pageerror',lambda error:errors.append(str(error)))

        def command(_source, target, changes):
            calls.append((target,deepcopy(changes)))
            if target == 'board':
                owner = board
            else:
                owner = next(e for e in (*board.embedded_projectors,*board.backend_projectors,*board.embedded_pairs)
                             if f'anywidget:{e.model_id}' == target)
            for key,value in changes.items():
                setattr(owner,key,value)
            return state()

        page.expose_binding('pythonDocument',command)
        page.set_content('<div id="document"></div>')
        page.add_style_tag(content=(STATIC/'projector-widget.css').read_text())
        page.add_style_tag(content=(STATIC/'whiteboard-widget.css').read_text())
        page.evaluate("""async ({snapshot,boardSource,childSource})=>{
          const boardModule=await import('data:text/javascript;base64,'+boardSource);
          const childModule=await import('data:text/javascript;base64,'+childSource);
          const models=new Map();
          function modelFor(id,state){
            const values=structuredClone(state), listeners=new Map(), dirty=new Map();
            const model={model_id:id,get:key=>values[key],set(key,value){
              if(JSON.stringify(value)===JSON.stringify(values[key]))return;
              values[key]=value; dirty.set(key,value);
              for(const fn of listeners.get('change:'+key)||[])fn({new:value});
            },on(names,fn){for(const name of names.split(' ')){
              if(!listeners.has(name))listeners.set(name,new Set());listeners.get(name).add(fn);
            }},off(names,fn){for(const name of names.split(' '))listeners.get(name)?.delete(fn);},
            save_changes(){
              const changes=Object.fromEntries(dirty);dirty.clear();
              if(!Object.keys(changes).length)return;
              const delay=window.delayNext||0;window.delayNext=0;
              pythonDocument(id,changes).then(reply=>setTimeout(()=>apply(reply),delay));
            },receive(key,value){
              if(JSON.stringify(value)===JSON.stringify(values[key]))return;
              values[key]=value;
              for(const fn of listeners.get('change:'+key)||[])fn({new:value});
            }};
            models.set(id,model);return model;
          }
          function apply(reply){
            for(const [id,state] of Object.entries(reply.children)){
              const child=models.get(id)||modelFor(id,state);
              for(const [key,value] of Object.entries(state))
                if(!['editor_request','save_command','local_undo_command'].includes(key)) child.receive(key,value);
            }
            for(const [key,value] of Object.entries(reply.board))
              if(!['document_state','document_feedback','document_request'].includes(key)) model.receive(key,value);
            model.receive('document_state',reply.board.document_state);
            model.receive('document_feedback',reply.board.document_feedback);
          }
          window.model=modelFor('board',snapshot.board);
          for(const [id,state] of Object.entries(snapshot.children))modelFor(id,state);
          window.applyReply=apply;
          const host={getModel:async id=>models.get(id),getWidget:async id=>({render:async({el})=>{
            window.mounts=(window.mounts||0)+1;
            return childModule.default.render({model:models.get(id),el});
          }})};
          window.remount=()=>{window.cleanup?.();window.cleanup=boardModule.default.render({
            model,el:document.querySelector('#document'),host});};
          remount();
        }""",{'snapshot':state(), 'boardSource':base64.b64encode((STATIC/'whiteboard-widget.js').read_bytes()).decode(),
               'childSource':base64.b64encode((STATIC/'projector-widget.js').read_bytes()).decode()})
        page.wait_for_selector('[data-block-id="line"] textarea',state='attached')
        yield page,board,calls,path
        page.evaluate('cleanup()')
        browser.close()
        assert not errors


def settled(page):
    page.wait_for_function("model.get('document_feedback')?.request_id===model.get('document_request')?.request_id")


def test_scrolled_toolbar_name_retains_pointer_focus_and_commits_rename(live_document):
    page,board,calls,path=live_document
    board.blocks=[{'id':f'line-{i}','source':f'x_{i}'} for i in range(40)]
    page.evaluate('reply=>applyReply(reply)',{'board':board.get_state(),'children':{}})
    page.evaluate('window.scrollTo(0,500)')
    page.wait_for_function("document.querySelector('.birdtracks-whiteboard-heading').getBoundingClientRect().top>=-1")
    title=page.get_by_role('textbox',name='Whiteboard session name')
    before=page.evaluate('window.scrollY')
    box=title.bounding_box()
    page.mouse.click(box['x']+box['width']/2,box['y']+box['height']/2)
    assert page.evaluate('window.scrollY')==pytest.approx(before,abs=1),'title click scrolled'
    playwright.expect(title).to_be_focused()
    assert not page.locator('.birdtracks-whiteboard-block.editing').count()
    title.press('Control+a')
    assert page.evaluate('window.scrollY')==pytest.approx(before,abs=1),'title selection scrolled'
    title.press_sequentially('Renamed while scrolled')
    assert page.evaluate('window.scrollY')==pytest.approx(before,abs=1),'title typing scrolled'
    page.get_by_role('button',name='Save',exact=True).click()
    assert board.title=='Renamed while scrolled'
    assert page.evaluate('window.scrollY')==pytest.approx(before,abs=1)


@pytest.mark.parametrize('generated',[False,True])
@pytest.mark.parametrize('stale_calculation_viewport',[False,True])
def test_enter_between_rows_keeps_viewport_and_new_row_focus(live_document,generated,stale_calculation_viewport):
    page,board,calls,path=live_document
    blocks=[{'id':f'text-{i}','source':'xy'} for i in range(1,41)]
    if generated:
        blocks[14].update(source='= x',read_only=True,calculation_group='g',calculation_step=1)
    if stale_calculation_viewport:
        blocks[-1].update(source='= 1',read_only=True,calculation_group='scalar',calculation_step=1,
                          calculation_scalar=True)
    board.blocks=blocks
    page.evaluate('reply=>applyReply(reply)',{'board':board.get_state(),'children':{}})
    if stale_calculation_viewport:
        completed=page.locator('[data-block-id="text-40"] .birdtracks-whiteboard-rendered')
        completed.evaluate("e=>{e.scrollIntoView({block:'end'});e.focus({preventScroll:true});}")
        completed.press('Shift+Enter')
        page.wait_for_function("model.get('calculation_feedback')?.action==='completed'")
    target=page.locator('[data-block-id="text-15"] '+('.birdtracks-whiteboard-rendered' if generated else 'textarea'))
    target.evaluate("e=>{e.scrollIntoView({block:'center'});e.focus({preventScroll:true});}")
    if not generated:
        target.press('Home')
    before=page.evaluate('window.scrollY')
    page.evaluate('window.delayNext=180')
    target.press('Enter')
    inserted=page.locator('[data-block-id="text-41"] textarea')
    playwright.expect(inserted).to_be_focused()
    assert page.evaluate('window.scrollY')==pytest.approx(before,abs=1),'Enter jumped immediately'
    settled(page)
    playwright.expect(inserted).to_be_focused()
    assert page.evaluate('window.scrollY')==pytest.approx(before,abs=1),'acknowledgement jumped'
    assert not inserted.evaluate('e=>e.closest("[data-block-id]").classList.contains("trailing-blank")')
    inserted.press_sequentially('inserted')
    settled(page)
    assert next(b for b in board.blocks if b['id']=='text-41')['source'].startswith('inserted')


@pytest.mark.parametrize('live_document',['pair'],indirect=True)
@pytest.mark.parametrize('delete',['Delete','Backspace','contextmenu'])
def test_repeated_pair_box_edits_keep_focus_and_active_controls(live_document,delete):
    page,board,calls,path=live_document
    page.wait_for_selector('.birdtracks-young-term')
    anchor=page.locator('.birdtracks-whiteboard-embedded-pair')
    child=board.embedded_pairs[0]
    source=page.locator('[data-block-id="line"] textarea')
    source.focus()
    source.press('End')
    anchor.click(position={'x':2,'y':2})
    assert anchor.evaluate('e=>e.classList.contains("inline-active")'),page.evaluate('document.activeElement.outerHTML.slice(0,200)')
    for column in (0,1):
        anchor.locator(f'[data-grid-column="{column}"][data-grid-row="0"]').first.click()
        settled(page)
        assert anchor.evaluate('e=>e.contains(document.activeElement)')
        assert anchor.evaluate('e=>e.classList.contains("inline-active")')
    assert anchor.locator('.birdtracks-young-box').count()==2
    box=anchor.locator('.birdtracks-young-box[data-column="1"]')
    if delete=='contextmenu':
        box.click(button='right')
    else:
        box.click()
        page.keyboard.press(delete)
    settled(page)
    assert anchor.locator('.birdtracks-young-box').count()==1
    assert anchor.evaluate('e=>e.contains(document.activeElement)')
    assert anchor.evaluate('e=>e.classList.contains("inline-active")')
    anchor.locator('[data-grid-column="1"][data-grid-row="0"]').first.click()
    settled(page)
    assert anchor.locator('.birdtracks-young-box').count()==2
    assert board.embedded_pairs[0] is child
    assert source.input_value()==r'B\def \pair'


def test_typing_uses_one_surface_and_preserves_last_valid_value_while_saving_draft(live_document):
    page,board,calls,path=live_document
    editor=page.locator('[data-block-id="line"] textarea')
    editor.focus()
    editor.fill(r'\frac{1}{2} x')
    settled(page)
    assert page.locator('[data-block-id="line"] mfrac').count()==1
    editor.fill(r'\frac{1}{')
    settled(page)
    assert editor.input_value()==r'\frac{1}{'
    assert page.locator('[data-block-id="line"] mfrac').count()==0
    assert page.locator('[data-block-id="line"] .birdtracks-whiteboard-rendered').text_content()==r'\frac{1}{'
    assert board._document_session.committed_blocks[0]['source']==r'\frac{1}{2} x'
    assert editor.get_attribute('aria-invalid')=='true'
    assert page.locator('[data-block-id="line"] .birdtracks-whiteboard-parse-status').is_visible()
    playwright.expect(editor).to_be_focused()
    assert editor.evaluate('e=>e.selectionStart')==len(r'\frac{1}{')
    page.get_by_role('button',name='Save',exact=True).click()
    settled(page)
    from birdtracks import whiteboard
    loaded=whiteboard(path,debug=True)
    assert loaded.blocks[0]['source']==r'\frac{1}{'
    assert loaded.blocks[0]['source_edit']['committed_source']==r'\frac{1}{2} x'
    editor.fill(r'\frac{3}{4}')
    settled(page)
    assert editor.get_attribute('aria-invalid') is None
    page.locator('.birdtracks-whiteboard-title').click()
    assert not page.locator('.birdtracks-whiteboard-block[data-block-id="line"]').evaluate('r=>r.classList.contains("editing")')
    assert page.locator('[data-block-id="line"] mfrac').count()==1
    assert not any('simplify_request' in data for _,data in calls)


def test_rapid_typing_and_old_document_reply_cannot_replace_new_draft(live_document):
    page,board,calls,path=live_document
    before=deepcopy(board.document_state)
    editor=page.locator('[data-block-id="line"] textarea')
    editor.focus()
    editor.press('End')
    page.evaluate('window.delayNext=180')
    editor.press_sequentially('yz',delay=10)
    playwright.expect(editor).to_have_value('xyz')
    settled(page)
    playwright.expect(editor).to_have_value('xyz')
    assert editor.evaluate('e=>e.selectionStart')==3
    page.evaluate('old=>model.receive("document_state",old)',before)
    playwright.expect(editor).to_have_value('xyz')
    assert page.evaluate('model.get("document_state").revision')==board.document_state['revision']
    playwright.expect(editor).to_be_focused()
    page.evaluate('remount()')
    playwright.expect(page.locator('[data-block-id="line"] textarea')).to_have_value('xyz')


def test_save_waits_for_latest_draft_and_detached_transport_finishes(live_document):
    page,board,calls,path=live_document
    editor=page.locator('[data-block-id="line"] textarea')
    editor.focus()
    page.evaluate('window.delayNext=180')
    editor.fill('xyz')
    editor.fill(r'\sqrt{')
    page.get_by_role('button',name='Save',exact=True).click()
    page.evaluate('cleanup()')
    page.wait_for_function("model.get('document_state').blocks[0].source==='\\\\sqrt{' && model.get('save_request')>0")
    from birdtracks import whiteboard
    loaded=whiteboard(path,debug=True)
    assert loaded.blocks[0]['source']==r'\sqrt{'
    assert loaded.blocks[0]['source_edit']['committed_source']=='xyz'
    page.evaluate('remount()')
    assert page.locator('[data-block-id="line"] textarea').input_value()==r'\sqrt{'
    assert page.locator('[data-block-id="line"] .birdtracks-whiteboard-rendered').text_content()==r'\sqrt{'


@pytest.mark.parametrize('live_document',['pair'],indirect=True)
def test_nested_pair_input_keeps_focus_caret_and_draft_across_other_row_update(live_document):
    page,board,calls,path=live_document
    page.wait_for_selector('.birdtracks-young-term')
    panel=page.locator('.birdtracks-young-term')
    panel.focus()
    panel.press('Control+Enter')
    coefficient=page.locator('.birdtracks-whiteboard-embedded-pair input[aria-label="Prefactor"]')
    coefficient.fill('7')
    coefficient.evaluate('e=>e.setSelectionRange(0,1)')
    # A real Python document update must not dispose or refocus this form.
    board.blocks=[*board.blocks,{'id':'other','source':'x'}]
    owners=(*board.embedded_projectors,*board.backend_projectors,*board.embedded_pairs)
    page.evaluate('reply=>applyReply(reply)',{'board':board.get_state(),
                 'children':{f'anywidget:{e.model_id}':e.get_state() for e in owners}})
    playwright.expect(coefficient).to_be_focused()
    assert coefficient.input_value()=='7'
    assert coefficient.evaluate('e=>[e.selectionStart,e.selectionEnd]')==[0,1]
    page.locator('.birdtracks-whiteboard-title').click()
    settled(page)
    assert board.embedded_pairs[0].pair_expression['terms'][0]['coefficient']=='7'


@pytest.mark.parametrize('live_document',['diagram'],indirect=True)
def test_diagram_activation_editing_and_incomplete_source_keep_one_owner(live_document):
    page,board,calls,path=live_document
    page.wait_for_selector('.birdtracks-node rect')
    child=board.embedded_projectors[0]
    owner=child._editor_session
    original=owner.state.projector
    anchor=page.locator('.birdtracks-whiteboard-embedded-projector').first
    assert not anchor.evaluate('e=>e.classList.contains("inline-active")')
    anchor.click(position={'x':2,'y':2})
    assert anchor.evaluate('e=>e.classList.contains("inline-active")')
    from tests.ui.test_projector_editor_gestures import move_hit
    move_hit(page,'.birdtracks-node rect',45)
    page.wait_for_function("model.get('document_state').blocks[0].projector_snapshots?.['0']?.editor_state?.state?.revision>0")
    assert child._editor_session is owner
    assert owner.state.projector is original
    before_mounts=page.evaluate('mounts')
    editor=page.locator('[data-block-id="line"] textarea')
    editor.fill(r'P\def \birdt')
    settled(page)
    assert board.embedded_projectors[0] is child
    assert page.locator('.birdtracks-whiteboard-command-suggestion').text_content()=='racks'
    editor.press('Tab')
    settled(page)
    page.wait_for_selector('.birdtracks-node rect')
    assert page.evaluate('mounts')==before_mounts
    page.locator('.birdtracks-whiteboard-title').click()
    assert not anchor.evaluate('e=>e.classList.contains("inline-active")')
    assert anchor.evaluate("e=>getComputedStyle(e).boxShadow")=='none'


@pytest.mark.parametrize('live_document',['pair'],indirect=True)
def test_pair_box_edit_uses_document_command_and_survives_draft_reload(live_document):
    page,board,calls,path=live_document
    page.wait_for_selector('.birdtracks-young-term')
    child=board.embedded_pairs[0]
    anchor=page.locator('.birdtracks-whiteboard-embedded-pair')
    page.locator('.birdtracks-young-term').click(position={'x':5,'y':5})
    assert anchor.evaluate('e=>e.classList.contains("inline-active")')
    page.locator('[data-grid-column="0"][data-grid-row="0"]').first.dblclick()
    page.wait_for_function("model.get('document_state').blocks[0].pair_snapshots?.['0']?.terms[0].unbarred.length===1")
    assert any(data.get('document_request',{}).get('action')=='pair' for _,data in calls)
    editor=page.locator('[data-block-id="line"] textarea')
    editor.fill(r'B\def \pa')
    settled(page)
    assert board.embedded_pairs[0] is child
    editor.press('Tab')
    settled(page)
    page.wait_for_selector('.birdtracks-young-box')
    editor.fill(r'B\def \pa')
    settled(page)
    from birdtracks import whiteboard
    loaded=whiteboard(path,debug=True)
    assert loaded.blocks[0]['source']==r'B\def \pa'
    assert loaded.embedded_pairs[0].pair_expression==child.pair_expression


@pytest.mark.parametrize(('prefix','completed'),[
    (r'\bi',r'\birdtracks'),(r'\pa',r'\pair'),(r'\de','\\def '),
    (r'\op','\\oplus '),(r'\ot','\\otimes '),
])
def test_partial_commands_complete_without_frontend_algebra_commit(live_document,prefix,completed):
    page,board,calls,path=live_document
    editor=page.locator('[data-block-id="line"] textarea')
    editor.fill('x '+prefix)
    settled(page)
    assert board._document_session.committed_blocks[0]['source']=='x'
    assert page.locator('.birdtracks-whiteboard-command-suggestion').is_visible()
    editor.press('ArrowLeft')
    assert editor.evaluate('e=>e.selectionStart')==len('x '+prefix)-1
    editor.press('End')
    editor.press('Tab')
    settled(page)
    assert editor.input_value()=='x '+completed
    assert editor.evaluate('e=>e.selectionStart')==len('x '+completed)
    playwright.expect(editor).to_be_focused()


@pytest.mark.parametrize('source',['a+b',r'a+\frac{12}{34}',r'\frac{12}{',r'x+\bi','a = '])
def test_caret_uses_current_surface_for_mouse_arrows_and_end(live_document,source):
    page,board,calls,path=live_document
    editor=page.locator('[data-block-id="line"] textarea')
    editor.fill(source)
    settled(page)
    editor.press('Home')
    assert editor.evaluate('e=>e.selectionStart')==0
    editor.press('End')
    assert editor.evaluate('e=>e.selectionStart')==len(source)
    if source==r'\frac{12}{':
        editor.press('ArrowLeft')
        assert editor.evaluate('e=>e.selectionStart')==len(source)-1
        editor.press('ArrowRight')
        assert editor.evaluate('e=>e.selectionStart')==len(source)
    editor.press('Home')
    page.keyboard.press('End')
    # Click beyond the visible expression, not beyond the invisible textarea's
    # raw LaTeX length. It must map to the current source end.
    box=page.locator('[data-block-id="line"] .birdtracks-whiteboard-rendered').bounding_box()
    page.mouse.click(box['x']+box['width']-4,box['y']+box['height']/2)
    assert editor.evaluate('e=>e.selectionStart')==len(source)
    metrics=page.locator('[data-block-id="line"] .birdtracks-whiteboard-caret').evaluate('''e=>({
      hidden:e.hidden,x:e.getBoundingClientRect().left,
      row:e.closest('[data-block-id]').getBoundingClientRect().left})''')
    assert not metrics['hidden']
    assert metrics['x']>metrics['row']
