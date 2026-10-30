import sys,httpx,json
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
from browser_support import start,stop,CHROME,PASSWORD
from playwright.sync_api import sync_playwright,expect
r=start()
try:
 c=httpx.Client(base_url=r[3],trust_env=False);token=c.post('/api/login',json={'username':'admin','password':PASSWORD}).json()['token'];c.headers['Authorization']='Bearer '+token
 today=c.get('/api/state').json()['today'];month=today[:7]
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path=CHROME,headless=True);page=b.new_page();page.goto(r[3]);page.evaluate('(t)=>sessionStorage.setItem("warehouseToken",t)',token);page.reload();expect(page.locator('.sidebar')).to_be_visible()
  page.locator('.nav-section>summary',has_text='마감·보고').click();page.locator('.sidebar [data-page=parts]').click();expect(page.locator('[data-part=day]').first).to_be_visible()
  held=[]
  def hold(route):held.append((route,c.get(route.request.url).json()))
  page.route('**/api/parts?*',hold)
  page.evaluate('(d)=>{const e=document.querySelector("#parts-day");e.value=d;e.dispatchEvent(new Event("change"));}',month+'-02');page.wait_for_timeout(150)
  page.evaluate('(d)=>{const e=document.querySelector("#parts-day");e.value=d;e.dispatchEvent(new Event("change"));}',month+'-03');page.wait_for_timeout(150)
  assert len(held)>=2;held=held[-2:]
  held[1][1]['report']['totals']['inbound']=333;held[0][1]['report']['totals']['inbound']=222
  held[1][0].fulfill(json=held[1][1]);page.wait_for_timeout(150)
  latest=page.locator('#content').inner_text()
  held[0][0].fulfill(json=held[0][1]);page.wait_for_timeout(150)
  final=page.locator('#content').inner_text();print('PARTS_RACE',json.dumps({'selected_input':page.locator('#parts-day').input_value(),'second_response_then_old_changed_view':final!=latest,'stale_222_visible':'222' in final},ensure_ascii=False))
  assert final==latest and '333' in final and '222' not in final
  result=page.evaluate("""async()=>{const {mountCustomerEditor}=await import('/customers.js');const root=document.createElement('div');document.body.append(root);let pages=0;mountCustomerEditor(root,{esc:x=>x,api:async(path,options)=>{const body=JSON.parse(options.body);pages++;return body.after?{items:[{id:'last',name:'합성 후속업체',kind:'COMPANY'}],next:null}:{items:Array.from({length:20},(_,i)=>({id:'company'+i,name:'합성 '+i,kind:'COMPANY'})),next:'company19'};}});root.querySelector('[data-name]').value='합성';root.querySelector('[data-name]').dispatchEvent(new Event('input'));await new Promise(r=>setTimeout(r,350));root.querySelector('[data-customer-next]')?.scrollIntoView();await new Promise(r=>setTimeout(r,250));root.querySelector('[data-choice="last"]').click();const id=await root.saveCustomer();root.remove();return {pages,id};}""")
  assert result=={'pages':2,'id':'last'},result
  network=[];page.on('request',lambda req:network.append(req.url));page.wait_for_timeout(11000)
  assert not any(url.endswith('/api/state') for url in network),network
  assert sum('/api/state/version' in url for url in network)>=2,network
  print('PASS stale date response ignored; customer pagination selected; unchanged polling uses version only')
  b.close()
finally:stop(r)
