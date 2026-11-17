"""Phone layout and warehouse toolbar in a synthetic server with touch emulation."""
from playwright.sync_api import sync_playwright, expect
from browser_support import start, stop, CHROME, PASSWORD, RESULTS

runtime = start()
try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME)
        page = browser.new_page(has_touch=True, is_mobile=True, viewport={'width':360,'height':800})
        page.goto(runtime[3])
        form = page.locator('#login')
        expect(form).to_be_visible()
        assert form.bounding_box()['width'] <= 360
        form.locator('[name=username]').fill('admin')
        form.locator('[name=password]').fill(PASSWORD)
        form.locator('[type=submit]').click()
        page.locator('.bottom-nav [data-page=map]').tap()
        tools = page.locator('#warehouse-tools')
        toggle = page.locator('#compact-warehouse-toggle')
        for width,height in [(320,640),(360,800),(390,844),(412,915),(600,900)]:
            page.set_viewport_size({'width':width,'height':height})
            expect(tools).to_be_hidden()
            expect(toggle).to_be_in_viewport()
            toggle.tap()
            expect(tools.get_by_text('창고 목록')).to_be_visible()
            toggle.tap()
            zoom = page.get_by_role('button',name='지도 확대')
            expect(zoom).to_be_in_viewport()
            assert page.locator('.bottom-nav').evaluate('(bar)=>[...bar.children].every(b=>b.offsetHeight>=44)')
            assert page.evaluate('document.documentElement.scrollWidth') <= width
            bottom=page.locator('.bottom-nav').bounding_box()['y']
            assert page.locator('.map-viewport').bounding_box()['y']+96 < bottom
            if width==360:page.screenshot(path=str(RESULTS/'android-compact-map.png'))
        for width,height in [(915,412),(768,960),(1280,800)]:
            page.set_viewport_size({'width':width,'height':height})
            expect(toggle).to_be_hidden()
            expect(tools.get_by_text('창고 목록')).to_be_visible()
        browser.close()
    print('PASS login, bottom nav, toolbar, map visibility across five phone widths and three wider layouts')
finally:
    stop(runtime)
