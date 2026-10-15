from playwright.sync_api import sync_playwright
import subprocess,sys,os,time,json
from pathlib import Path
server=subprocess.Popen([sys.executable,'-m','uvicorn','server.app:app','--port','8766'],cwd=Path(__file__).resolve().parents[1],env=dict(os.environ,DATABASE_URL='sqlite:////tmp/warehouse-ui.db'),stdout=open('/tmp/fold-server.log','w'),stderr=subprocess.STDOUT)
time.sleep(1)
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':390,'height':844},has_touch=True,is_mobile=True,device_scale_factor=1);page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:8766');page.locator('[name=username]').fill('admin');page.locator('[name=password]').fill('LocalTestOnly-1234');page.locator('#login button').click();page.get_by_role('heading',name='창고 운영 현황').wait_for()
  for w,h in [(360,800),(412,915),(768,960),(884,1104),(1024,768)]:
   page.set_viewport_size({'width':w,'height':h});page.wait_for_timeout(100);assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),f'overflow {w}'
  page.set_viewport_size({'width':390,'height':844});page.locator('[data-act=receipt]').first.click();page.locator('#vin').fill('LFOLD000000000001');page.locator('[name=notes]').fill('접기 펼치기 입력 보존');page.set_viewport_size({'width':884,'height':1104});assert page.locator('#vin').input_value()=='LFOLD000000000001';assert page.locator('[name=notes]').input_value()=='접기 펼치기 입력 보존';page.set_viewport_size({'width':390,'height':844});assert page.locator('#vin').input_value()=='LFOLD000000000001';page.locator('[data-act=close]').click()
  # Previously dispatched vehicle is still retrievable by exact VIN scan.
  value=page.evaluate("JSON.parse(localStorage.getItem('warehouseCache')).vehicles[0].vin")
  page.locator('.bottom-nav [data-act=scan]').click();page.locator('#scan-vin').fill(value);page.locator('[data-act=scan-confirm]').click();page.locator('#timeline').wait_for();page.set_viewport_size({'width':884,'height':1104});page.wait_for_timeout(100);assert page.locator('#modal').evaluate("e=>e.classList.contains('inspector')");assert page.locator('body').evaluate("e=>e.classList.contains('inspector-open')");page.screenshot(path='/tmp/warehouse-ui/fold-unfolded.png',full_page=True)
  page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(100);assert not page.locator('#modal').evaluate("e=>e.classList.contains('inspector')");assert page.locator('#modal').is_visible();page.screenshot(path='/tmp/warehouse-ui/fold-cover.png',full_page=True)
  assert not errors,errors
  print(json.dumps({'widths_tested':[360,412,768,884,1024],'input_preservation':True,'detail_preservation':True,'js_errors':errors}));browser.close()
finally:server.terminate()
