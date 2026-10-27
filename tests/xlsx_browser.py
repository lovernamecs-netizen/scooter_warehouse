from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,CHROME,PASSWORD
from test_purchase_xlsx import fixture
r=start();folder=Path('verification');folder.mkdir(exist_ok=True);f=folder/'synthetic.xlsx'
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page();errors=[];page.on('dialog',lambda dialog:dialog.accept());page.on('pageerror',lambda e:errors.append(str(e)));page.goto(r[3]);page.locator('[name=username]').fill('admin');page.locator('[name=password]').fill(PASSWORD);page.locator('#login button').click();page.locator('[data-page=purchases]').first.click()
  def read(data):
   f.write_bytes(data);page.locator('[data-purchase=xlsx]').click();page.locator('#xlsx-upload [name=file]').set_input_files(str(f.resolve()));page.locator('[data-purchase=xlsx-read]').click()
  read(fixture(251));expect(page.locator('#modal')).not_to_be_visible(timeout=60000);expect(page.locator('.purchase-record')).to_have_count(50);expect(page.locator('[role=status]').first).to_contain_text('가져오기 완료 · 저장 251건')
  read(fixture(251));expect(page.locator('#modal')).not_to_be_visible(timeout=60000);expect(page.locator('.purchase-record')).to_have_count(50);expect(page.locator('[role=status]').first).to_contain_text('변경 없음 251건')
  read(fixture(1,True));expect(page.locator('#modal')).not_to_be_visible(timeout=15000);expect(page.locator('[role=status]').first).to_contain_text('가져오기 완료');expect(page.locator('[role=status]').first).to_contain_text('보류 0건')
  read(b'invalid');expect(page.locator('#modal .modal-error')).to_contain_text('파일');expect(page.locator('#modal')).to_be_visible();page.locator('#modal [data-act=close]').click()
  before_count=page.locator('.purchase-record').count()
  page.locator('.purchase-record summary').first.click();page.locator('[data-purchase=edit]').first.click();page.locator('#purchase-form [name=memo1]').fill('브라우저 수정');page.locator('#purchase-form [name=reason]').fill('이력 테스트');page.locator('[data-purchase=save-edit]').click();expect(page.locator('#modal')).not_to_be_visible()
  page.locator('.purchase-record summary').first.click();page.locator('[data-purchase=delete-record]').first.click();page.locator('#ledger-reason').fill('삭제 테스트');page.locator('[data-purchase=ledger-save]').click();expect(page.locator('.purchase-record')).to_have_count(before_count)
  page.locator('[data-purchase=ledger]').click();page.locator('#modal > .modal-body > details').first.locator('summary').first.click();page.locator('#modal [data-purchase=restore-record]').first.locator('..').locator('summary').click();page.locator('#modal [data-purchase=restore-record]').first.click();page.locator('#ledger-reason').fill('복구 테스트');page.locator('[data-purchase=ledger-save]').click();expect(page.locator('.purchase-record')).to_have_count(before_count)
  page.locator('[data-purchase=google]').click();page.locator('[data-purchase=google-login]').click();expect(page.locator('#modal .modal-error')).to_contain_text('OAuth');page.locator('#modal [data-act=close]').click()
  import time,json
  from server.purchase_xlsx import parse
  def slow_google(route):
   time.sleep(21);route.fulfill(status=200,content_type='application/json',body=json.dumps(parse(fixture(1),'slow.xlsx')))
  page.route('**/api/purchases/google',slow_google)
  page.locator('[data-purchase=google]').click();page.locator('#google-import [name=url]').fill('https://docs.google.com/spreadsheets/d/abcdefghijk/edit');page.locator('[data-purchase=google-read]').click();expect(page.locator('#modal')).not_to_be_visible(timeout=60000);expect(page.locator('[role=status]').first).to_contain_text('가져오기 완료');assert not errors;browser.close()
 print('PASS one-click import 251 rows, dialog close, unchanged reimport, held rows, visible invalid-file error')
finally:stop(r)
