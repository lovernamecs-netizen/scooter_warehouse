"""Regression: Android VIN uses OS camera file capture, never the legacy native scan UI."""
import io,json
from PIL import Image
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,CHROME,PASSWORD
runtime=start(demo=True)
photo=io.BytesIO();Image.new('RGB',(100,60),'white').save(photo,'JPEG')
vin='MLHJK05A1P5000001'
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True)
  for native in (True,False):
   context=browser.new_context(user_agent='Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/130 Mobile Safari/537.36',viewport={'width':390,'height':844})
   page=context.new_page();page.goto(runtime[3]);page.locator('[name=username]').fill('admin');page.locator('[name=password]').fill(PASSWORD);page.locator('#login button').click()
   page.evaluate("()=>{window.legacyCalls=0;window.mediaCalls=0;navigator.mediaDevices.getUserMedia=async()=>{window.mediaCalls++;throw Error('Unexpected custom camera')}}")
   if native:
    page.evaluate("window.WarehouseNative={scan(){window.legacyCalls++},recognizeImage(image){window.nativeImage=image;window.onWarehouseOCR({raw:'MLHJK05A1P5000001',candidates:['MLHJK05A1P5000001']})}}")
   else:
    page.route('**/api/vin/ocr',lambda route:route.fulfill(json={'raw':vin,'candidates':[vin]}))
   for selector in ('[data-act=scan]:visible','[data-act=scan-again]'):
    with page.expect_file_chooser() as chosen:page.locator(selector).first.click()
    chooser=chosen.value
    assert chooser.element.get_attribute('capture')=='environment'
    assert chooser.element.get_attribute('accept')=='image/*'
    chooser.set_files({'name':'synthetic-vin.jpg','mimeType':'image/jpeg','buffer':photo.getvalue()})
    expect(page.locator('#scan-vin')).to_have_value(vin)
    assert page.evaluate('window.legacyCalls===0 && window.mediaCalls===0')
    assert page.locator('.capture-dialog').count()==0
   if native:assert page.evaluate('window.nativeImage.length>0')
   with page.expect_file_chooser() as chosen:page.locator('[data-act=scan-again]').click()
   chosen.value.set_files([])
   assert page.locator('input[type=file][capture]').count()==0
   context.close()
  page=browser.new_page();page.goto(runtime[3])
  page.evaluate("""async()=>{navigator.mediaDevices.getUserMedia=async c=>{window.cameraConstraints=c;throw new DOMException('No rear camera','OverconstrainedError')};const m=await import('/camera.js');window.photoPromise=m.capturePhoto({rearRequired:true});}""")
  expect(page.locator('.capture-dialog [role=status]')).to_contain_text('후면 카메라를 열 수 없습니다')
  assert page.evaluate("window.cameraConstraints.video.facingMode.exact")=='environment'
  page.locator('[data-camera=cancel]').first.click();assert page.evaluate('window.photoPromise') is None
  browser.close()
 print('PASS Android APK/browser routing, rear capture hint, image OCR, retake, cancel; PC rear-only capture preserved. Physical Android camera not tested.')
finally:stop(runtime)
