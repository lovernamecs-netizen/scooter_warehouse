from playwright.sync_api import sync_playwright
from browser_support import start,stop,CHROME
r=start()
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page(viewport={'width':1000,'height':800},has_touch=True)
  page.goto(r[3]);page.evaluate('''async()=>{document.body.innerHTML='<div class="map-viewport" data-map-zoom="1" style="position:absolute;left:10px;top:10px;width:600px;height:400px;overflow:auto;touch-action:none"><div style="width:2000px;height:1600px"><div class="map-canvas" style="width:2000px;height:1600px"><button style="position:absolute;left:500px;top:500px">Vehicle</button></div></div></div>';const v=document.querySelector('.map-viewport');const {bindMapNavigation}=await import('/map-editor.js');bindMapNavigation(v,()=>{});v.scrollLeft=400;v.scrollTop=400;}''')
  def scroll():return page.locator('.map-viewport').evaluate('(v)=>[v.scrollLeft,v.scrollTop]')
  before=scroll();page.mouse.move(400,300);page.mouse.down();page.mouse.move(300,220,steps=10);page.mouse.up();after=scroll();assert after[0]>before[0]+90 and after[1]>before[1]+70,(before,after)
  assert not page.locator('.map-panning').count()
  cdp=page.context.new_cdp_session(page);before=scroll()
  cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':250,'y':240,'id':1},{'x':400,'y':240,'id':2}]})
  cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':200,'y':190,'id':1},{'x':350,'y':190,'id':2}]})
  cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
  after=scroll();assert after[0]>before[0]+45 and after[1]>before[1]+45,(before,after)
  assert abs(float(page.locator('.map-viewport').get_attribute('data-map-zoom'))-1)<.01
  browser.close()
 print('PASS actual Chrome mouse drag and emulated two-touch pan without zoom change. Android hardware unverified.')
finally:stop(r)
