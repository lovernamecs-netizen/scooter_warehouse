"""Exercise the real login API in Chrome with a simulated browser password vault."""
from playwright.sync_api import expect, sync_playwright
from browser_support import CHROME, PASSWORD, start, stop

runtime = start()
try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=CHROME)
        context = browser.new_context()
        vault = {}
        context.expose_function('testStore', lambda account: vault.update(account))
        context.expose_function('testGet', lambda: vault or None)
        context.add_init_script("""
          Object.defineProperty(navigator.credentials,'store',{value:c=>window.testStore({id:c.id,password:c.password})});
          Object.defineProperty(navigator.credentials,'get',{value:()=>window.testGet()});
        """)
        page = context.new_page()
        page.goto(runtime[3])
        user = page.get_by_label('아이디', exact=True)
        password = page.get_by_label('비밀번호', exact=True)
        remember = page.get_by_label('이 PC에 로그인 정보 저장')
        user.fill('admin')
        password.fill('wrong-synthetic-password')
        remember.check()
        page.locator('#login button[type=submit]').click()
        expect(page.locator('#login-error')).not_to_be_empty()
        assert not vault
        password.fill(PASSWORD)
        page.locator('#login button[type=submit]').click()
        expect(page.locator('#login')).to_have_count(0)
        page.wait_for_function("localStorage.getItem('warehouse.pc-login.username')==='admin'")
        assert vault == {'id':'admin','password':PASSWORD}
        assert PASSWORD not in page.evaluate('JSON.stringify(localStorage)+JSON.stringify(sessionStorage)')
        # A new tab has no warehouse session but shares the same PC profile.
        next_page = context.new_page()
        next_page.goto(runtime[3])
        expect(next_page.locator('#login-user')).to_have_value('admin')
        expect(next_page.locator('#login-password')).to_have_value(PASSWORD)
        expect(next_page.locator('#login')).to_be_visible()
        next_page.get_by_label('이 PC에 로그인 정보 저장').uncheck()
        next_page.locator('#login button[type=submit]').click()
        expect(next_page.locator('#login')).to_have_count(0)
        assert next_page.evaluate("localStorage.getItem('warehouse.pc-login.username')") is None
        mobile = browser.new_context(user_agent='Mozilla/5.0 (Linux; Android 14)')
        phone = mobile.new_page()
        phone.goto(runtime[3])
        expect(phone.locator('#login-password')).to_be_visible()
        expect(phone.locator('#remember-login')).to_have_count(0)
        browser.close()
        print('PASS: login failure/success, vault request, second-tab autofill, opt-out, Android exclusion')
finally:
    stop(runtime)
