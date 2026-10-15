"""Disposable DB + browser regression for warehouse layout editing."""
from pathlib import Path
import tempfile,subprocess,sys,os,time,json
import httpx
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as td:
 env=dict(os.environ,DATABASE_URL='sqlite:///'+str(Path(td)/'test.db'),WAREHOUSE_ADMIN_PASSWORD='LocalTestOnly-1234')
 for cmd in ['init','demo']:subprocess.run([sys.executable,'-m','server.cli',cmd],cwd=root,env=env,check=True,capture_output=True)
 log=open(Path(td)/'log','w');server=subprocess.Popen([sys.executable,'-m','uvicorn','server.app:app','--port','8879'],cwd=root,env=env,stdout=log,stderr=log)
 try:
  with httpx.Client(base_url='http://127.0.0.1:8879',trust_env=False) as client:
   for _ in range(80):
    try:
     if client.get('/health').status_code==200:break
    except httpx.HTTPError:pass
    time.sleep(.1)
   with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':1500,'height':1050});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8879');page.locator('[name=username]').fill('admin');page.locator('[name=password]').fill('LocalTestOnly-1234');page.locator('#login button').click();page.locator('.sidebar [data-page=map]').click()
    page.locator('.zone-title').first.click(button='right');page.get_by_role('menuitem',name='설정 수정…').click();page.locator('#name').fill('우클릭 구역');page.locator('[data-act=save-zone]').click();page.locator("#modal").wait_for(state="hidden")
    page.locator('[data-act=edit-map]').click();page.locator('#map-snap').select_option('20')
    def state():return page.evaluate("async()=>await (await fetch('/api/state',{headers:{Authorization:'Bearer '+sessionStorage.warehouseToken}})).json()")
    first=state()['layout']['zones'][0];zid=first['id'];sel=f'.zone[data-zone-id="{zid}"]'
    def drag(dx,dy,cancel=False):
     box=page.locator(sel+' .zone-title').bounding_box();x=box['x']+35;y=box['y']+15
     page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+dx,y+dy,steps=8)
     if cancel:page.keyboard.press('Escape')
     page.mouse.up()
    drag(53,37)
    expected_x=round((first['x']+53/.8)/20)*20;expected_y=round((first['y']+37/.8)/20)*20
    page.get_by_text('배치 위치 저장 완료',exact=True).wait_for()
    moved=next(z for z in state()['layout']['zones'] if z['id']==zid);assert (moved['x'],moved['y'])==(expected_x,expected_y),moved
    assert [s['id'] for s in moved['slots']]==[s['id'] for s in first['slots']]
    drag(50,50,True);assert next(z for z in state()['layout']['zones'] if z['id']==zid)['x']==moved['x']
    page.reload();page.locator('.sidebar [data-page=map]').click();assert int(page.locator(sel).evaluate('(el)=>parseInt(el.style.left)'))==moved['x']
    page.locator('[data-act=edit-map]').click();page.locator(sel+' .zone-title').click(button='right');assert page.get_by_role('menuitem',name='설정 수정…').count()==1
    page.keyboard.press('Escape');assert page.get_by_role('menu').count()==0
    # A rejected write must restore the persisted map, never leave a false success.
    page.route('**/api/command',lambda route:route.fulfill(status=409,content_type='application/json',body='{"detail":"다른 작업으로 변경됨"}'))
    drag(70,30);page.get_by_text('위치 저장 실패:',exact=False).wait_for();page.wait_for_timeout(200)
    assert int(page.locator(sel).evaluate('(el)=>parseInt(el.style.left)'))==moved['x']
    page.unroute('**/api/command');page.locator(sel+' .zone-title').click(button='right')
    out=root/'docs/screenshots';out.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(out/'pc-map-editor.png'))
    page.keyboard.press('Escape')
    revision=state()['revision']
    result=page.evaluate("""async(revision)=>{return await (await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+sessionStorage.warehouseToken},body:JSON.stringify({command_id:crypto.randomUUID(),action:'map_objects',payload:{revision,objects:[{kind:'MATERIAL',label:'자재',x:20,y:850,width:150,height:80}]}})})).json()}""",revision)
    page.locator('[data-act=refresh]').click();page.locator('.map-object').scroll_into_view_if_needed()
    box=page.locator('.map-object').bounding_box();page.mouse.move(box['x']+30,box['y']+20);page.mouse.down();page.mouse.move(box['x']+78,box['y']+36,steps=5);page.mouse.up()
    page.wait_for_timeout(400)
    obj=state()['layout']['objects'][0];assert (obj['x'],obj['y'])==(80,880),obj
    page.locator('.map-object').click(button='right');page.get_by_role('menuitem',name='설정 수정…').click();page.get_by_role('heading',name='문·통로·자재 구역').wait_for()
    assert not errors,errors
    print(json.dumps({'context_edit':True,'snap_at_80_percent':True,'escape_cancel':True,'persist_after_reload':True,'slot_ids_preserved':True,'conflict_rollback':True,'object_drag_and_context':True,'js_errors':errors}))
    browser.close()
 finally:server.terminate();server.wait(timeout=10);log.close()
