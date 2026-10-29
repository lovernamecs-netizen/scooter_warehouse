import uuid,httpx
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,CHROME,PASSWORD
r=start()
try:
 c=httpx.Client(base_url=r[3],timeout=30,trust_env=False)
 token=c.post('/api/login',json={'username':'admin','password':PASSWORD}).json()['token'];headers={'Authorization':'Bearer '+token}
 def cmd(action,payload):
  response=c.post('/api/command',headers=headers,json={'command_id':str(uuid.uuid4()),'action':action,'payload':payload});assert response.status_code==200,response.text;return response.json()
 state=c.get('/api/state',headers=headers).json();model=next(m for m in state['masters'] if m['kind']=='model');color=next(m for m in state['masters'] if m['kind']=='color')
 vehicle=cmd('receive',{'vin':'MLHJK05A1P5000991','model_id':model['id'],'color_id':color['id'],'year':2026,'manufactured_month':'2026-01','kind':'NEW'})['vehicle_id']
 state=c.get('/api/state',headers=headers).json();v=next(v for v in state['vehicles'] if v['id']==vehicle);zone=next(z for z in state['layout']['zones'] if z['active'] and z['kind']=='STORAGE' and (not z['model_ids'] or model['id'] in z['model_ids']));slot=next(s for s in zone['slots'] if s['enabled'] and not s['stay_id'])
 cmd('move',{'vehicle_id':vehicle,'version':v['version'],'slot_id':slot['id']})
 customer=c.post('/api/customers',headers=headers,json={'name':'합성 단골업체','kind':'COMPANY','request_id':str(uuid.uuid4())}).json()['id']
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page(viewport={'width':1200,'height':900},has_touch=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(r[3]);page.evaluate('(token)=>sessionStorage.setItem("warehouseToken",token)',token);page.reload()
  page.locator('.nav-section>summary',has_text='차량 관리').click();page.locator('[data-page=map]').first.click()
  page.locator('#warehouse-select').select_option(zone['warehouse_id'])
  page.locator('[data-act=edit-map]').click();card=page.locator('.slot[data-vehicle="'+vehicle+'"]');card.scroll_into_view_if_needed()
  # Touch-like pointer events exercise the application 2-second hold timer.
  card.dispatch_event('pointerdown',{'pointerId':501,'pointerType':'touch','button':0,'clientX':150,'clientY':200})
  expect(page.get_by_role('menuitem',name='차량 이동…')).to_be_visible(timeout=5000)
  card.dispatch_event('pointerup',{'pointerId':501,'pointerType':'touch','button':0})
  page.wait_for_timeout(500);page.get_by_role('menuitem',name='차량 이동…').click()
  expect(page.locator('[data-act=cancel-move]')).to_be_visible();expect(page.locator('[data-act=edit-map]')).to_have_text('지도 편집')
  page.locator('[data-act=cancel-move]').click();page.locator('.slot[data-vehicle="'+vehicle+'"]').click()
  page.locator('[data-act=assign][data-channel=B2C]').click()
  page.locator('#customer-editor [data-name]').fill('합성 단')
  page.locator('#customer-editor [data-choice]').filter(has_text='합성 단골업체').click()
  selected=page.evaluate("document.querySelector('#customer-editor').readCustomer()")
  assert selected['id']==customer
  assert page.evaluate("document.querySelector('#customer-editor').saveCustomer()") == customer
  assert page.evaluate("!JSON.stringify(localStorage).includes('합성 단골업체') && !JSON.stringify(sessionStorage).includes('합성 단골업체')")
  page.locator('#modal').evaluate('(e)=>e.close()')
  state=c.get('/api/state',headers=headers).json();v=next(v for v in state['vehicles'] if v['id']==vehicle)
  cmd('assign',{'vehicle_id':vehicle,'version':v['version'],'scheduled':state['today'],'customer_id':customer})
  page.reload();page.locator('.nav-section>summary',has_text='주문·출고').click();page.locator('.sidebar [data-page=work]').click()
  expect(page.locator('.work-customer-cell .order-customer-name')).to_have_text('합성 단골업체')
  expect(page.locator('.work-customer-card .order-customer-name').last).to_have_text('합성 단골업체')
  row=page.locator('.vehicle-cards [data-id="'+vehicle+'"]');row.click()
  expect(page.locator('.modal-body>section.customer-order-banner:first-child .order-customer-name')).to_have_text('합성 단골업체')
  order=page.evaluate("""async()=>{const {sortWorkOrders}=await import('/work-orders.js');return sortWorkOrders([{id:'far',assignment:{scheduled:'2026-10-01'}},{id:'tomorrow',assignment:{scheduled:'2026-10-30'}},{id:'today',assignment:{scheduled:'2026-10-29'}},{id:'yesterday',assignment:{scheduled:'2026-10-28'}},{id:'unknown',assignment:{}}],'2026-10-29').map(v=>v.id)}""")
  assert order==['today','yesterday','tomorrow','far','unknown']
  assert page.evaluate("!JSON.stringify(localStorage).includes('합성 단골업체') && !JSON.stringify(sessionStorage).includes('합성 단골업체')")
  for channel,label in [('B2B','B2B'),('B2C','B2C'),(None,'구분 미등록')]:
   def channel_response(route):
    response=route.fetch();body=response.json()
    for row in body['vehicles']:
     if row['id']==vehicle:row['assignment']['parts_order']={'channel':channel} if channel else None
    route.fulfill(response=response,json=body)
   page.route('**/api/state',channel_response);page.reload()
   expect(page.locator('.dispatch-priority [data-id="'+vehicle+'"] .order-channel-badge')).to_have_text(label)
   page.locator('.nav-section>summary',has_text='주문·출고').click();page.locator('.sidebar [data-page=work]').click()
   expect(page.locator('.vehicle-cards [data-id="'+vehicle+'"] .order-channel-badge')).to_have_text(label)
   expect(page.locator('tr[data-id="'+vehicle+'"] .order-channel-badge')).to_have_text(label)
   expect(page.locator('.today-work-card[data-id="'+vehicle+'"] .order-channel-badge')).to_have_text(label)
   page.unroute('**/api/state',channel_response)
  assert not errors,errors
  browser.close()
 print('PASS actual browser: edit-mode 2s hold/move menu, exit edit mode, customer autocomplete/select, no name in browser persistent storage. Physical Android unverified.')
finally:stop(r)
