from browser_support import nav
"""Windows Chrome integration checks using an isolated server/DB and synthetic originals."""
from pathlib import Path
import sys,os,io,uuid,json,hashlib,base64,time
from PIL import Image,ImageDraw
import httpx
from playwright.sync_api import sync_playwright,expect
from browser_support import stop,PASSWORD
import tempfile,subprocess

from browser_support import start,stop,observe

OUT=Path(os.environ.get('PHOTO_UI_OUTPUT',str(Path(__file__).resolve().parents[2]/'photo-ui-results')));OUT.mkdir(exist_ok=True,parents=True)
def picture(w=4000,h=3000,color='#b9c9c5'):
 im=Image.new('RGB',(w,h),color);d=ImageDraw.Draw(im)
 for n in range(0,w,100):d.line((n,0,n,h),fill='#718f88',width=2)
 d.rectangle((w//3,h//3,w*2//3,h*2//3),outline='#e36f4e',width=12);d.line((w//3,h//2,w*2//3,h//2+60),fill='#173c36',width=3)
 b=io.BytesIO();im.save(b,'JPEG',quality=95);return b.getvalue()
raw=picture();runtime=start(demo=False);base=runtime[3];errors=[]
try:
 client=httpx.Client(base_url=base,trust_env=False,timeout=30)
 token=client.post('/api/login',json={'username':'admin','password':PASSWORD}).json()['token'];client.headers['Authorization']='Bearer '+token

 def cmd(action,payload):
  r=client.post('/api/command',json={'command_id':str(uuid.uuid4()),'action':action,'payload':payload});r.raise_for_status();return r.json()
 brand=cmd('master',{'kind':'brand','name':'Synthetic Brand'})['id'];cmd('master',{'kind':'model','name':'Test Scooter','detail':{'brand_id':brand}});cmd('master',{'kind':'color','name':'Test Silver'})
 state=client.get('/api/state').json();model=next(x['id'] for x in state['masters'] if x['kind']=='model');color=next(x['id'] for x in state['masters'] if x['kind']=='color')
 r=client.post('/api/command',json={'command_id':str(uuid.uuid4()),'action':'receive','payload':{'kind':'USED','model_id':model,'color_id':color,'year':2026}});r.raise_for_status();vid=r.json()['vehicle_id']
 def media():return client.get('/api/used/'+vid).json()['media']
 with sync_playwright() as pw:
  browser=pw.chromium.launch(channel='chrome',headless=True)
  context=browser.new_context(viewport={'width':1366,'height':768},accept_downloads=True)
  page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));observe(page,'photo')
  page.goto(base);page.evaluate('(token)=>sessionStorage.setItem("warehouseToken",token)',token);page.reload()
  nav(page,'used');page.locator(f'[data-act=used-open][data-id="{vid}"][data-step="3"]').click()
  expect(page.locator('.product-photo-grid .photo-drop')).to_have_count(6)
  def drop(selector,files):
   page.locator(selector).first.evaluate('''(el,files)=>{const dt=new DataTransfer();for(const f of files){const bytes=Uint8Array.from(atob(f.data),c=>c.charCodeAt(0));dt.items.add(new File([bytes],f.name,{type:f.type}));}for(const name of ['dragenter','dragover','drop'])el.dispatchEvent(new DragEvent(name,{bubbles:true,cancelable:true,dataTransfer:dt}));}''',files)
  def f(name='synthetic.jpg',data=raw,mime='image/jpeg'):return {'name':name,'data':base64.b64encode(data).decode(),'type':mime}
  for key in ['front','rear','left','right','cockpit','dashboard']:
   drop(f'.product-photo-grid [data-key="{key}"]',[f()]);expect(page.locator('#used-form fieldset')).to_be_enabled()
   expect(page.locator(f'.product-photo-grid [data-key="{key}"] [data-media]')).to_have_count(1)
  assert len(media())==6 and {x['key'] for x in media()}=={'front','rear','left','right','cockpit','dashboard'}
  page.locator('[name=equipment_notes]').fill('드롭 중 보존 메모')
  drop('.product-photo-grid [data-key=front]',[f(),f('two.jpg')]);assert len(media())==6;assert page.locator('[name=equipment_notes]').input_value()=='드롭 중 보존 메모'
  page.wait_for_timeout(400)
  # Original dimensions, pointer anchored zoom, pan, fit, download bytes and return state.
  page.locator('.product-photo-grid [data-key=front] .photo-tile-open').click();expect(page.locator('.original-status')).to_contain_text('4000 × 3000')
  page.locator('[data-v=actual]').click();assert float(page.locator('.original-viewport').get_attribute('data-scale'))==1
  page.locator('.original-viewport').hover();page.mouse.wheel(0,-300);page.wait_for_timeout(100);assert float(page.locator('.original-viewport').get_attribute('data-scale'))>1
  box=page.locator('.original-viewport').bounding_box();page.mouse.move(box['x']+300,box['y']+220);page.mouse.down();page.mouse.move(box['x']+400,box['y']+250);page.mouse.up()
  with page.expect_download() as download_info:page.locator('[data-v=download]').click()
  downloaded=Path(download_info.value.path()).read_bytes();assert hashlib.sha256(downloaded).digest()==hashlib.sha256(raw).digest()
  page.screenshot(path=str(OUT/'original-desktop.png'))
  page.keyboard.press('Escape');expect(page.locator('.original-viewer')).to_have_count(0);expect(page.locator('#modal')).to_be_visible();assert page.locator('[name=equipment_notes]').input_value()=='드롭 중 보존 메모'
  page.locator('.product-photo-grid [data-key=front] .photo-tile-add').click();expect(page.locator('dialog.used-photo-dialog')).to_be_visible();assert page.locator('dialog.used-photo-dialog').bounding_box()['width']<=561
  page.screenshot(path=str(OUT/'single-photo-desktop.png'));page.locator('dialog.used-photo-dialog [data-p=close]').first.click();page.wait_for_timeout(150)
  for width,height in [(1366,768),(1920,1080),(820,900),(390,844),(320,640),(844,390)]:
   page.set_viewport_size({'width':width,'height':height});page.wait_for_timeout(60)
   assert page.locator('#modal').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1'),(width,height,'horizontal overflow')
   page.locator('.product-photo-grid').scroll_into_view_if_needed();page.screenshot(path=str(OUT/f'product-{width}x{height}.png'))
  page.set_viewport_size({'width':1366,'height':768})
  # Existing record -> intake/damage/wear, multi-drop, partial failure and same-ID retry.
  page.locator('[data-act=used-step][data-step="1"]').first.click()
  expect(page.locator('.used-record')).to_be_visible()
  page.locator('[name=exterior]').fill('입고 메모 유지')
  failed_once=[False]
  def flaky(route):
   if not failed_once[0]:failed_once[0]=True;route.fulfill(status=503,content_type='application/json',body='{"detail":"synthetic transient failure"}')
   else:route.continue_()
  page.route('**/api/used/*/upload',flaky)
  drop('.used-photo-tile[data-category=intake][data-key=whole]',[f('first.jpg'),f('second.jpg')])
  expect(page.locator('#web-photo-jobs')).to_contain_text('서버가 요청을 처리하지 못했습니다.')
  assert len([x for x in media() if x['category']=='intake'])==1
  assert page.locator('[name=exterior]').input_value()=='입고 메모 유지'
  page.unroute('**/api/used/*/upload',flaky)
  page.locator('[data-act=used-retry]').click();expect(page.locator('#web-photo-jobs')).to_be_empty()
  intake_media=[x for x in media() if x['category']=='intake'];assert len(intake_media)==2 and len({x['id'] for x in intake_media})==2
  # Corrupt bytes are rejected by the server and remain recoverable, rather than claimed saved.
  drop('.used-photo-tile[data-category=intake][data-key=plate]',[f('fake.jpg',b'not an image')]);expect(page.locator('#web-photo-jobs')).to_contain_text('해독')
  page.wait_for_timeout(400);page.locator('.used-photo-tile[data-key=plate] .photo-tile-add').click()
  page.once('dialog',lambda d:d.accept());page.locator('dialog.used-photo-dialog [data-p=delete]').click();expect(page.locator('#web-photo-jobs')).to_be_empty();page.wait_for_timeout(200)
  page.locator('dialog.used-photo-dialog [data-p=close]').first.click();page.wait_for_timeout(150)
  drop('.used-photo-tile[data-category=intake][data-key=plate]',[f('invalid.txt',b'bad','text/plain')]);assert not [x for x in media() if x['key']=='plate']
  # Out-of-zone drop never navigates away.
  previous_url=page.url;drop('#modal .modal-head',[f()]);assert page.url==previous_url
  page.wait_for_timeout(400);page.locator('[data-act=used-step][data-step="2"]').first.click();expect(page.locator('.part-hotspot')).to_have_count(13)
  page.locator('.part-hotspot[data-key=front]').click();page.locator('#damage-note').fill('카울 흠집 메모');page.locator('#damage-status').select_option('damaged')
  drop('.damage-inline',[f('damage1.jpg'),f('damage2.jpg')]);expect(page.locator('.damage-inline [data-media]')).to_have_count(2)
  assert page.locator('#damage-note').input_value()=='카울 흠집 메모'
  page.screenshot(path=str(OUT/'damage-desktop.png'))
  for key in ['headlight','shield','mirror','handle','floor','seat','rear','left','right','exhaust','front_fender','rear_fender']:
   drop(f'.part-hotspot[data-key="{key}"]',[f(key+'.jpg')]);expect(page.locator('#used-form fieldset')).to_be_enabled()
   # Wait for server-confirmed thumbnail count at this exact part.
   expect(page.locator(f'.part-hotspot[data-key="{key}"] b')).to_have_text('1')
  assert len([x for x in media() if x['category']=='damage'])==14
  page.wait_for_timeout(400);page.locator('[data-act=used-step][data-step="3"]').first.click()
  for key in ['pad_front','pad_rear','tire_front','tire_rear']:
   drop(f'.used-photo-tile[data-category=wear][data-key="{key}"]',[f(key+'.jpg')]);expect(page.locator(f'.used-photo-tile[data-category=wear][data-key="{key}"] [data-media]')).to_have_count(1)
  # Replacement cancellation preserves server bytes.
  prior=next(x['id'] for x in media() if x['category']=='product' and x['key']=='front')
  page.once('dialog',lambda d:d.dismiss());drop('.product-photo-grid [data-key=front]',[f('replacement.jpg',picture(1000,1600))])
  assert next(x['id'] for x in media() if x['category']=='product' and x['key']=='front')==prior
  # New and old native bridge detection; do not confuse a JS mock with Galaxy verification.
  page.wait_for_timeout(400);page.evaluate('() => {window.nativeCalls=[];window.WarehouseNative={capturePhoto:m=>nativeCalls.push(JSON.parse(m)),photoJobs:()=>{}};}')
  page.once('dialog',lambda d:d.accept());page.locator('.product-photo-grid [data-key=rear] .photo-tile-add').click();page.locator('dialog.used-photo-dialog [data-p=camera]').click()
  assert page.evaluate('nativeCalls.at(-1).category')=='product';assert page.evaluate('nativeCalls.at(-1).key')=='rear';assert page.evaluate('nativeCalls.at(-1).vehicle_id')==vid
  page.locator('dialog.used-photo-dialog [data-p=close]').first.click();page.wait_for_timeout(150)
  page.evaluate('() => {window.WarehouseNative={captureDamage:m=>nativeCalls.push(JSON.parse(m)),photoJobs:()=>{}};}')
  page.locator('[data-act=used-step][data-step="2"]').first.click();page.locator('.part-hotspot[data-key=front]').click();page.locator('.damage-inline [data-p=camera]').click();assert page.evaluate('nativeCalls.at(-1).category')=='damage'
  page.evaluate('() => {delete window.WarehouseNative;}')
  # Browser Back closes the original viewer only; editor remains and notes survive.
  page.locator('.damage-inline [data-p=original]').first.click();expect(page.locator('.original-status')).to_contain_text('4000 × 3000');page.go_back();expect(page.locator('.original-viewer')).to_have_count(0);expect(page.locator('#modal')).to_be_visible()
  # Real browser touch input emulation (not an Android device).
  page.set_viewport_size({'width':390,'height':844});page.locator('.damage-inline [data-p=original]').first.click();expect(page.locator('.original-status')).to_contain_text('4000 × 3000')
  stage=page.locator('.original-viewport');rect=stage.bounding_box();cx=rect['x']+rect['width']/2;cy=rect['y']+rect['height']/2;before=float(stage.get_attribute('data-scale'))
  cdp=context.new_cdp_session(page)
  cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':cx-30,'y':cy,'id':1},{'x':cx+30,'y':cy,'id':2}]})
  for n in range(1,6):cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':cx-30-n*12,'y':cy,'id':1},{'x':cx+30+n*12,'y':cy,'id':2}]})
  cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]});assert float(stage.get_attribute('data-scale'))>before
  page.screenshot(path=str(OUT/'original-mobile.png'));page.evaluate('() => window.handleWarehouseBack()');expect(page.locator('.original-viewer')).to_have_count(0);expect(page.locator('#modal')).to_be_visible()
  # New vehicle keeps pending originals when required fields are missing.
  page.set_viewport_size({'width':1366,'height':768});page.once('dialog',lambda d:d.accept());page.locator('#modal .modal-head [data-act=close]').click();page.wait_for_timeout(150)
  page.locator('[data-act=receipt]').first.click();expect(page.locator('.used-record')).to_be_visible()
  drop('.used-photo-tile[data-category=intake][data-key=whole]',[f('pending.jpg')]);expect(page.locator('#web-photo-jobs')).to_contain_text('저장 대기')
  page.wait_for_timeout(400);page.locator('.used-photo-tile[data-key=whole] .photo-tile-open').click();expect(page.locator('.original-status')).to_contain_text('4000 × 3000');page.locator('[data-v=close]').click();page.wait_for_timeout(150)
  page.locator('[data-act=used-save]').click();expect(page.locator('.system-error')).to_be_visible();page.locator('.system-error button').click();expect(page.locator('#web-photo-jobs')).to_contain_text('저장 대기')
  page.locator('[name=model_id]').select_option(model);page.locator('[name=color_id]').select_option(color);page.locator('[name=exterior]').fill('신규 기록 보존')
  page.locator('[data-act=used-step][data-step="2"]').first.click();expect(page.locator('.used-inspection-board')).to_be_visible();expect(page.locator('#web-photo-jobs')).to_be_empty()
  new_state=client.get('/api/state').json();new_id=next(v['id'] for v in new_state['vehicles'] if v['id']!=vid);new_data=client.get('/api/used/'+new_id).json();assert len(new_data['media'])==1 and not new_data['ready'];assert new_data['profile']['exterior']=='신규 기록 보존'
  page.locator('[data-act=used-step][data-step="1"]').first.click();assert page.locator('[name=exterior]').input_value()=='신규 기록 보존'
  page.locator('[name=exterior]').fill('취소 보호');page.once('dialog',lambda d:d.dismiss());page.locator('#modal .modal-head [data-act=close]').click();expect(page.locator('#modal')).to_be_visible();assert page.locator('[name=exterior]').input_value()=='취소 보호'
  print('EXTENDED UI PASS: intake/damage/wear multi-drop, 13 hotspots, partial retry, server format validation, replacement cancel, outside-drop protection, bridge compatibility, touch pinch, browser/native back, new-vehicle pending, draft protection',flush=True)
  print('INITIAL UI PASS: 6 directions, high-res viewer, download hash, state preservation, responsive sizes',flush=True)
  assert not errors,errors
  browser.close()
except Exception:
 print('PAGE ERRORS',errors,flush=True)
 try: page.screenshot(path=str(OUT/'failure.png'));print('MODALS',page.locator('dialog').evaluate_all('(ds)=>ds.map(d=>({open:d.open,cls:d.className,text:d.innerText.slice(0,400)}))'),flush=True)
 except Exception:pass
 raise
finally:
 stop(runtime)
