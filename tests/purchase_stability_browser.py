from browser_support import nav
import uuid,time,httpx
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,CHROME,PASSWORD
from test_purchase_xlsx import fixture
from server.purchase_xlsx import parse
def save_ledger(page):
 with page.expect_response(lambda response:'/api/purchases/page?' in response.url and response.status==200):page.locator('[data-purchase=ledger-save]').click()
 expect(page.locator('#modal')).not_to_be_visible()
 expect(page.locator('#content')).to_have_attribute('aria-busy','false')
runtime=start()
try:
 with httpx.Client(base_url=runtime[3],timeout=120) as client:
  token=client.post('/api/login',json={'username':'admin','password':PASSWORD}).json()['token']
  payload=parse(fixture(123),'browser-synthetic.xlsx');payload['request_id']=str(uuid.uuid4())
  response=client.post('/api/purchases/import',headers={'Authorization':'Bearer '+token},json=payload);assert response.status_code==200,response.text
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)));page.on('response',lambda res:print('HTTP failure',res.status,res.url,flush=True) if res.status>=400 else None)
  page.goto(runtime[3]);page.locator('[name=username]').fill('admin');page.locator('[name=password]').fill(PASSWORD);page.locator('#login button').click()
  nav(page,'purchases');page.locator('[data-purchase-month]').fill('2026-01');page.locator('[data-purchase-month]').dispatch_event('change');expect(page.locator('.purchase-record')).to_have_count(50)
  page.locator('[data-purchase=list-page][data-delta="1"]').click();expect(page.locator('[aria-label="자료 페이지"]')).to_contain_text('2 / 3')
  page.locator('[data-purchase=choose-filter][data-key=vin]').click();page.locator('[data-filter=vin]').fill('000122');page.locator('#purchase-filter-form button').click();expect(page.locator('.purchase-record')).to_have_count(1)
  page.locator('.purchase-record > summary').click();expect(page.locator('.purchase-fields')).to_contain_text('054687311')
  page.locator('[data-purchase=record-history]').click();expect(page.locator('#modal')).to_contain_text('v1');page.locator('#modal [data-act=close]').click()
  page.locator('[data-purchase=month-review]').click();expect(page.locator('#modal')).to_contain_text('123');page.locator('#month-reason').fill('합성 브라우저 확인');page.locator('#month-ack').check();page.locator('[data-purchase=month-confirm]').click();expect(page.locator('#modal')).to_contain_text('월 확정됨');page.locator('#modal [data-act=close]').click()
  page.locator('[data-purchase=delete-record]').click();page.locator('#ledger-reason').fill('합성 삭제');save_ledger(page);expect(page.locator('.purchase-record')).to_have_count(0)
  page.locator('[data-purchase=ledger]').click();expect(page.locator('.purchase-record')).to_have_count(1);page.locator('.purchase-record > summary').click();page.locator('[data-purchase=record-history]').click();page.locator('#modal details').last.locator('summary').click();page.locator('[data-purchase=restore-record]').click();page.locator('#ledger-reason').fill('합성 복구');save_ledger(page)
  from pathlib import Path
  upload=Path(runtime[1].name)/'browser-synthetic.xlsx';upload.write_bytes(fixture(123))
  expect(page.locator('[data-page=registration-ocr]')).to_have_count(0);page.locator('[data-purchase=import-menu]').click();expect(page.locator('#modal [data-purchase]')).to_have_count(3);page.locator('[data-purchase=xlsx]').click();expect(page.locator('[name=source_namespace]')).to_be_visible(timeout=15000);page.locator('[name=source_namespace]').select_option(label='browser-synthetic.xlsx · 재고');page.locator('input[type=file]').set_input_files(upload);page.locator('[data-purchase=xlsx-read]').click();expect(page.locator('#modal')).not_to_be_visible(timeout=30000)
  page.locator('[data-purchase=month-review]').click();expect(page.locator('#modal')).to_contain_text('2026-01');page.locator('#modal [data-act=close]').click()
  page.set_viewport_size({'width':390,'height':844});expect(page.locator('.purchase-record')).to_have_count(50)
  assert not errors,errors;browser.close();print('PASS real-server browser: bounded pages, filtering, lazy history, confirmation, delete/restore, mobile viewport')
finally:stop(runtime)
