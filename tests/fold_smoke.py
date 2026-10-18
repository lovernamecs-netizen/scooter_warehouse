"""Viewport simulation only; not a physical Galaxy/Fold test."""
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,PASSWORD,CHROME,RESULTS
runtime=start()
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page(viewport={'width':390,'height':844},has_touch=True,is_mobile=True)
  page.goto(runtime[3]);page.locator('[name=username]').fill('admin');page.locator('[name=password]').fill(PASSWORD);page.locator('#login button').click();expect(page.locator('.username')).to_have_text('admin')
  page.locator('[data-act=receipt]').first.click();page.locator('[name=notes]').fill('화면 크기 변경 합성 초안')
  for w,h in [(360,400),(412,915),(768,960),(884,1104),(1024,768)]:
   page.set_viewport_size({'width':w,'height':h});assert page.locator('[name=notes]').input_value()=='화면 크기 변경 합성 초안';assert page.locator('#modal').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1');page.locator('[data-act=save-receipt]').scroll_into_view_if_needed()
  page.screenshot(path=str(RESULTS/'fold-viewport.png'));browser.close();print('viewport resize/draft preservation passed')
finally:stop(runtime)
