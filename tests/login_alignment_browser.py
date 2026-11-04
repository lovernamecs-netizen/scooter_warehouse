"""Login geometry on synthetic server, including touch UI scale and short keyboard viewport."""
import json,os
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,CHROME,RESULTS
r=start(demo=False)
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True)
  results=[]
  for width,height,touch in [(360,780,True),(600,850,True),(768,900,True),(900,768,True),(1440,900,False),(600,350,True)]:
   for scale in ([70,90,100,130] if touch else [100]):
    context=browser.new_context(viewport={'width':width,'height':height},has_touch=touch)
    page=context.new_page()
    page.add_init_script(f"localStorage.setItem('warehouse-ui-scale-wide','{scale}');localStorage.setItem('warehouse-ui-scale-narrow','{scale}');")
    page.goto(r[3]);expect(page.locator('#login')).to_be_visible()
    box=page.locator('.login').bounding_box()
    delta=round(box['x']+box['width']/2-width/2,2)
    results.append({'width':width,'height':height,'scale':scale,'offset':delta})
    if not os.getenv('LOGIN_BASELINE'):
     assert abs(delta)<2,results[-1]
     assert box['x']>=0 and box['x']+box['width']<=width+1,results[-1]
     assert box['y']>=0
     if box['height']+32*scale/100<height:assert abs(box['y']+box['height']/2-height/2)<2,results[-1]
     page.locator('[name=password]').fill('synthetic-only')
     page.locator('[type=submit]').scroll_into_view_if_needed();assert page.locator('[type=submit]').is_visible()
    if width==600 and height==850 and scale==90:page.screenshot(path=str(RESULTS/'login-centered-touch.png'))
    context.close()
  browser.close();print(json.dumps(results));print('PASS login geometry' if not os.getenv('LOGIN_BASELINE') else 'BASELINE measured')
finally:stop(r)
