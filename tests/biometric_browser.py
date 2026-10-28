import httpx
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,CHROME,PASSWORD
r=start()
try:
 token=httpx.post(r[3]+'/api/login',json={'username':'admin','password':PASSWORD},trust_env=False).json()['token']
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True)
  page=browser.new_page();page.goto(r[3]);expect(page.locator('#enable-biometric')).to_have_count(0)
  page.locator('[name=username]').fill('admin');page.locator('[name=password]').fill(PASSWORD);page.locator('#login [type=submit]').click();expect(page.locator('.sidebar')).to_be_visible()
  page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.add_init_script('''window.bioReady=true;window.bioMode='cancel';window.WarehouseNative={
   biometricStatus:()=>JSON.stringify({available:true,ready:window.bioReady}),
   biometricClear:()=>{window.bioReady=false;},
   biometricEnroll:(id,u,p)=>{window.enrollmentRequested=!!u&&!!p;setTimeout(()=>window.onWarehouseBiometric(id,{error:'생체인증을 취소했습니다.'}),50);},
   biometricLogin:id=>setTimeout(()=>window.onWarehouseBiometric(id,window.bioMode==='success'?{token:window.testToken}:window.bioMode==='invalid'?{token:'invalid-session'}:{error:'생체인증을 취소했습니다.'}),50)
  };''')
  page.goto(r[3]);page.locator('#biometric-login').click();expect(page.locator('#login-error')).to_contain_text('취소');expect(page.locator('#login')).to_be_visible()
  page.evaluate("window.bioMode='invalid'");page.locator('#biometric-login').click();expect(page.locator('#login-error')).to_contain_text('로그인');assert page.evaluate("sessionStorage.getItem('warehouseToken')") is None
  page.evaluate('(t)=>{window.testToken=t;window.bioMode="success"}',token);page.locator('#biometric-login').click();expect(page.locator('.sidebar')).to_be_visible()
  page.evaluate('sessionStorage.clear()');page.reload();page.locator('[name=username]').fill('admin');page.locator('[name=password]').fill(PASSWORD);page.locator('#enable-biometric').check();page.locator('#login [type=submit]').click();expect(page.locator('.sidebar')).to_be_visible()
  assert page.evaluate('window.enrollmentRequested')
  assert page.evaluate('(password)=>!JSON.stringify(localStorage).includes(password)&&!JSON.stringify(sessionStorage).includes(password)',PASSWORD)
  assert not errors,errors
  browser.close()
 print('PASS password login/old APK fallback, biometric callback cancellation/success, invalid server token rejected, enrollment cancel retains password login, no password in web storage. Native biometrics mocked; device unverified.')
finally:stop(r)
