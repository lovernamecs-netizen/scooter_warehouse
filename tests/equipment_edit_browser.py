import json,uuid,httpx
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,observe,PASSWORD,CHROME,RESULTS
from server.parts_orders import TEMPLATES
runtime=start(demo=False)
try:
 c=httpx.Client(base_url=runtime[3],trust_env=False,timeout=30);token=c.post('/api/login',json={'username':'admin','password':PASSWORD}).json()['token'];c.headers['Authorization']='Bearer '+token
 def command(action,payload):
  r=c.post('/api/command',json={'command_id':str(uuid.uuid4()),'action':action,'payload':payload});r.raise_for_status();return r.json()
 def state():return c.get('/api/state').json()
 def vehicle(vid):return next(v for v in state()['vehicles'] if v['id']==vid)
 def vc(action,vid,**p):return command(action,dict(vehicle_id=vid,version=vehicle(vid)['version'],**p))
 brand=command('master',{'kind':'brand','name':'Synthetic'})['id'];model=command('master',{'kind':'model','name':'HUSKY125','detail':{'brand_id':brand}})['id'];color=command('master',{'kind':'color','name':'Black'})['id'];today=state()['today']
 parts=c.get('/api/parts',params={'day':today,'month':today[:7]}).json();rules=parts['rules'];rules['models'][model]=TEMPLATES['HUSKY'];r=c.post('/api/parts/command',json={'action':'rules','rules':rules,'revision':parts['revision'],'request_id':str(uuid.uuid4())});r.raise_for_status()
 vid=command('receive',{'vin':'MLHJK05A1P5000001','kind':'NEW','model_id':model,'color_id':color,'year':2026})['vehicle_id']
 vc('assign',vid,scheduled=today,parts_order={'channel':'B2C','purposes':{'SC':'INSTALL'}})
 for line in vehicle(vid)['assignment']['options']:vc('work_line',vid,kind='options',line_id=line['id'],done=line['qty'])
 vc('cancel_order',vid,reason='synthetic cancelled order');vc('assign',vid,scheduled=today,parts_order={'channel':'B2C','purposes':{'SC':'INSTALL'},'omit_lines':['SC:INSTALL']})
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page(viewport={'width':1366,'height':900});errors=observe(page,'equipment-edit')
  page.goto(runtime[3]);page.evaluate('(t)=>sessionStorage.setItem("warehouseToken",t)',token);page.reload();page.locator('#global-search').fill('0001');page.locator('#global-search-form button').click();page.locator(f'[data-act=detail][data-id="{vid}"]').first.click()
  expect(page.locator('#modal')).to_contain_text('취소된 주문 장착품');page.locator('[data-act=equipment-edit][data-mode=carry]').click();expect(page.locator('#modal')).to_contain_text('실제 출고 때 차감')
  page.locator('#modal [name=reason]').fill('실제 장착 유지');page.locator('#modal [name=confirmed]').check();page.locator('[data-act=save-equipment-edit]').click();expect(page.locator('#modal')).to_contain_text('차량 상세');assert not page.locator('[data-mode=carry]').count()
  sc=next(e for e in vehicle(vid)['equipment'] if e['item'].get('part_id')=='SC');assert next(l for l in vehicle(vid)['assignment']['options'] if l['item'].get('part_id')=='SC')['done']==1
  page.screenshot(path=str(RESULTS/'equipment-carried-desktop.png'))
  page.set_viewport_size({'width':390,'height':844});button=page.locator(f'[data-act=equipment-edit][data-equipment="{sc["id"]}"][data-mode=correct]');button.scroll_into_view_if_needed();expect(button).to_be_visible();assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');page.screenshot(path=str(RESULTS/'equipment-correction-mobile.png'));button.click()
  page.locator('#modal [name=reason]').fill('잘못된 완료 체크');page.locator('#modal [name=confirmed]').check();page.locator('[data-act=save-equipment-edit]').click();expect(page.locator('#modal')).to_contain_text('차량 상세')
  assert not any(e['item'].get('part_id')=='SC' for e in vehicle(vid)['equipment']);assert next(l for l in vehicle(vid)['assignment']['options'] if l['item'].get('part_id')=='SC')['done']==0
  page.locator('[data-act=parts-plan]').click();expect(page.locator('#order-parts-editor')).to_be_visible()
  assert not errors['pageerror'] and not errors['console_error'] and not errors['requestfailed'],errors
  (RESULTS/'equipment-browser-result.json').write_text(json.dumps({'passed':True,'checks':['cancelled label','carry UI','current completion retained','mobile correction UI','work reset','parts editor accessible'],'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8');browser.close()
 print('PASS isolated equipment correction browser workflow')
finally:stop(runtime)
