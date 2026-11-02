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
  button=page.locator('[data-act=map-pan-mode]');expect(button).to_have_attribute('aria-pressed','false');button.click();expect(button).to_have_attribute('aria-pressed','true');expect(page.locator('.map-navigation-mode')).to_have_count(1)
  page.locator('.slot').first.click();expect(page.locator('#modal')).not_to_be_visible()
  slot=page.locator('.slot[data-vehicle]:not([data-vehicle=""])').first
  expect(slot).to_be_visible();box=slot.bounding_box();cdp_hold=page.context.new_cdp_session(page)
  cdp_hold.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'id':1,'x':box['x']+box['width']/2,'y':box['y']+box['height']/2}]});page.wait_for_timeout(2100);cdp_hold.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
  expect(page.locator('.map-context')).to_have_count(0);expect(page.locator('[data-act=cancel-move]')).to_have_count(0);expect(page.locator('#modal')).not_to_be_visible()
  page.screenshot(path=str(RESULTS/'map-navigation-mode.png'))
  button.click();expect(button).to_have_attribute('aria-pressed','false')
  page.locator('.slot').first.click();expect(page.locator('#modal')).to_be_visible();page.locator('[data-act=close]').click()
  page.locator('[data-act=edit-map]').click();expect(page.locator('.map-canvas.editing')).to_have_count(1);button.click();expect(page.locator('.map-canvas.editing')).to_have_count(0)
  zoom_before=float(page.locator('.map-viewport').get_attribute('data-map-zoom'));page.locator('[data-act=zoom][data-delta="0.1"]').click();assert float(page.locator('.map-viewport').get_attribute('data-map-zoom'))>zoom_before
  # Test geometry in a large scrollable canvas, independent of warehouse dimensions.
  page.evaluate('''async()=>{document.documentElement.style.zoom='1';document.body.innerHTML='<div class="map-viewport" data-map-zoom="1" style="position:absolute;left:10px;top:10px;width:600px;height:400px;overflow:auto;touch-action:none"><div style="width:2000px;height:1600px"><div class="map-canvas" style="width:2000px;height:1600px"><button class="slot" style="position:absolute;left:500px;top:500px">Vehicle</button></div></div></div>';const v=document.querySelector('.map-viewport');const {bindMapNavigation}=await import('/map-editor.js?v=20261102-map-mode-v1');bindMapNavigation(v,()=>{},{panMode:true});v.scrollLeft=400;v.scrollTop=400;}''')
  cdp=page.context.new_cdp_session(page)
  def touch(kind,pts):
   cdp.send('Input.dispatchTouchEvent',{'type':kind,'touchPoints':[dict(x=x,y=y,id=i) for i,x,y in pts]});page.wait_for_timeout(35)
  def geometry():return page.locator('.map-viewport').evaluate('(v)=>[v.scrollLeft,v.scrollTop,Number(v.dataset.mapZoom)]')
  a=geometry();touch('touchStart',[(1,300,250)]);touch('touchMove',[(1,240,200)]);touch('touchEnd',[]);b=geometry();assert b[0]>a[0]+50 and b[1]>a[1]+40 and b[2]==a[2],(a,b)
  # Translate two fingers together: neither pinch zoom nor two-finger pan in this mode.
  a=geometry();touch('touchStart',[(1,200,240),(2,400,240)]);touch('touchMove',[(1,170,200),(2,370,200)]);b=geometry();assert a==b,(a,b)
  touch('touchMove',[(1,168,200),(2,372,200)]);assert geometry()[2]==a[2] # 4px jitter
  touch('touchMove',[(1,120,200),(2,420,200)]);b=geometry();assert b[2]>a[2]*1.4,(a,b)
  touch('touchMove',[(1,210,200),(2,330,200)]);assert geometry()[2]<a[2]*.7
  # Lift one finger, continue panning without scale jump.
  touch('touchEnd',[(2,330,200)]);a=geometry();touch('touchMove',[(1,190,180)]);b=geometry();assert b[2]==a[2] and b[0]>a[0],(a,b);touch('touchEnd',[])
  # Cancellation and a new gesture must not inherit stale pinch state.
  touch('touchStart',[(1,200,220),(2,400,220)]);touch('touchCancel',[]);a=geometry();touch('touchStart',[(1,300,250)]);touch('touchMove',[(1,280,230)]);touch('touchEnd',[]);assert geometry()[2]==a[2]
  assert business()==before
  assert not errors['pageerror'],errors
  browser.close()
 print('PASS mode button, selection/hold lock, one-touch pan, parallel two-touch stable, jitter threshold, pinch in/out, two-to-one transition, cancellation, business data unchanged')
finally:stop(r)
