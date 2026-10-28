from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,CHROME,PASSWORD
import httpx
r=start()
try:
 token=httpx.post(r[3]+'/api/login',json={'username':'admin','password':PASSWORD},trust_env=False).json()['token']
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True)
  page=browser.new_page(viewport={'width':800,'height':900},has_touch=True)
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(r[3]);page.evaluate('(t)=>sessionStorage.setItem("warehouseToken",t)',token);page.reload()
  expect(page.locator('.ui-scale-controls')).to_be_visible()
  assert page.evaluate('document.documentElement.style.zoom')=='0.9'
  assert page.locator('.sidebar').bounding_box()['width']>=170
  assert page.locator('.nav-section>summary').first.evaluate('(e)=>getComputedStyle(e).whiteSpace')=='nowrap'
  page.locator('.nav-section>summary',has_text='차량 관리').click()
  assert page.locator('.sidebar [data-page=stock]').evaluate('(e)=>getComputedStyle(e).fontSize')=='13px'
  def gesture(factor,count=3):
   page.evaluate('''({factor,count})=>{
    const target=document.querySelector('.content');
    function event(type,m,n){const touches=Array.from({length:n},(_,i)=>new Touch({identifier:i,target,clientX:400+Math.cos(i*2*Math.PI/count)*80*m,clientY:350+Math.sin(i*2*Math.PI/count)*80*m}));target.dispatchEvent(new TouchEvent(type,{bubbles:true,cancelable:true,touches,targetTouches:touches,changedTouches:touches}));}
    event('touchstart',1,count);event('touchmove',factor,count);event('touchmove',factor,count);event('touchend',1,0);
   }''',{'factor':factor,'count':count})
   page.wait_for_timeout(460)
  gesture(.6);assert page.evaluate('document.documentElement.style.zoom')=='0.8'
  gesture(1.5);assert page.evaluate('document.documentElement.style.zoom')=='0.9'
  gesture(.6,2);assert page.evaluate('document.documentElement.style.zoom')=='0.9'
  for _ in range(6):gesture(.6)
  assert page.evaluate('document.documentElement.style.zoom')=='0.7'
  page.reload();assert page.evaluate('document.documentElement.style.zoom')=='0.7'
  page.locator('[data-ui-scale-reset]').click();assert page.evaluate('document.documentElement.style.zoom')=='0.9'
  page.set_viewport_size({'width':400,'height':850});assert page.evaluate('document.documentElement.style.zoom')=='1'
  page.set_viewport_size({'width':900,'height':800});page.wait_for_timeout(200)
  assert page.evaluate('document.documentElement.style.zoom')=='0.9'
  desktop=browser.new_page(viewport={'width':1400,'height':900});desktop.goto(r[3])
  assert desktop.evaluate('document.documentElement.style.zoom')==''
  assert not errors,errors
  browser.close()
 print('PASS fold viewport navigation, 3-touch scale steps/limits/persistence, 2-touch unchanged, folded/unfolded preferences, desktop unchanged. Synthetic touch events; real Galaxy unverified.')
finally:stop(r)
