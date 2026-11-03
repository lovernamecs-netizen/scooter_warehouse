"""Real document endpoints and UI; paid-send route intercepted before network."""
import base64,io,zipfile,httpx,fitz
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,CHROME,PASSWORD,RESULTS,nav,observe
r=start();calls=[]
try:
 with fitz.open() as pdf:
  p=pdf.new_page(width=600,height=850);p.insert_text((20,210),'차량번호: 123가4567',fontname='korea');p.insert_text((20,100),'합성 보험 안내문',fontname='korea');pdfdata=pdf.tobytes()
 token=httpx.post(r[3]+'/api/login',json={'username':'admin','password':PASSWORD},trust_env=False).json()['token']
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});errors=observe(page,'insurance')
  page.on('dialog',lambda d:d.accept())
  page.route('**/api/insurance/mms/settings',lambda route:route.fulfill(json={'sender_phone':'01011112222','msg_template':'{차량번호} 합성 고지문','api_key_configured':True,'api_secret_configured':True}))
  def send(route):
   data=route.request.post_data_json;assert len(base64.b64decode(data['jpeg_base64']))<=199000;calls.append(data);route.fulfill(json={'state':'accepted','group_id':'mock-only'})
  page.route('**/api/insurance/mms/send',send)
  page.goto(r[3]);page.evaluate('(t)=>sessionStorage.setItem("warehouseToken",t)',token);page.reload();nav(page,'insurance')
  def load():
   page.locator('input[data-insurance=pdf]').set_input_files({'name':'synthetic.pdf','mimeType':'application/pdf','buffer':pdfdata})
   expect(page.locator('[data-insurance=confirm]')).to_have_count(1,timeout=30000);page.locator('[data-insurance=confirm]').click()
   page.locator('input[data-insurance=contacts]').set_input_files({'name':'synthetic.csv','mimeType':'text/csv','buffer':'차량번호,연락처\n123가4567,01012345678'.encode()})
   expect(page.locator('[data-insurance-phone]')).to_have_value('01012345678')
  load()
  page.screenshot(path=str(RESULTS/'insurance-desktop.png'),full_page=True)
  with page.expect_download() as saved:page.locator('[data-insurance=zip]').click()
  path=saved.value.path()
  with zipfile.ZipFile(path) as archive:assert archive.namelist()==['123가4567.jpg'] and len(archive.read('123가4567.jpg'))<=199000
  # Clearing must preserve the sender's array reference, then newly imported data sends.
  page.locator('[data-insurance=clear]').click();load()
  page.locator('[data-insurance-phone]').fill('');page.locator('[data-insurance-phone]').press('Tab')
  expect(page.locator('[data-insurance=send]')).to_be_disabled()
  page.locator('[data-insurance-phone]').fill('01012345678');page.locator('[data-insurance-phone]').press('Tab')
  page.locator('[data-insurance-select]').check();page.locator('[data-mms=send-selected]').click()
  expect(page.locator('#insurance-send-progress')).to_contain_text('접수 1건');assert len(calls)==1
  expect(page.locator('[data-insurance=send]')).to_be_disabled()
  page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(RESULTS/'insurance-mobile.png'),full_page=True)
  assert page.locator('#insurance-tool').evaluate('(e)=>e.getBoundingClientRect().right')<=390
  assert not errors['pageerror'],errors;browser.close()
 print('PASS actual PDF conversion/contacts, ZIP <=199000 bytes, clear/reimport, blank phone, selected mock send, desktop/mobile viewport; no paid send')
finally:stop(r)
