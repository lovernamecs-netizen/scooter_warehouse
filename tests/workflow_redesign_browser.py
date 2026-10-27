import uuid,httpx
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,CHROME,PASSWORD
from test_purchase_xlsx import fixture
from server.purchase_xlsx import parse
r=start()
try:
 with httpx.Client(base_url=r[3],timeout=90) as c:
  token=c.post('/api/login',json={'username':'admin','password':PASSWORD}).json()['token'];body=parse(fixture(4),'workflow.xlsx');body['request_id']=str(uuid.uuid4())
  response=c.post('/api/purchases/import',headers={'Authorization':'Bearer '+token},json=body);assert response.status_code==200,response.text
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(r[3]);page.locator('[name=username]').fill('admin');page.locator('[name=password]').fill(PASSWORD);page.locator('#login button').click()
  page.locator('.nav-section > summary',has_text='구매·가액').click();page.locator('[data-page=purchases]').click()
  page.locator('[data-purchase-month]').fill('2026-01');page.locator('[data-purchase-month]').dispatch_event('change');expect(page.locator('.purchase-record')).to_have_count(4)
  expect(page.locator('[data-purchase=all]')).to_have_count(0);expect(page.locator('[data-purchase=source-review]')).to_have_count(0)
  page.locator('[data-purchase=import-menu]').click();expect(page.locator('#modal [data-purchase]')).to_have_count(3);page.locator('#modal [data-act=close]').click()
  page.locator('[data-purchase=month-review]').click();expect(page.locator('#modal')).to_contain_text('일치 4건');page.locator('#month-reason').fill('월 검토');page.locator('#month-ack').check();page.locator('[data-purchase=month-confirm]').click();expect(page.locator('#modal')).to_contain_text('월 확정됨')
  page.locator('[data-purchase=month-history]').click();page.locator('[data-purchase=month-snapshot]').click();expect(page.locator('#modal')).to_contain_text('확정 당시 자료');page.locator('#modal [data-act=close]').click()
  import io,zipfile
  output=io.BytesIO()
  with zipfile.ZipFile(io.BytesIO(fixture(4))) as source,zipfile.ZipFile(output,'w') as dest:
   for info in source.infolist():
    raw=source.read(info.filename)
    if info.filename=='xl/worksheets/sheet1.xml':raw=raw.replace(b'<c r="O2" t="inlineStr"><is><t></t></is></c>',b'<c r="O2" t="inlineStr"><is><t>source changed</t></is></c>')
    dest.writestr(info,raw)
  file=Path(r[1].name)/'changed.xlsx';file.write_bytes(output.getvalue())
  page.locator('[data-purchase=month-review]').click();page.locator('[data-purchase=scan-source]').click();page.locator('[data-purchase=xlsx]').click();page.locator('[name=source_namespace]').select_option(label='workflow.xlsx · 재고');page.locator('input[type=file]').set_input_files(file);page.locator('[data-purchase=xlsx-read]').click();expect(page.locator('#modal')).to_contain_text('항목 차이 1건',timeout=15000);expect(page.locator('#modal')).to_contain_text('재검토 필요');page.locator('#modal [data-act=close]').click()
  page.locator('.nav-section > summary',has_text='마감·보고').click();page.locator('[data-page=closing]').click();expect(page.locator('#content')).to_contain_text('일일 업무 보고');expect(page.locator('#content')).to_contain_text('미판매 (배정 전)');expect(page.locator('#content')).to_contain_text('고객 인도 차량')
  page.set_viewport_size({'width':390,'height':844});expect(page.locator('#report-day')).to_be_visible();assert not errors,errors
  page.screenshot(path=str(Path(r[1].name)/'workflow-mobile.png'),full_page=True);browser.close();print('PASS real browser: grouped navigation, import menu, month selection/reconcile/approval/history, business report, mobile viewport')
finally:stop(r)
