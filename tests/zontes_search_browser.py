"""Real Chrome + isolated server; synthetic inventory and vehicles only."""
import uuid,json,httpx
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,observe,PASSWORD,CHROME,RESULTS
runtime=start(demo=False)
try:
 c=httpx.Client(base_url=runtime[3],trust_env=False,timeout=30)
 token=c.post('/api/login',json={'username':'admin','password':PASSWORD}).json()['token'];c.headers['Authorization']='Bearer '+token
 def cmd(action,payload):
  r=c.post('/api/command',json={'command_id':str(uuid.uuid4()),'action':action,'payload':payload});r.raise_for_status();return r.json()
 def state():return c.get('/api/state').json()
 def vehicle(vid):return next(v for v in state()['vehicles'] if v['id']==vid)
 def vc(action,vid,**p):return cmd(action,dict(vehicle_id=vid,version=vehicle(vid)['version'],**p))
 today=state()['today']
 def parts():return c.get('/api/parts',params={'day':today,'month':today[:7]}).json()
 def pcmd(action,**p):
  r=c.post('/api/parts/command',json=dict(action=action,revision=parts()['revision'],request_id=str(uuid.uuid4()),**p));r.raise_for_status();return r.json()
 brand=cmd('master',{'kind':'brand','name':'Synthetic'})['id'];model=cmd('master',{'kind':'model','name':'368G','detail':{'brand_id':brand}})['id'];color=cmd('master',{'kind':'color','name':'Silver'})['id']
 from server.parts_orders import TEMPLATES
 rules=parts()['rules'];rules['models'][model]={**TEMPLATES['ZONTES368G'],'preinstalled_bracket':True,'defaults':{'B2B':['SC','CUP','MITT'],'B2C':['SC']}};pcmd('rules',rules=rules)
 pcmd('stocktake',day=today,reason='synthetic baseline',quantities={i['id']:100 for i in parts()['items']})
 ids=[cmd('receive',{'vin':('MLHJK05A1P5000001' if n==1 else 'MLHJK05B1P5000001'),'kind':'NEW','model_id':model,'color_id':color,'year':2026})['vehicle_id'] for n in [1,2]]
 cmd('zone',{'name':'Synthetic swap','rows':1,'cols':3,'kind':'STORAGE','x':20,'y':20})
 slots=next(z['slots'] for z in state()['layout']['zones'] if z['name']=='Synthetic swap')
 for n,vid in enumerate(ids):vc('move',vid,slot_id=slots[n]['id'])

 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page(viewport={'width':1366,'height':900});errors=observe(page,'search-and-zontes')
  page.goto(runtime[3]);assert page.locator('.login').count();page.evaluate('(t)=>sessionStorage.setItem("warehouseToken",t)',token);page.reload()
  query=page.locator('#global-search');query.fill(' 0001 ');page.locator('#global-search-form button').click();expect(page.locator('#content .badge').first).to_have_text('2');expect(page.locator('#modal')).not_to_be_visible()
  page.locator('#global-search').fill(' mlhjk05a1p5000001 ');page.locator('#global-search').press('Enter');expect(page.locator('#content .badge').first).to_have_text('1');expect(page.locator('#global-search')).to_have_value('MLHJK05A1P5000001')
  page.locator('#list-search').fill('9999');page.locator('#list-search-form button[type=submit]').click();expect(page.locator('#content')).to_contain_text('검색 결과가 없습니다.')
  page.locator('#global-search').fill('0001');page.locator('#global-search').dispatch_event('compositionstart');page.locator('#global-search').dispatch_event('keydown',{'key':'Enter','isComposing':True,'keyCode':229});page.locator('#global-search-form').dispatch_event('submit');expect(page.locator('#content')).to_contain_text('검색 결과가 없습니다.');page.locator('#global-search').dispatch_event('compositionend');page.locator('#global-search').press('Enter');expect(page.locator('#content .badge').first).to_have_text('2')
  for width,height in [(390,844),(720,900),(844,390),(1366,900)]:
   page.set_viewport_size({'width':width,'height':height});expect(page.locator('#global-search-form button')).to_be_visible();box=page.locator('#global-search-form button').bounding_box();assert box['x']>=0 and box['x']+box['width']<=width;assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');page.screenshot(path=str(RESULTS/f'search-{width}.png'))
  page.locator(f'[data-act=detail][data-id="{ids[0]}"]').first.click();expect(page.locator('#modal')).to_contain_text('입고 기본 장착');page.locator('[data-act=assign][data-channel=B2B]').click();expect(page.locator('[data-plan-result]')).to_contain_text('토시');expect(page.locator('[data-plan-result]')).to_contain_text('입고 기본 장착 · 작업 없음');page.locator('[data-op=set]').select_option('TOP01');page.locator('[data-plan-preview]').click();page.locator('[data-act=save-assign]').click();expect(page.locator('#modal')).to_contain_text('주문 ow')
  a=vehicle(ids[0])['assignment'];assert {l['item']['part_id'] for l in a['options']}=={'SC','CUP','MITT','ST01'};assert not any(l['item']['part_id']=='RBZ' for l in a['options']);page.screenshot(path=str(RESULTS/'zontes-work.png'))
  for l in a['options']:vc('work_line',ids[0],kind='options',line_id=l['id'],done=l['qty'])
  vc('dispatch',ids[0],exception_reason='synthetic dispatch',handed={});page.evaluate('document.querySelector("#modal").close()');page.reload();page.locator('[data-act=nav][data-page=outbound]').first.click();page.locator('#global-search').fill('0001');page.locator('#global-search-form button').click();expect(page.locator('#content h1')).to_have_text('출고이력');expect(page.locator('[data-act=out-detail]')).to_have_count(1)
  page.locator('[data-act=nav][data-page=parts]').first.click();page.locator('.dispatch-vehicle summary').click();expect(page.locator('.dispatch-vehicle')).to_contain_text('입고 기본 장착품 · 차감 없음');page.screenshot(path=str(RESULTS/'zontes-summary.png'))
  # Rapid submissions are handled once; search never confirms a vehicle automatically.
  page.locator('[data-act=nav][data-page=stock]').first.click();page.locator('#global-search').fill('0001');page.locator('#global-search-form').evaluate('(form)=>{form.requestSubmit();form.requestSubmit();form.requestSubmit()}');expect(page.locator('#modal')).not_to_be_visible()
  assert not errors['pageerror'],errors
  (RESULTS/'browser-result.json').write_text(json.dumps({'passed':True,'scenarios':['button','Enter','full VIN','duplicate suffix','empty','IME composition','responsive','factory equipment','B2B work','outbound scope','summary','rapid submit'],'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8');browser.close()
 print('PASS isolated Chrome search and Zontes workflows')
finally:stop(runtime)
