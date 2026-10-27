import json,uuid,httpx
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,CHROME,PASSWORD,RESULTS,observe
from server.purchase_sheet import HEADERS
runtime=start(demo=True)
try:
 client=httpx.Client(base_url=runtime[3],trust_env=False)
 token=client.post('/api/login',json={'username':'admin','password':PASSWORD}).json()['token'];client.headers['Authorization']='Bearer '+token
 state=client.get('/api/state').json();model=next(m for m in state['masters'] if m['kind']=='model');color=next(m for m in state['masters'] if m['kind']=='color');today=state['today']
 source=['','합성 공급업체','테스트 대표',today,'테스트 보관지역',model['name'],'MLHJK05A1P5000020',color['name'],'테스트 계약자','재고','7,790,000','7,081,818']
 pasted='\t'.join(HEADERS)+'\n'+'\t'.join(source)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});errors=observe(page,'purchase')
  page.goto(runtime[3]);page.evaluate('(t)=>sessionStorage.setItem("warehouseToken",t)',token);page.reload()
  page.locator('[data-act=nav][data-page=purchases]').first.click();expect(page.locator('h1')).to_have_text('구매·입고 자료')
  page.locator('[data-purchase=paste]').click();page.locator('#purchase-paste textarea').fill(pasted);page.locator('[data-purchase=review-paste]').click()
  expect(page.locator('#purchase-review')).to_contain_text('시트 기준 재고 반영');page.locator('[name=create]').check();page.locator('[name=year]').fill('2026');page.locator('[name=confirmed]').check()
  def lose_response(route):
   response=route.fetch();assert response.status==200;route.fulfill(status=503,content_type='application/json',body=json.dumps({'message':'synthetic lost response'}))
  page.route('**/api/purchases/apply',lose_response,times=1)
  page.locator('[data-purchase=save]').click();expect(page.locator('#toast')).to_contain_text('같은 요청');page.locator('[data-purchase=save]').click()
  expect(page.locator('.purchase-record')).to_have_count(1);expect(page.locator('.purchase-record')).to_contain_text('7,790,000원')
  page.locator('.purchase-record>summary').click();expect(page.locator('.purchase-fields').first).to_contain_text('7,081,818')
  page.locator('[data-purchase=vehicle]').click();page.locator('summary',has_text='차량 정보·수정·위치이동').click();page.locator('[data-act=vehicle-edit]').click()
  page.locator('[name=serial_number]').fill('000-SERIAL-01');page.locator('[name=ubis_number]').fill('000-UBIS-02');page.locator('[data-act=save-vehicle]').click()
  page.locator('summary',has_text='차량 정보·수정·위치이동').click();expect(page.locator('#modal')).to_contain_text('000-SERIAL-01');expect(page.locator('#modal')).to_contain_text('000-UBIS-02')
  page.locator('#modal .modal-head [data-act=close]').click()
  page.locator('[data-purchase=paste]').click();page.locator('#purchase-paste textarea').fill(pasted);page.locator('[data-purchase=review-paste]').click();expect(page.locator('#purchase-review')).to_contain_text('시트 기준 · 기존 차량 참고 연결');page.locator('[name=confirmed]').check();page.locator('[data-purchase=save]').click();expect(page.locator('.purchase-record')).to_have_count(1);expect(page.locator('#toast')).to_contain_text('변경 없음 1건')
  page.locator('[data-purchase=manual]').click();page.locator('#purchase-form [name=supplier]').fill('합성 미입고');page.locator('#purchase-form [name=model]').fill('PCX125');page.locator('#purchase-form [name=vin]').fill('입고예정');page.locator('#purchase-form [name=region]').fill('미입고');page.locator('[data-purchase=review-manual]').click();expect(page.locator('#purchase-review')).to_contain_text('미입고 자료');page.locator('[name=confirmed]').check();page.locator('[data-purchase=save]').click();expect(page.locator('.purchase-record')).to_have_count(2)
  page.locator('[data-purchase=pending]').click();expect(page.locator('.purchase-record')).to_have_count(1);page.locator('[data-purchase=all]').click();page.screenshot(path=str(RESULTS/'purchase-desktop.png'),full_page=True)
  page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');page.screenshot(path=str(RESULTS/'purchase-mobile.png'),full_page=True)
  page.set_viewport_size({'width':1440,'height':1000})
  page.locator('[data-purchase=manual]').click();page.locator('#purchase-form [name=model]').fill('시트 원문 미등록 차종');page.locator('#purchase-form [name=vin]').fill('MLHJK05A1P5000099');page.locator('#purchase-form [name=received_date]').fill('2025-01-02');page.locator('#purchase-form [name=vat_included]').fill('1234000');page.locator('#purchase-form [name=vat_excluded]').fill('1121818');page.locator('#purchase-form [name=serial_number]').fill('000-SHEET-S');page.locator('#purchase-form [name=ubis_number]').fill('000-SHEET-U');page.locator('#purchase-form [name=ubis_installation]').fill('유비스')
  page.locator('[data-purchase=review-manual]').click();expect(page.locator('#purchase-review')).to_contain_text('시트 기준 재고 반영');page.locator('[name=confirmed]').check();page.locator('[data-purchase=save]').click();expect(page.locator('.purchase-record')).to_have_count(3)
  record=page.locator('.purchase-record').filter(has_text='MLHJK05A1P5000099');record.locator(':scope > summary').click();expect(record).to_contain_text('000-SHEET-S');expect(record).to_contain_text('000-SHEET-U')
  record.locator('[data-purchase=edit]').click();expect(page.locator('#purchase-form [name=serial_number]')).to_have_value('000-SHEET-S');page.locator('#purchase-form [name=ubis_number]').fill('000-SHEET-U2');page.locator('[data-purchase=review-manual]').click();page.locator('[name=reason]').fill('번호 정정');page.locator('[name=confirmed]').check();page.locator('[data-purchase=save]').click();expect(page.locator('#toast')).to_contain_text('저장 1건');record=page.locator('.purchase-record').filter(has_text='MLHJK05A1P5000099');record.locator(':scope > summary').click();expect(record).to_contain_text('000-SHEET-U2')
  page.locator('[data-purchase=choose-filter][data-key=serial_number]').click();page.locator('[data-filter=serial_number]').fill('000-SHEET');page.locator('[data-filter=serial_number]').press('Enter');expect(page.locator('.purchase-record')).to_have_count(1)
  page.locator('[data-purchase=choose-filter][data-key=ubis_number]').click();page.locator('[data-filter=ubis_number]').fill('NO-MATCH');page.locator('#purchase-filter-form button[type=submit]').click();expect(page.locator('.purchase-record')).to_have_count(0);expect(page.locator('.purchase-match')).to_have_count(0)
  page.locator('[data-purchase=remove-filter][data-key=ubis_number]').click();expect(page.locator('[data-filter=ubis_number]')).to_have_value('NO-MATCH');expect(page.locator('.purchase-record')).to_have_count(1);page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');boxes=page.locator('.purchase-filter-editor').evaluate('(el)=>[...el.querySelectorAll("input,select,button")].map(x=>{const r=x.getBoundingClientRect();return {top:r.top,bottom:r.bottom,height:r.height}})');assert abs(boxes[1]['bottom']-boxes[2]['bottom'])<1 and all(abs(b['height']-44)<1 for b in boxes);page.screenshot(path=str(RESULTS/'filter-buttons-mobile.png'),full_page=True);page.set_viewport_size({'width':1440,'height':1000});boxes=page.locator('.purchase-filter-editor').evaluate('(el)=>[...el.querySelectorAll("input,select,button")].map(x=>x.getBoundingClientRect().bottom)');assert max(boxes)-min(boxes)<1;page.screenshot(path=str(RESULTS/'filter-alignment-desktop.png'),full_page=True);page.locator('[data-purchase=clear-filter]').click();expect(page.locator('[data-filter=ubis_number]')).to_have_value('NO-MATCH');expect(page.locator('.purchase-record')).to_have_count(3);page.locator('[data-purchase=choose-filter][data-key=serial_number]').click();expect(page.locator('[data-filter=serial_number]')).to_have_value('000-SHEET')
  page.locator('[data-purchase=choose-filter][data-key=ubis_installation]').click();page.locator('[data-filter-mode=ubis_installation]').select_option('empty');page.locator('#purchase-filter-form button[type=submit]').click();expect(page.locator('.purchase-record')).to_have_count(2);expect(page.locator(f'[data-day="{today}"]')).to_contain_text('1건');page.locator(f'[data-day="{today}"]').click();expect(page.locator('.purchase-record')).to_have_count(1)
  page.locator('[data-purchase=clear-filter]').click()
  page.locator('[data-act=nav][data-page=closing]').first.click();expect(page.locator('.vi-panel h3')).to_contain_text(today);page.locator('#report-day').fill('2025-01-03');page.locator('#report-day').dispatch_event('change')
  expect(page.locator('.vi-panel h3')).to_contain_text('2025-01-03');expect(page.locator('.vi-panel')).to_contain_text('시트 기준 재고');expect(page.locator('.vi-panel')).to_contain_text('1,234,000원');expect(page.locator('.vi-panel')).to_contain_text('시트 원문 미등록 차종')
  page.screenshot(path=str(RESULTS/'sheet-authority-calendar.png'),full_page=True)
  assert not errors['pageerror'] and not errors['requestfailed'],errors
  assert all('503' in x for x in errors['console_error']),errors
  browser.close()
 assert len(client.get('/api/state').json()['vehicles'])==1
 (RESULTS/'purchase-browser.json').write_text(json.dumps({'passed':True,'checks':['committed response-loss retry','paste','12 columns','explicit receipt','VAT prices','identifiers edit','duplicate paste','manual pending','date calendar','mobile viewport','historical unmapped sheet counted without operational vehicle','source valuation calendar'],'errors':errors},indent=2),encoding='utf-8')
 print('PASS actual isolated server and purchase browser workflow')
finally:stop(runtime)

