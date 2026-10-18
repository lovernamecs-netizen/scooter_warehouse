"""Windows Chrome integration checks using an isolated server/DB and synthetic originals."""
from pathlib import Path
import sys,os,io,uuid,json,hashlib,base64,time
from PIL import Image,ImageDraw
import httpx
from playwright.sync_api import sync_playwright,expect
from browser_support import stop,PASSWORD
import tempfile,subprocess

from browser_support import start,stop,observe

OUT=Path(__file__).resolve().parents[2]/'closing-results';OUT.mkdir(exist_ok=True)
runtime=start(demo=False);base=runtime[3];errors=[]
try:
 client=httpx.Client(base_url=base,trust_env=False,timeout=30)
 token=client.post('/api/login',json={'username':'admin','password':PASSWORD}).json()['token'];client.headers['Authorization']='Bearer '+token
 def cmd(action,payload):
  r=client.post('/api/command',json={'command_id':str(uuid.uuid4()),'action':action,'payload':payload});r.raise_for_status();return r.json()
 def pdata():
  today=client.get('/api/state').json()['today'];return client.get('/api/parts',params={'day':today,'month':today[:7]}).json()
 def pcmd(action,**payload):
  r=client.post('/api/parts/command',json={'action':action,'request_id':str(uuid.uuid4()),'revision':pdata()['revision'],**payload});r.raise_for_status();return r.json()
 brand=cmd('master',{'kind':'brand','name':'Synthetic Brand'})['id'];model=cmd('master',{'kind':'model','name':'Synthetic PCX','detail':{'brand_id':brand}})['id'];color=cmd('master',{'kind':'color','name':'Silver'})['id']
 vid=cmd('receive',{'vin':'MLHJK05A1P5000001','kind':'NEW','model_id':model,'color_id':color,'year':2026})['vehicle_id']
 pcmd('stocktake',day='2020-01-01',reason='synthetic baseline',quantities={i['id']:'100' for i in pdata()['items']})
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
  page=browser.new_page(viewport={'width':1366,'height':900});page.on('pageerror',lambda e:errors.append(str(e)));observe(page,'closing')
  page.goto(base);page.evaluate('(t)=>sessionStorage.setItem("warehouseToken",t)',token);page.reload()
  cmd('zone',{'name':'Hold test','rows':1,'cols':2,'kind':'STORAGE','x':20,'y':20})
  st=client.get('/api/state').json();z=next(z for z in st['layout']['zones'] if z['name']=='Hold test');v=next(v for v in st['vehicles'] if v['id']==vid)
  cmd('move',{'vehicle_id':vid,'version':v['version'],'slot_id':z['slots'][0]['id']})
  page.reload();page.locator('[data-act=nav][data-page=map]').first.click()
  card=page.locator(f'.slot[data-vehicle="{vid}"]');card.click();expect(page.locator('#modal')).to_be_visible()
  page.locator('#modal [data-act=assign][data-channel=B2C]').click();expect(page.locator('[data-op=channel]')).to_have_value('B2C');page.evaluate('document.querySelector("#modal").close()')
  card.scroll_into_view_if_needed();box=card.bounding_box();page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);page.mouse.down();page.wait_for_timeout(2200);page.mouse.up();page.wait_for_timeout(500)
  expect(page.locator('[data-act=cancel-move]')).to_be_visible();expect(page.locator('#modal')).not_to_be_visible()
  assert next(v for v in client.get('/api/state').json()['vehicles'] if v['id']==vid)['location']['slot_id']==z['slots'][0]['id']
  page.locator(f'.slot[data-slot="{z["slots"][1]["id"]}"]').click();expect(page.locator('#modal')).to_contain_text('위치이동 확인');page.locator('[data-act=save-move]').click();expect(page.locator('#modal')).not_to_be_visible()
  assert next(v for v in client.get('/api/state').json()['vehicles'] if v['id']==vid)['location']['slot_id']==z['slots'][1]['id']
  card.scroll_into_view_if_needed();box=card.bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
  cdp=page.context.new_cdp_session(page)
  cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]});page.wait_for_timeout(2200);cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]});page.wait_for_timeout(500)
  expect(page.locator('[data-act=cancel-move]')).to_be_visible();page.keyboard.press('Escape');expect(page.locator('[data-act=cancel-move]')).to_have_count(0)
  card.scroll_into_view_if_needed();box=card.bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
  cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]});cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x+35,'y':y}]});page.wait_for_timeout(2200);cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
  expect(page.locator('[data-act=cancel-move]')).to_have_count(0)
  page.locator('[data-act=nav][data-page=parts]').first.click();expect(page.locator('.parts-toolbar summary')).to_be_visible()
  assert page.locator('[data-part=refresh],[data-part=warehouse]').count()==0
  page.locator('.parts-toolbar summary').click();page.locator('[data-part=rules]').click()
  page.locator('[data-template]').select_option('PCX');page.locator('[data-part=save-rules]').click();expect(page.locator('#modal')).not_to_be_visible()
  page.locator('.parts-toolbar summary').click();page.locator('[data-part=movement]').click();page.locator('.part-item').select_option('SSP');page.locator('.part-boxes').fill('2');page.locator('.part-loose').fill('1');expect(page.locator('.part-converted')).to_have_text('5EA');page.locator('[name=reason]').fill('Synthetic receipt');page.locator('[data-part=save-movement]').click();expect(page.locator('#modal')).not_to_be_visible()
  page.locator('.parts-toolbar summary').click();page.locator('[data-part=stocktake]').click();assert page.locator('#modal [name=day]').input_value()=='';page.locator('[data-part=stock-draft]').click();assert page.locator('[data-count=SSP]').input_value()=='51';assert page.locator('[data-count=ST02]').input_value()=='-'
  page.evaluate('document.querySelector("#modal").close()')
  page.locator('[data-act=nav][data-page=stock]').first.click();page.locator(f'[data-act=detail][data-id="{vid}"]').first.click();page.locator('#modal [data-act=assign][data-channel=B2B]').click()
  expect(page.locator('[data-op=channel]')).to_be_visible();expect(page.locator('[name=number]')).to_be_disabled();assert page.locator('[data-op=channel]').input_value()=='B2B'
  expect(page.locator('[data-op=channel]')).to_be_disabled();expect(page.locator('[data-op=screen]')).not_to_be_visible()
  expect(page.locator('[data-plan-extras]')).not_to_have_attribute('open','');expect(page.locator('.order-parts-table')).not_to_be_visible()
  page.locator('#order-parts-editor details summary').click();expect(page.locator('.order-parts-table')).to_be_visible()
  for part,purpose in [('SC','INSTALL'),('WPCX_0','INSTALL')]:page.locator(f'[data-op-id="{part}"] [data-col=purpose]').select_option(purpose)
  page.locator('[data-op=set]').select_option('EPP');page.locator('[data-set-mode=item]').select_option('DELIVERY');page.locator('[data-set-mode=component]').select_option('OMIT');page.locator('[data-plan-preview]').click();expect(page.locator('[data-plan-result]')).to_contain_text('SE');expect(page.locator('[data-plan-result]')).not_to_contain_text('SSP');page.locator('[data-set-mode=component]').select_option('DELIVERY');page.locator('[data-plan-preview]').click();expect(page.locator('[data-plan-result]')).to_contain_text('SSP')
  page.locator('[data-plan-extras] summary').click();expect(page.locator('.plan-card-title strong').first).to_be_visible();page.locator('[data-plan-result]').scroll_into_view_if_needed();page.screenshot(path=str(OUT/'plan-cards.png'));
  page.locator('[data-op=channel]').scroll_into_view_if_needed();page.screenshot(path=str(OUT/'order-desktop.png'))
  for width,height in [(390,844),(320,640)]:
   page.set_viewport_size({'width':width,'height':height});assert page.locator('#modal').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1');page.screenshot(path=str(OUT/f'order-{width}.png'))
  page.set_viewport_size({'width':1366,'height':900})
  page.locator('[data-act=save-assign]').click();expect(page.locator('#modal')).to_contain_text('주문 ow001')
  state=client.get('/api/state').json();v=next(v for v in state['vehicles'] if v['id']==vid);assert v['assignment']['parts_order']['channel']=='B2B';assert all(r['purpose']=='DELIVERY' for r in v['assignment']['parts_order']['lines'] if r['part_id'] in ['SE','SSP'])
  page.locator('.vehicle-history summary').first.click();page.locator('[data-act=ubis-set]').click();page.locator('[data-act=save-ubis]').click();expect(page.locator('#modal')).to_contain_text('U 설치완료')
  for kind in ['options','items']:
   for line in v['assignment'][kind]:
    page.locator(f'[data-act=work-all][data-line="{line["id"]}"]').click()
    if kind=='options':expect(page.locator(f'[data-act=work-all][data-line="{line["id"]}"]')).to_have_class('active')
    else:expect(page.locator(f'#qty-{line["id"]}')).to_have_value(str(line['qty']))
  page.locator('[data-action=finish_work]').click();expect(page.locator('[data-action=ready]')).to_be_visible();page.locator('[data-action=ready]').click();page.locator('[data-act=stage-ready]').click();expect(page.locator('[data-act=dispatch]')).to_be_visible();page.locator('[data-act=dispatch]').click()
  assert page.locator('#confirm-vin').count()==0
  sent=[]
  def capture_request(req):
   if req.url.endswith('/api/command') and req.method=='POST' and req.post_data_json.get('action')=='dispatch':sent.append(req.post_data_json)
  page.on('request',capture_request)
  for el in page.locator('input[id^="hand-"]').all():el.fill('1')
  page.locator('[data-act=save-dispatch]').dblclick();expect(page.locator('#modal')).not_to_be_visible()
  assert len(client.get('/api/outbound').json())==1
  assert sent;retry=client.post('/api/command',json=sent[0]);retry.raise_for_status();assert len(client.get('/api/outbound').json())==1
  assert len([e for e in pdata()['outbounds'] if e.get('id')])==1
  page.evaluate('document.querySelector("#modal").close()');page.locator('[data-act=nav][data-page=parts]').first.click()
  for width,height in [(1366,900),(1920,1080),(390,844),(320,640),(844,390)]:
   page.set_viewport_size({'width':width,'height':height});page.wait_for_timeout(100)
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(width,'page overflow')
   page.locator('.parts-toolbar summary').click()
   box=page.locator('.parts-tools-grid').bounding_box();assert box['x']>=0 and box['x']+box['width']<=width,(width,box)
   expect(page.locator('[data-part=movement]')).to_be_visible()
   page.screenshot(path=str(OUT/f'menu-{width}.png'))
   page.locator('.parts-toolbar summary').click()
   page.screenshot(path=str(OUT/f'inventory-{width}x{height}.png'),full_page=True)
  page.set_viewport_size({'width':1366,'height':900})
  assert page.locator('[data-part=paste],[data-part=warehouse],[data-part=resume]').count()==0
  page.locator('.parts-toolbar summary').click();page.locator('[data-part=movement]').click();page.locator('[name=reason]').fill('충돌 후 보존')
  pcmd('movement',day=client.get('/api/state').json()['today'],kind='IN',reason='동시 작업',lines=[{'item_id':'SC','qty':1}])
  page.locator('[data-part=save-movement]').click();expect(page.locator('.system-error')).to_be_visible();page.locator('.system-error button').click();assert page.locator('[name=reason]').input_value()=='충돌 후 보존'
  page.locator('[data-part=save-movement]').click();expect(page.locator('#modal')).not_to_be_visible()
  assert not errors,errors
  browser.close()
 (OUT/'browser-results.json').write_text(json.dumps({'passed':True,'checks':['mouse/touch 2 second hold and confirmed move','pan cancels hold','Escape cancels move','short click and B2C choice','browser work/ready/dispatch double click and identical replay','rules model ID','movement BOX/EA','undated stocktake draft','new order B2B plan preview/save','legacy paste removed','grouped management bounds','responsive five sizes'],'page_errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
 print('closing browser checks passed')
finally:stop(runtime)
