import httpx
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,CHROME,PASSWORD,RESULTS
r=start()
try:
 token=httpx.post(r[3]+'/api/login',json={'username':'admin','password':PASSWORD},trust_env=False).json()['token']
 today=httpx.get(r[3]+'/api/state',headers={'Authorization':'Bearer '+token},trust_env=False).json()['today'];month=today[:7]
 rows=[{'id':str(i),'vehicle_id':str(i),'day':month+'-02','at':month+'-02T01:00:00Z','snapshot':{'vehicle':{'vin':'TEST'+str(i),'model':'합성 차종'},'options':[],'items':[]},'adjustments':[{'kind':'VOID'}] if i==2 else [{'kind':'RETURN'}] if i==1 else []} for i in range(3)]
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page(viewport={'width':1280,'height':950});errors=[];requests=[]
  page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
  page.goto(r[3]);page.evaluate('(t)=>sessionStorage.setItem("warehouseToken",t)',token);page.reload()
  page.route('**/api/outbound?month=*',lambda route:route.fulfill(json=rows if route.request.url.endswith(month) else []))
  page.route('**/api/customers/outbounds',lambda route:route.fulfill(json={'0':{'name':'합성 업체 <테스트>','kind':'COMPANY'},'1':{'name':'합성 주문자','kind':'PERSON'},'2':None}))
  page.locator('.nav-section>summary',has_text='주문·출고').click();expect(page.locator('.sidebar [data-page=schedule]')).to_have_count(0)
  page.locator('.sidebar [data-page=outbound]').click()
  expect(page.locator('.dispatch-month-totals')).to_contain_text('월 실제 출고 2대')
  page.locator('[data-dispatch=day][data-day="'+month+'-02"]').click();expect(page.locator('#content')).to_contain_text('출고취소')
  expect(page.locator('#content')).to_contain_text('출고 후 반품')
  expect(page.locator('[data-outbound-customer="0"]')).to_have_text('합성 업체 <테스트>')
  expect(page.locator('[data-outbound-customer="1"]')).to_have_text('합성 주문자')
  expect(page.locator('[data-outbound-customer="2"]')).to_have_text('미등록')
  page.screenshot(path=str(RESULTS/'calendar-dispatch-desktop.png'),full_page=True)
  page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(RESULTS/'calendar-dispatch-mobile.png'),full_page=True)
  assert page.locator('.month-calendar').evaluate('(e)=>e.scrollWidth<=e.clientWidth')
  page.set_viewport_size({'width':1280,'height':950})
  page.locator('[data-dispatch=month][data-delta="1"]').click();expect(page.locator('.dispatch-month-totals')).to_contain_text('월 실제 출고 0대')
  page.locator('.nav-section>summary',has_text='구매·가액').click();page.locator('.sidebar [data-page=purchases]').click();expect(page.locator('.month-calendar')).to_be_visible()
  page.locator('[data-purchase=day]').first.click();expect(page.locator('.month-calendar-day.is-selected')).to_have_count(1)
  page.locator('.nav-section>summary',has_text='마감·보고').click();requests.clear();page.locator('.sidebar [data-page=parts]').click();expect(page.locator('.month-calendar')).to_be_visible()
  page.locator('[data-part=day]').first.click();expect(page.locator('.month-calendar-day.is-selected')).to_have_count(1)
  assert not any('/api/purchases' in url or '/api/vehicle-inventory' in url for url in requests)
  assert '차량가격(VAT' not in page.locator('#content').inner_text()
  page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(RESULTS/'calendar-parts-mobile.png'),full_page=True)
  assert page.locator('.month-calendar').evaluate('(e)=>e.getBoundingClientRect().right')<=390
  leap=page.evaluate("""async()=>{const {monthCalendar}=await import('/month-calendar.js');const el=document.createElement('div');el.innerHTML=monthCalendar({month:'2024-02',cell:(d,n)=>'<button>'+n+'</button>'});return el.querySelectorAll('.month-calendar-day').length;}""")
  assert leap==29
  result=page.evaluate("""async(token)=>{
   const api=async(path,options={})=>{const r=await fetch('/api'+path,{...options,headers:{'Content-Type':'application/json',Authorization:'Bearer '+token}});const data=await r.json();if(!r.ok)throw Error(data.detail);return data;};
   const ids=[];for(let i=0;i<2;i++)ids.push((await api('/customers',{method:'POST',body:JSON.stringify({name:'합성 중복업체',kind:'COMPANY',request_id:crypto.randomUUID()})})).id);
   const {mountCustomerEditor}=await import('/customers.js');const root=document.createElement('div');document.body.append(root);mountCustomerEditor(root,{api,esc:x=>String(x)});
   const input=root.querySelector('[data-name]');input.value='합성 중복업체';input.dispatchEvent(new Event('input'));await new Promise(r=>setTimeout(r,500));
   const groups=root.querySelectorAll('details').length;let rejected=false;try{await root.saveCustomer();}catch(e){rejected=e.message.includes('기존 고객');}
   root.querySelector('[data-choice]').click();const id=await root.saveCustomer();const cleared=!root.querySelector('[data-results]').textContent;root.remove();return {groups,rejected,selected:ids.includes(id),cleared};
  }""",token)
  assert result=={'groups':1,'rejected':True,'selected':True,'cleared':True},result
  typography=page.evaluate("""async()=>{
   const {monthCalendar}=await import('/month-calendar.js');const {koreanHoliday}=await import('/korean-holidays.js');
   const root=document.createElement('div');document.body.append(root);
   root.innerHTML=['출고 일정·이력 달력','구매입고 달력','부품 재고마감 달력','차량 재고 달력'].map(label=>monthCalendar({month:'2026-10',label,cell:(d,n)=>'<button><strong>'+n+'</strong><small>출고 14대</small><b>3대</b></button>'})).join('');
   const sizes=[...root.querySelectorAll('.month-calendar')].map(c=>['.month-calendar-week span','.month-calendar-day strong','.month-calendar-day small:not(.calendar-holiday)','.month-calendar-day b'].map(q=>getComputedStyle(c.querySelector(q)).fontSize).join(','));
   const red=getComputedStyle(root.querySelector('[data-calendar-day="2026-10-04"] strong')).color;
   const blue=getComputedStyle(root.querySelector('[data-calendar-day="2026-10-10"] strong')).color;
   const holiday=root.querySelector('[data-calendar-day="2026-10-03"]').classList.contains('is-holiday');
   root.remove();return {sizes,red,blue,holiday,substitute:koreanHoliday('2026-10-05').name,oldConstitution:koreanHoliday('2025-07-17').holiday,newConstitution:koreanHoliday('2026-07-17').holiday};
  }""")
  assert len(set(typography['sizes']))==1,typography
  assert typography['red']=='rgb(188, 48, 59)' and typography['blue']=='rgb(37, 99, 166)',typography
  assert typography['holiday'] and typography['substitute']=='대체공휴일'
  assert not typography['oldConstitution'] and typography['newConstitution']
  assert not errors,errors
  browser.close()
 print('PASS common purchase/parts/dispatch calendar UI, selection/month navigation, VOID excluded, RETURN retained, 390px layout, leap month, parts requests contain no purchase/value queries. Native device unverified.')
finally:stop(r)
