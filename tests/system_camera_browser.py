from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
 page=browser.new_page(user_agent='Mozilla/5.0 (Linux; Android 14) Chrome/130 Mobile')
 script=(Path(__file__).resolve().parents[1]/'web/camera.js').read_text(encoding='utf-8')
 page.route('https://camera.test/**',lambda route:route.fulfill(body=script,content_type='text/javascript') if route.request.url.endswith('camera.js') else route.fulfill(body='<button id="shot">Camera</button>',content_type='text/html'))
 page.goto('https://camera.test/')
 page.evaluate("async()=>{const m=await import('/camera.js');navigator.mediaDevices.getUserMedia=()=>{throw Error('Web camera must not run')};document.querySelector('button').onclick=()=>{window.result=undefined;m.capturePhoto().then(f=>window.result=f?{size:f.size,name:f.name}:null)}}")
 with page.expect_file_chooser() as pending:page.click('#shot')
 chooser=pending.value
 assert chooser.element.get_attribute('capture')=='environment'
 chooser.set_files({'name':'original.jpg','mimeType':'image/jpeg','buffer':b'synthetic-original-bytes'})
 page.wait_for_timeout(100)
 assert page.evaluate('window.result.size')==24
 assert page.locator('input').count()==0
 with page.expect_file_chooser():page.click('#shot')
 page.locator('input').dispatch_event('cancel');page.wait_for_timeout(100)
 assert page.evaluate('window.result') is None and page.locator('input').count()==0
 browser.close()
print('Android system-camera input/original bytes/cancel checks passed (browser simulation)')
