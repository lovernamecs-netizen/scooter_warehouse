"""Synthetic local JPEG folder + real UI; MMS intercepted, no real sends."""
import io,zipfile,httpx
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,CHROME,PASSWORD,nav,observe
r=start();calls=[]
try:
 folder=Path(r[1].name)/'insurance-batch';folder.mkdir();(folder/'November').mkdir()
 for name in ['123가4567.jpg','234나5678.jpeg','November/보험ABC.jpg']:
  Image.new('RGB',(600,850),'white').save(folder/name,'JPEG')
 token=httpx.post(r[3]+'/api/login',json={'username':'admin','password':PASSWORD},trust_env=False).json()['token']
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});errors=observe(page,'insurance-search')
  page.on('dialog',lambda d:d.accept())
  page.route('**/api/insurance/mms/settings',lambda route:route.fulfill(json={'sender_phone':'01011112222','msg_template':'{차량번호} 합성 테스트','api_key_configured':True,'api_secret_configured':True}))
  def send(route):
   calls.append(route.request.post_data_json);route.fulfill(json={'state':'accepted'})
  page.route('**/api/insurance/mms/send',send)
  page.goto(r[3]);page.evaluate('(t)=>sessionStorage.setItem("warehouseToken",t)',token);page.reload();nav(page,'insurance')
  page.locator('input[webkitdirectory]').set_input_files(str(folder))
  expect(page.locator('#insurance-progress')).to_contain_text('JPG 3개')
  expect(page.locator('[data-insurance-plate]')).to_have_count(3)
  for plate in ['123가4567','234나5678']:
   row=page.locator('#insurance-rows tr').filter(has=page.locator('input[value="'+plate+'"]'))
   row.locator('[data-insurance=confirm]').click()
  page.locator('input[data-insurance=contacts]').set_input_files({'name':'test.csv','mimeType':'text/csv','buffer':'차량번호,연락처\n123가4567,01011112222\n234나5678,01033334444'.encode()})
  expect(page.locator('#insurance-summary')).to_contain_text('연락처 매칭 2건')
  def search(query,field='all'):
   page.locator('#insurance-search-field').select_option(field)
   page.locator('#insurance-search-query').fill(query);page.locator('#insurance-search-query').press('Enter')
  search('5678','plate');expect(page.locator('[data-insurance-plate]')).to_have_count(1)
  expect(page.locator('[data-insurance-plate]')).to_have_value('234나5678')
  page.locator('[data-insurance=preview]').click();expect(page.locator('.insurance-preview-head')).to_contain_text('234나5678.jpeg');page.locator('.insurance-preview button').click()
  with page.expect_download() as saved:page.locator('[data-insurance=zip]').click()
  with zipfile.ZipFile(saved.value.path()) as z:assert z.namelist()==['234나5678.jpg']
  page.locator('[data-insurance-select-all]').check();expect(page.locator('#insurance-search-status')).to_contain_text('선택 1건')
  page.locator('[data-mms=send-all]').click();expect(page.locator('#insurance-send-progress')).to_contain_text('접수 1건')
  assert len(calls)==1 and calls[0]['plate']=='234나5678'
  search('no-result');expect(page.locator('#insurance-rows')).to_contain_text('검색 결과가 없습니다.')
  expect(page.locator('[data-insurance-plate]')).to_have_count(0)
  page.locator('[data-insurance=search-reset]').click();expect(page.locator('[data-insurance-plate]')).to_have_count(3)
  expect(page.locator('#insurance-search-query')).to_have_value('no-result')
  search('12 3-가4567','plate');expect(page.locator('[data-insurance-plate]')).to_have_value('123가4567')
  search('보험abc','file');expect(page.locator('[data-insurance-plate]')).to_have_count(1)
  search('november','file');expect(page.locator('#insurance-rows')).to_contain_text('보험ABC.jpg')
  page.set_viewport_size({'width':390,'height':844})
  assert page.locator('#insurance-search').evaluate('(e)=>e.getBoundingClientRect().right')<=390
  assert not errors['pageerror'],errors
  browser.close()
 print('PASS JPEG folder import, filename/folder/plate normalization, preview, filtered ZIP, filtered send (mock), zero results, reset preserves input and full list, mobile layout')
finally:stop(r)
