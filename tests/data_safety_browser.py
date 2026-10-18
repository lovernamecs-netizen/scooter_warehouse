"""Actual server + browser: account-scoped pending replay after closing the tab."""
import json,httpx
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,CHROME,PASSWORD,RESULTS,observe
runtime=start();base=runtime[3]
try:
 with httpx.Client(base_url=base,trust_env=False) as client:
  token=client.post('/api/login',json={'username':'admin','password':PASSWORD}).json()['token'];client.headers['Authorization']='Bearer '+token
  def state():return client.get('/api/state').json()
  initial=state();model=next(m['id'] for m in initial['masters'] if m['kind']=='model');color=next(m['id'] for m in initial['masters'] if m['kind']=='color')
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path=CHROME,headless=True);context=browser.new_context();page=context.new_page();observed=observe(page,'data-safety')
   def login(page):
    page.goto(base);page.locator('[name=username]').fill('admin');page.locator('[name=password]').fill(PASSWORD);page.locator('#login button').click();expect(page.locator('.topbar')).to_be_visible()
   login(page);expect(page.locator('.notice[role=status]')).to_contain_text('자동 백업이 꺼져')
   page.locator('[data-act=photo-storage]').first.click();expect(page.locator('#storage-form')).to_be_visible();expect(page.locator('#modal')).to_contain_text('백업 날짜 보존 수');page.screenshot(path=str(RESULTS/'backup-safety.png'));page.evaluate('document.querySelector("#modal").close()')
   page.locator('[data-act=receipt]').first.click();page.locator('#model_id').select_option(model);page.locator('#color_id').select_option(color);page.locator('[name=notes]').fill('탭 종료 복구 테스트')
   def lost(route):route.fetch();route.abort('failed')
   page.route('**/api/command',lost);page.locator('[data-act=save-receipt]').click();expect(page.locator('.system-error')).to_be_visible()
   assert len(state()['vehicles'])==len(initial['vehicles'])+1
   page.close();page=context.new_page();observe(page,'data-safety-reopened');login(page)
   # A different account namespace must not expose this pending request.
   assert page.evaluate("async()=>{const {pendingRequest}=await import('/pending-request.js');return pendingRequest('different-user').read()}") is None
   page.locator('[data-page=settings]').first.click();page.locator('[data-act=retry]').click()
   expect(page.locator('#toast')).to_contain_text('요청 결과를 확인했습니다.')
   assert page.evaluate("!Object.keys(localStorage).some(k=>k.startsWith('warehousePending.v2:'))")
   assert len(state()['vehicles'])==len(initial['vehicles'])+1
   page.locator('[data-page=dashboard]').first.click();page.locator('[data-act=receipt]').first.click();page.locator('#model_id').select_option(model);page.locator('#color_id').select_option(color)
   page.evaluate("() => {window.originalStorageSet=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(k.startsWith('warehousePending.v2:'))throw new DOMException('quota','QuotaExceededError');return window.originalStorageSet.call(this,k,v)};}")
   page.locator('[data-act=save-receipt]').click();expect(page.locator('.system-error')).to_contain_text('저장 요청을 보내지 않았습니다.');assert len(state()['vehicles'])==len(initial['vehicles'])+1
   page.evaluate('() => {Storage.prototype.setItem=window.originalStorageSet;}')
   assert not observed['pageerror'];browser.close()
 (RESULTS/'data-safety-browser.json').write_text(json.dumps({'passed':['backup warning and settings UI','saved response lost','tab closure and relogin','account namespace isolation','same request replay without duplicate','browser storage quota blocks write before server submission']},ensure_ascii=False,indent=2),encoding='utf-8')
 print('data safety browser passed')
finally:stop(runtime)
