import time,json
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,CHROME,PASSWORD
from server.purchase_sheet import ALL_FIELDS,ALL_HEADERS
r=start()
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  rows=[];history=[]
  for i in range(5000):
   source={k:'' for k in ALL_FIELDS};source.update(model='합성차종',vin=f'TEST{i:013d}',received_date='2026-10-19',vat_included='1000',serial_number='00123')
   data={'source':source,'values':{**source,'vat_included':1000},'pending':False,'status':'원본 자료 저장'}
   rows.append({'id':str(i),'revision':2,'data':data,'vehicle_id':None,'identifiers':{}})
   for version in (1,2):history.append({'id':str(i),'revision':version,'data':data,'actor':'tester','at':'2026-10-25'})
  payload={'rows':rows,'history':history,'masters':[],'fields':ALL_FIELDS,'headers':ALL_HEADERS}
  page.route('**/api/purchases',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(payload)))
  page.goto(r[3]);page.locator('[name=username]').fill('admin');page.locator('[name=password]').fill(PASSWORD);page.locator('#login button').click()
  start=time.monotonic();page.locator('[data-page=purchases]').first.click();expect(page.locator('.purchase-record')).to_have_count(50);print('5000 rows initial seconds:',round(time.monotonic()-start,3))
  expect(page.locator('.purchase-fields')).to_have_count(0)
  start=time.monotonic()
  for _ in range(12):page.locator('[data-purchase=month][data-delta="-1"]').click()
  print('12 month clicks seconds:',round(time.monotonic()-start,3));expect(page.locator('.purchase-record')).to_have_count(50)
  page.locator('[data-purchase=list-page][data-delta="1"]').click();expect(page.locator('.purchase-record').first).to_have_attribute('data-record-id','50')
  page.locator('.purchase-record > summary').first.click();expect(page.locator('.purchase-fields').first).to_contain_text('00123');expect(page.locator('[data-purchase=edit]')).to_have_count(1)
  page.locator('[data-purchase=choose-filter][data-key=vin]').click();page.locator('[data-filter=vin]').fill('TEST0000000004999');page.locator('#purchase-filter-form button').click();expect(page.locator('.purchase-record')).to_have_count(1);expect(page.locator('.purchase-record').first).to_have_attribute('data-record-id','4999')
  assert not errors,errors;browser.close();print('PASS pagination, lazy details/history, calendar navigation, full-dataset search')
finally:stop(r)
