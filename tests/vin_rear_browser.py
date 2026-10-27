import json,httpx
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,CHROME,PASSWORD,RESULTS
runtime=start(demo=True)
try:
 c=httpx.Client(base_url=runtime[3],trust_env=False)
 token=c.post('/api/login',json={'username':'admin','password':PASSWORD}).json()['token']
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True)
  page=browser.new_page(viewport={'width':390,'height':844})
  page.goto(runtime[3]);page.evaluate('(t)=>sessionStorage.setItem("warehouseToken",t)',token);page.reload()
  page.evaluate('window.nativeCalls=0;window.WarehouseNative={scan(){window.nativeCalls++}}')
  page.locator('[data-act=scan]:visible').first.click()
  assert page.evaluate('window.nativeCalls')==1
  assert page.locator('.capture-dialog').count()==0
  page.evaluate('window.onNativeVin({raw:"MLHJK05A1P5000001",candidates:["MLHJK05A1P5000001"]})')
  expect(page.locator('#scan-vin')).to_have_value('MLHJK05A1P5000001')
  page.locator('[data-act=scan-again]').click();assert page.evaluate('window.nativeCalls')==2
  page.locator('#modal [data-act=close]').first.click()
  page.evaluate('''async()=>{delete window.WarehouseNative;
   navigator.mediaDevices.getUserMedia=async c=>{window.cameraConstraints=c;throw new DOMException('No rear camera','OverconstrainedError')};
   const m=await import('/camera.js');window.photoPromise=m.capturePhoto({rearRequired:true});}''')
  expect(page.locator('.capture-dialog [role=status]')).to_contain_text('후면 카메라를 열 수 없습니다')
  assert page.evaluate('window.cameraConstraints.video.facingMode.exact')=='environment'
  page.locator('[data-camera=cancel]').first.click()
  assert page.evaluate('window.photoPromise') is None
  browser.close()
 (RESULTS/'vin-rear-browser.json').write_text(json.dumps({'passed':True,'checks':['native scan routing','OCR result','retake routing','web exact environment constraint','no front fallback','cancel'],'physical_device_verified':False}),encoding='utf-8')
 print('PASS VIN rear-camera routing and browser constraints; physical hardware not tested')
finally:stop(runtime)

