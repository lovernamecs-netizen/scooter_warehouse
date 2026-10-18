import uuid,httpx,json
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,PASSWORD,CHROME,RESULTS,observe
runtime=start();base=runtime[3]
try:
 c=httpx.Client(base_url=base,trust_env=False);token=c.post('/api/login',json={'username':'admin','password':PASSWORD}).json()['token'];c.headers['Authorization']='Bearer '+token
 def state():return c.get('/api/state').json()
 def cmd(action,payload):
  r=c.post('/api/command',json={'command_id':str(uuid.uuid4()),'action':action,'payload':payload});r.raise_for_status();return r.json()
 def vehicle(ident):return next(v for v in state()['vehicles'] if v['id']==ident)
 model=next(m['id'] for m in state()['masters'] if m['kind']=='model');color=next(m['id'] for m in state()['masters'] if m['kind']=='color')
 warehouses=[];zones=[]
 for i in range(2):
  wh=cmd('warehouse',{'revision':state()['revision'],'name':'Synthetic '+str(i),'width':1000,'height':800})['id'];warehouses.append(wh)
  cmd('zone',{'warehouse_id':wh,'name':'Zone '+str(i),'rows':2,'cols':2,'x':20,'y':20,'kind':'STORAGE'});zones.append(next(z for z in state()['layout']['zones'] if z['warehouse_id']==wh))
 ids=[]
 for i in range(2):
  ident=cmd('receive',{'vin':'MLHJK05A1P500004'+str(i),'kind':'NEW','model_id':model,'color_id':color,'year':2026})['vehicle_id'];ids.append(ident)
  cmd('move',{'vehicle_id':ident,'version':vehicle(ident)['version'],'slot_id':zones[i]['slots'][-1]['id']})
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page(viewport={'width':1366,'height':768});observed=observe(page,'map')
  page.goto(base);page.evaluate('(t)=>sessionStorage.setItem("warehouseToken",t)',token);page.reload();page.locator('[data-act=nav][data-page=stock]').first.click();page.locator(f'[data-act=detail][data-id="{ids[0]}"]').first.click();page.locator('.vehicle-history summary').first.click();page.locator('[data-act=move]').click()
  page.locator('#warehouse-select').select_option(warehouses[1]);page.locator(f'[data-slot="{zones[1]["slots"][-1]["id"]}"]').click();expect(page.locator('#toast')).to_contain_text('빈자리');expect(page.locator('#modal')).not_to_be_visible();assert vehicle(ids[0])['location']['warehouse_id']==warehouses[0]
  page.locator(f'[data-slot="{zones[1]["slots"][0]["id"]}"]').click();page.locator('[data-act=save-move]').click();expect(page.locator('#modal')).not_to_be_visible();assert vehicle(ids[0])['location']['warehouse_id']==warehouses[1]
  page.locator('[data-act=zoom][data-delta="0.1"]').click();zoom=page.locator('#map-zoom-label').inner_text();page.locator('[data-act=edit-map]').click();page.locator(f'[data-act=zone][data-id="{zones[1]["id"]}"]').click();page.locator('[name=rows]').fill('1');page.locator('[name=cols]').fill('1');page.locator('[data-act=save-zone]').click();expect(page.locator('.system-error')).to_be_visible();assert next(z for z in state()['layout']['zones'] if z['id']==zones[1]['id'])['rows']==2;assert vehicle(ids[1])['location']['slot_id']==zones[1]['slots'][-1]['id'];page.locator('.system-error button').click();expect(page.locator('[name=rows]')).to_have_value('1');assert page.locator('#map-zoom-label').inner_text()==zoom
  page.screenshot(path=str(RESULTS/'occupied-zone-error.png'));assert not observed['pageerror'];browser.close()
 print('map UI cross-warehouse move, occupied slot rejection, occupied zone shrink rollback, zoom/draft preservation passed')
finally:stop(runtime)
