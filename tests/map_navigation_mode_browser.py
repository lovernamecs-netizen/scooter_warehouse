"""Real isolated server + Chrome touch emulation; no Android hardware claim."""
import httpx,uuid
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,CHROME,PASSWORD,nav,observe,RESULTS
r=start()
try:
 c=httpx.Client(base_url=r[3],trust_env=False);token=c.post('/api/login',json={'username':'admin','password':PASSWORD}).json()['token'];c.headers['Authorization']='Bearer '+token
 def business():
  s=c.get('/api/state').json();return {k:s[k] for k in ['vehicles','layout']}
 state=c.get('/api/state').json()
 def command(action,payload):
  r=c.post('/api/command',json={'command_id':str(uuid.uuid4()),'action':action,'payload':payload});r.raise_for_status();return r.json()
 model=next(x['id'] for x in state['masters'] if x['kind']=='model');color=next(x['id'] for x in state['masters'] if x['kind']=='color')
 vid=command('receive',{'vin':'MLHJK05A1P5000099','kind':'NEW','model_id':model,'color_id':color,'year':2026})['vehicle_id']
 v=next(x for x in business()['vehicles'] if x['id']==vid);command('move',{'vehicle_id':vid,'version':v['version'],'slot_id':state['layout']['zones'][0]['slots'][0]['id']})
 before=business()
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page(viewport={'width':1000,'height':900},has_touch=True);errors=observe(page,'map-navigation-mode')
  page.goto(r[3]);page.evaluate('(t)=>sessionStorage.setItem("warehouseToken",t)',token);page.reload();nav(page,'map')
  expect(page.locator('[data-act=map-pan-mode]')).to_have_count(0)
  viewport=page.locator('.map-viewport')
  plus=page.get_by_role('button',name='지도 확대');minus=page.get_by_role('button',name='지도 축소')
  expect(plus).to_be_visible()
  plus.tap();expect(viewport).to_have_attribute('data-map-zoom','0.9')
  minus.tap();expect(viewport).to_have_attribute('data-map-zoom','0.8')
  for _ in range(4):minus.tap()
  expect(minus).to_be_disabled()
  for _ in range(12):plus.tap()
  expect(plus).to_be_disabled()
  expect(viewport).to_have_attribute('data-map-zoom','1.6')
  slot=page.locator('.slot[data-vehicle]:not([data-vehicle=""])').first
  slot.click();expect(page.locator('#modal')).to_be_visible();page.locator('[data-act=close]').click()
  slot.scroll_into_view_if_needed();box=slot.bounding_box();cdp_hold=page.context.new_cdp_session(page)
  cdp_hold.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'id':1,'x':box['x']+box['width']/2,'y':box['y']+box['height']/2}]});page.wait_for_timeout(2100);cdp_hold.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
  expect(page.locator('[data-act=cancel-move]')).to_be_visible();page.wait_for_timeout(500);page.locator('[data-act=cancel-move]').click()
  assert business()==before
  page.evaluate('''async()=>{document.documentElement.style.zoom='1';document.body.innerHTML='<dialog id="modal"></dialog><div class="map-viewport" data-map-zoom="1" style="position:absolute;left:10px;top:10px;width:600px;height:400px;overflow:auto;touch-action:none"><div style="width:2000px;height:1600px"><div class="map-canvas" style="width:2000px;height:1600px"><button class="slot" style="position:absolute;left:500px;top:500px">Vehicle</button></div></div></div>';const v=document.querySelector('.map-viewport');const {bindMapNavigation}=await import('/map-editor.js');bindMapNavigation(v);v.scrollLeft=400;v.scrollTop=400;}''')
  cdp=page.context.new_cdp_session(page)
  def touch(kind,pts):
   cdp.send('Input.dispatchTouchEvent',{'type':kind,'touchPoints':[dict(x=x,y=y,id=i) for i,x,y in pts]});page.wait_for_timeout(35)
  def geometry():return page.locator('.map-viewport').evaluate('(v)=>[v.scrollLeft,v.scrollTop,Number(v.dataset.mapZoom)]')
  a=geometry();touch('touchStart',[(1,300,250)]);touch('touchMove',[(1,240,200)]);touch('touchEnd',[]);b=geometry();assert b[0]>a[0]+50 and b[1]>a[1]+40 and b[2]==a[2],(a,b)
  # Two fingers no longer zoom or pan; adding a second finger cancels panning.
  a=geometry();touch('touchStart',[(1,200,240),(2,400,240)]);touch('touchMove',[(1,120,200),(2,420,200)]);touch('touchEnd',[]);assert geometry()==a
  # Mouse drag on blank canvas; wheel scroll must not change the map scale.
  a=geometry();page.mouse.move(350,280);page.mouse.down();page.mouse.move(280,230,steps=8);page.mouse.up();b=geometry();assert b[0]>a[0]+60 and b[1]>a[1]+40 and b[2]==a[2]
  page.mouse.wheel(0,80);assert geometry()[2]==a[2]
  touch('touchStart',[(1,300,250)]);touch('touchCancel',[]);a=geometry();touch('touchStart',[(1,300,250)]);touch('touchMove',[(1,280,230)]);touch('touchEnd',[]);assert geometry()[0]>a[0]
  assert business()==before
  assert not errors['pageerror'],errors
  browser.close()
 print('PASS bounded map zoom buttons, card selection/2-second hold, blank one-finger/mouse pan, no pinch zoom, cancellation, unchanged business data')
finally:stop(r)
