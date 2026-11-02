"""Historical calendar uses its selected snapshot rows, not mutable global filters."""
import httpx
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,CHROME,PASSWORD,nav,observe,RESULTS
runtime=start(demo=False)
try:
 token=httpx.post(runtime[3]+'/api/login',json={'username':'admin','password':PASSWORD},trust_env=False).json()['token']
 rows=[{'id':str(i),'vehicle_id':str(i),'day':'2026-10-20' if i<3 else '2026-10-21','at':'2026-10-20T03:00:00Z','snapshot':{'vehicle':{'vin':'TESTVIN000000000'+str(i),'model':'합성 차종','kind':'NEW'},'options':[],'items':[]},'adjustments':[]} for i in range(5)]
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page(viewport={'width':1366,'height':900});errors=observe(page,'historical-dispatch')
  page.goto(runtime[3]);page.evaluate('(t)=>sessionStorage.setItem("warehouseToken",t)',token);page.reload()
  page.route('**/api/outbound?month=*',lambda route:route.fulfill(json=rows if route.request.url.endswith('2026-10') else []))
  page.route('**/api/customers/outbounds',lambda route:route.fulfill(json={}))
  nav(page,'outbound');page.locator('[data-dispatch-month]').fill('2026-10');page.locator('[data-dispatch-month]').press('Tab');page.locator('[data-dispatch=day][data-day="2026-10-20"]').click()
  expect(page.locator('[data-act=out-detail]')).to_have_count(3);expect(page.locator('#content h2').last).to_contain_text('2026-10-20 · 출고확정 이력 3건')
  page.locator('[data-dispatch=day][data-day="2026-10-21"]').click();expect(page.locator('[data-act=out-detail]')).to_have_count(2)
  page.locator('[data-dispatch=all]').click();expect(page.locator('[data-act=out-detail]')).to_have_count(5)
  page.locator('[data-dispatch=day][data-day="2026-10-20"]').click();page.locator('#global-search').fill('0266');page.locator('#global-search-form button').click();expect(page.locator('[data-act=out-detail]')).to_have_count(0);expect(page.locator('[data-dispatch=clear-search]')).to_be_visible()
  page.locator('[data-dispatch=clear-search]').click();expect(page.locator('[data-act=out-detail]')).to_have_count(3)
  page.evaluate("const a=document.querySelector('[data-dispatch=day][data-day=\"2026-10-21\"]'),b=document.querySelector('[data-dispatch=day][data-day=\"2026-10-20\"]');a.click();b.click();");expect(page.locator('[data-act=out-detail]')).to_have_count(3)
  page.screenshot(path=str(RESULTS/'dispatch-october-selection.png'),full_page=True)
  page.set_viewport_size({'width':390,'height':844});expect(page.locator('[data-act=out-detail]')).to_have_count(3)
  assert not errors['pageerror'],errors
  browser.close()
 print('PASS October 20 three historical snapshots without current vehicles, next day, month total, visible search/clear and 390px')
finally:stop(runtime)
