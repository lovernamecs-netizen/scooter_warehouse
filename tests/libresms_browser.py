"""Real isolated server/browser. LibreSMS network and sends are intercepted."""
import httpx
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,CHROME,PASSWORD,nav,observe
r=start()
try:
 token=httpx.post(r[3]+'/api/login',json={'username':'admin','password':PASSWORD},trust_env=False).json()['token']
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True)
  page=browser.new_page(viewport={'width':1440,'height':1000});errors=observe(page,'libresms')
  configs={d:{'device_id':d,'enabled':False,'url':'','sender':'','name':'업무폰 '+d[-1],'interval':5} for d in ['phone1','phone2']}
  def settings(route):
   if route.request.method=='PUT':
    value=route.request.post_data_json;configs[value['device_id']]=value;route.fulfill(json=value)
   else:route.fulfill(json=configs[route.request.url.split('device_id=')[-1]])
  page.route('**/api/insurance/libresms/settings*',settings)
  page.route('**/api/insurance/libresms/health*',lambda route:route.fulfill(json={'online':True,'message':'합성 연결 확인','mms_verified':False}))
  page.route('**/api/insurance/libresms/queue',lambda route:route.fulfill(json=[]))
  page.goto(r[3]);page.evaluate('(t)=>sessionStorage.setItem("warehouseToken",t)',token);page.reload();nav(page,'insurance')
  expect(page.locator('#insurance-provider')).to_have_value('coolsms')
  page.locator('#insurance-provider').select_option('libresms')
  page.locator('#libre-device').select_option('phone2')
  page.locator('details').filter(has=page.locator('#libre-name')).locator('summary').click()
  expect(page.locator('#libre-name')).to_have_value('업무폰 2')
  page.locator('#libre-url').fill('http://100.64.1.3:8686');page.locator('#libre-sender').fill('01022223333')
  page.locator('#libre-private').check();page.locator('#libre-enabled').check();page.locator('[data-mms=libre-save]').click()
  expect(page.locator('#libre-status')).to_contain_text('저장했습니다')
  assert configs['phone2']['enabled'] and not configs['phone1']['enabled']
  page.locator('[data-mms=libre-health]').click();expect(page.locator('#libre-status')).to_have_text('합성 연결 확인')
  page.locator('#libre-device').select_option('phone1');expect(page.locator('#libre-enabled')).not_to_be_checked()
  page.locator('#libre-device').select_option('phone2');expect(page.locator('#libre-sender')).to_have_value('01022223333')
  page.set_viewport_size({'width':390,'height':844})
  assert page.locator('#insurance-tool').evaluate('(e)=>e.getBoundingClientRect().right')<=390
  assert not errors['pageerror'],errors
  browser.close()
 print('PASS: two-device settings, selection, connection, CoolSMS default, mobile viewport; no real MMS')
finally:stop(r)
