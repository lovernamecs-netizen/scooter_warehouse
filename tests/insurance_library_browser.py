"""Shared encrypted library UI on isolated server; no production or paid provider I/O."""
import io,httpx
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,CHROME,PASSWORD,nav,observe,RESULTS
r=start();image_requests=[]
try:
    folder=Path(r[1].name)/'incoming';folder.mkdir()
    for name,color in [('123가4567.jpg','white'),('123가4567_1.jpg','blue'),('123가4567_2.jpg','white')]:Image.new('RGB',(600,850),color).save(folder/name,'JPEG')
    token=httpx.post(r[3]+'/api/login',json={'username':'admin','password':PASSWORD},trust_env=False).json()['token']
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=CHROME,headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000});errors=observe(page,'library')
        page.on('dialog',lambda d:d.accept())
        page.on('request',lambda req:image_requests.append(req.url) if '/library/' in req.url and req.url.endswith('/image') else None)
        page.goto(r[3]);page.evaluate('(t)=>sessionStorage.setItem("warehouseToken",t)',token);page.reload();nav(page,'insurance')
        library=page.locator('#insurance-library-mount');library.locator('summary').click()
        expect(library.locator('#library-path-input')).not_to_have_value('')
        library.locator('#library-path-input').fill(str(Path(r[1].name)/'shared-root'))
        library.locator('[data-library=path]').click();expect(library.locator('#library-progress')).to_contain_text('저장 경로를 변경')
        library.locator('#library-folder').set_input_files(str(folder))
        expect(library.locator('#library-progress')).to_contain_text('등록 완료',timeout=30000)
        expect(library.locator('#library-progress')).to_contain_text('저장 2 · 동일 파일 1 · 실패 0')
        expect(library.locator('[data-library=download]')).to_have_count(2)
        assert not image_requests
        # Refresh/browser session changes do not lose the library.
        page.reload();nav(page,'insurance');library=page.locator('#insurance-library-mount')
        expect(library.locator('[data-library=download]')).to_have_count(2)
        library.locator('#library-query').fill('4567');library.locator('#library-query').press('Enter')
        expect(library.locator('[data-library=download]')).to_have_count(2)
        expect(library.locator('#library-list')).to_contain_text('같은 차량번호 증권 2건')
        library.locator('[data-library=preview]').first.click();expect(page.locator('.insurance-preview img')).to_be_visible();page.locator('.insurance-preview button').click()
        assert len(image_requests)==1
        with page.expect_download() as saved:library.locator('[data-library=download]').first.click()
        with Image.open(saved.value.path()) as image:assert image.format=='JPEG'
        library.locator('[data-library=load]').first.click();expect(page.locator('[data-insurance-plate]')).to_have_count(1)
        page.locator('[data-insurance=confirm]').click();page.locator('[data-library=save-local]').click()
        expect(page.locator('#library-progress')).to_contain_text('동일 파일 1')
        expect(page.locator('[data-insurance=zip]')).to_be_enabled()
        library.locator('#library-query').fill('missing');library.locator('#library-query').press('Enter');expect(library.locator('#library-list')).to_contain_text('검색 결과가 없습니다')
        library.locator('[data-library=reset]').click();expect(library.locator('[data-library=download]')).to_have_count(2)
        page.screenshot(path=str(RESULTS/'insurance-library-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844});assert library.bounding_box()['x']+library.bounding_box()['width']<=391
        page.screenshot(path=str(RESULTS/'insurance-library-mobile.png'),full_page=True)
        assert not errors['pageerror'],errors
        browser.close()
    print('PASS shared folder path, bounded folder upload, duplicates, refresh persistence, indexed search, lazy images, preview/download, return-to-send, scoped store, mobile viewport; no MMS sent')
finally:stop(r)
