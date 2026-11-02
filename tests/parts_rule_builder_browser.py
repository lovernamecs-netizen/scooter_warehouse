import uuid,httpx
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,observe,nav,PASSWORD,CHROME,RESULTS
runtime=start(demo=False)
try:
 c=httpx.Client(base_url=runtime[3],trust_env=False,timeout=30);token=c.post('/api/login',json={'username':'admin','password':PASSWORD}).json()['token'];c.headers['Authorization']='Bearer '+token
 def get():return c.get('/api/parts',params={'day':'2026-11-01','month':'2026-11'}).json()
 def cmd(action,**payload):
  r=c.post('/api/parts/command',json={'action':action,'revision':get()['revision'],'request_id':str(uuid.uuid4()),**payload});r.raise_for_status();return r.json()
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page(viewport={'width':1366,'height':900});errors=observe(page,'parts-rule-builder')
  page.goto(runtime[3]);page.evaluate('(t)=>sessionStorage.setItem("warehouseToken",t)',token);page.reload();nav(page,'parts');page.locator('.parts-tools summary').click();page.locator('[data-part=rules]').click()
  expect(page.locator('#parts-rule-builder')).to_be_visible()
  page.locator('[data-rb=tab][data-tab=B2C]').click()
  page.locator('[data-rb=select][data-id=MITT]').drag_to(page.locator('[data-zone=base]'))
  expect(page.locator('[data-rb=remove][data-id=MITT]')).to_have_count(1)
  page.locator('[data-rb=save]').click();expect(page.locator('#modal')).not_to_be_visible();assert 'MITT' in get()['rules']['defaults']['B2C']
  cmd('item',item={'code':'NEWCARD','name':'추가 품목','purpose':'INSTALL'})
  page.locator('.parts-tools summary').click();page.locator('[data-part=rules]').click();expect(page.locator('.rb-item',has_text='NEWCARD')).to_be_visible()
  page.locator('[data-rb=tab][data-tab=B2C]').click();page.locator('[data-rb=remove][data-id=MITT]').click()
  new=next(i for i in get()['items'] if i['code']=='NEWCARD');new.update(code='RENAMED',name='변경된 이름');cmd('item',item=new)
  page.locator('[data-rb=save]').click();expect(page.locator('[data-rb-message]')).to_contain_text('최신 자료');assert 'MITT' in get()['rules']['defaults']['B2C']
  page.on('dialog',lambda d:d.accept());page.locator('[data-rb=reload]').click();expect(page.locator('.rb-item',has_text='RENAMED')).to_be_visible()
  page.locator('[data-rb=remove][data-id=MITT]').click();page.locator('[data-rb=save]').click();expect(page.locator('#modal')).not_to_be_visible();assert 'MITT' not in get()['rules']['defaults']['B2C']
  page.locator('.parts-tools summary').click();page.locator('[data-part=rules]').click();page.screenshot(path=str(RESULTS/'parts-builder-live-desktop.png'))
  page.set_viewport_size({'width':390,'height':844});page.locator('[data-rb=tab][data-tab=B2C]').click();page.locator('[data-rb=select][data-id=MITT]').click();page.locator('[data-rb=add][data-slot=base]').click();expect(page.locator('[data-rb=remove][data-id=MITT]')).to_have_count(1)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');page.screenshot(path=str(RESULTS/'parts-builder-live-mobile.png'))
  page.locator('[data-rb=save]').click();expect(page.locator('#modal')).not_to_be_visible()
  inactive=next(i for i in get()['items'] if i['id']=='MITT');inactive['active']=False;cmd('item',item=inactive)
  page.locator('.parts-tools summary').click();page.locator('[data-part=rules]').click();page.locator('[data-rb=tab][data-tab=B2C]').click();expect(page.locator('.rb-invalid')).to_contain_text('사용 중지')
  expect(page.locator('[data-rb=select][data-id=MITT]')).to_have_count(0)
  page.locator('[data-rb=remove][data-id=MITT]').click();page.locator('[data-rb=tab][data-tab=B2B]').click();page.locator('[data-rb=remove][data-id=MITT]').click()
  # Persist the first request but lose its response: retry must reuse request ID.
  revision=get()['revision'];attempts=[]
  def lost_response(route):
   attempts.append(route.request.post_data_json['request_id'])
   if len(attempts)==1:route.fetch();route.abort('failed')
   else:route.continue_()
  page.route('**/api/parts/command',lost_response)
  page.locator('[data-rb=save]').click();expect(page.locator('[data-rb-message]')).to_contain_text('연결')
  page.locator('[data-rb=save]').click();expect(page.locator('#modal')).not_to_be_visible()
  assert len(attempts)==2 and attempts[0]==attempts[1] and get()['revision']==revision+1
  # Configure a real synthetic model and exercise the paired set slots.
  def master(kind,name,detail=None):
   r=c.post('/api/command',json={'command_id':str(uuid.uuid4()),'action':'master','payload':{'kind':kind,'name':name,'detail':detail or {}}});r.raise_for_status();return r.json()['id']
  brand=master('brand','테스트');model=master('model','PCX 합성',{'brand_id':brand})
  rules=get()['rules'];rules['models'][model]={'slide':'SSP','bracket':'RBP'};cmd('rules',rules=rules)
  page.locator('.parts-tools summary').click();page.locator('[data-part=rules]').click();page.locator('[data-rb=tab][data-tab=SETS]').click();page.locator('[data-rb-field=model]').select_option(model)
  page.locator('[data-rb-field=set]').select_option('EPP');page.locator('[data-rb=mode][data-slot=item]').click()
  page.locator('[data-rb=save]').click();expect(page.locator('#modal')).not_to_be_visible();assert get()['rules']['sets']['EPP']['modes']['item']=='DELIVERY'
  assert get()['rules']['models'][model]['slide']=='SSP'
  assert not errors['pageerror'],errors
  browser.close()
 print('PASS live browser: drag/drop, save, item create/rename, stale conflict/reload, mobile tap and no overflow')
finally:stop(runtime)
