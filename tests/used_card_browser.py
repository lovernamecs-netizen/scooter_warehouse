import base64, io, uuid
import httpx
from PIL import Image
from playwright.sync_api import sync_playwright, expect
from browser_support import start, stop, nav, CHROME, PASSWORD

runtime = start()
try:
    with httpx.Client(base_url=runtime[3], trust_env=False) as client:
        token = client.post('/api/login', json=dict(username='admin', password=PASSWORD)).json()['token']
        client.headers['Authorization'] = 'Bearer ' + token
        state = client.get('/api/state').json()
        def command(action, payload):
            response = client.post('/api/command', json=dict(command_id=str(uuid.uuid4()), action=action, payload=payload))
            response.raise_for_status()
            return response.json()
        def master(kind):
            return next(x['id'] for x in state['masters'] if x['kind'] == kind)
        vid = command('receive', dict(kind='USED', model_id=master('model'), color_id=master('color'),
                                     year=2026, plate='서울가1234', vin='MLHJK05A1P5000099'))['vehicle_id']
        def update(action, **fields):
            vehicle = next(x for x in client.get('/api/state').json()['vehicles'] if x['id'] == vid)
            command(action, dict(vehicle_id=vid, version=vehicle['version'], **fields))
        update('used_profile', profile=dict(pad_front=0, oil_changed=True, equipment_checked=False, repairs_done=False))
        image = io.BytesIO()
        Image.new('RGB', (480, 240), 'green').save(image, 'PNG')
        encoded = base64.b64encode(image.getvalue()).decode()
        update('used_media', category='intake', key='whole', original=encoded, preview=encoded)
        update('used_media', category='damage', key='front', original=encoded, preview=encoded)
        jpeg = io.BytesIO()
        Image.new('RGB', (320, 180), 'blue').save(jpeg, 'JPEG')
        update('used_photo', view='perspective', jpeg=base64.b64encode(jpeg.getvalue()).decode())
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=CHROME)
            page = browser.new_page(viewport=dict(width=1280, height=900))
            page.goto(runtime[3])
            page.evaluate('(t)=>sessionStorage.setItem("warehouseToken",t)', token)
            page.reload()
            nav(page, 'used')
            card = page.locator('.used-vehicle-card').filter(has_text='서울가1234')
            expect(card.locator('h2')).to_have_text('서울가1234')
            expect(card.locator('img')).to_be_visible()
            page.set_viewport_size(dict(width=360, height=780))
            assert card.bounding_box()['width'] <= 360
            expect(card.locator('[data-act=used-open]')).to_have_count(1)
            card.get_by_role('button', name='입고 기록').click()
            expect(page.locator('.used-steps')).to_have_count(0)
            options = page.locator('.used-consumables')
            expect(options.locator('[name=pad_front]')).to_be_hidden()
            options.locator('summary').click()
            expect(options.locator('[name=pad_front]')).to_have_value('0')
            expect(options.locator('[name=oil_changed]')).to_be_checked()
            damage = page.locator('.used-photo-tile[data-category=damage][data-key=front]')
            damage.locator('.photo-tile-add').click()
            panel = page.locator('dialog.used-photo-dialog')
            page.once('dialog', lambda d: d.accept())
            panel.locator('[data-p=delete]').click()
            expect(damage).to_have_count(0)
            expect(panel).to_be_visible()
            panel.locator('[data-p=close]').first.click()
            legacy_delete = page.locator('[data-act=used-legacy-delete]')
            page.once('dialog', lambda d: d.dismiss())
            legacy_delete.click()
            expect(legacy_delete).to_be_visible()
            page.once('dialog', lambda d: d.accept())
            legacy_delete.click()
            expect(legacy_delete).to_have_count(0)
            detail = client.get('/api/used/'+vid).json()
            assert not detail['photos'] and [m['category'] for m in detail['media']] == ['intake']
            page.evaluate("""() => {
                window.WarehouseNative = {capturePhoto: m => {window.captureTarget = JSON.parse(m); document.body.dataset.captureKey=window.captureTarget.key;}, photoJobs: () => {}};
            }""")
            for key in ('plate', 'whole'):
                tile = page.locator('.used-photo-tile[data-category=intake][data-key="'+key+'"]')
                tile.locator('.photo-tile-add').click()
                panel = page.locator('dialog.used-photo-dialog')
                panel.locator('[data-p=camera]').click()
                expect(page.locator('body')).to_have_attribute('data-capture-key', key)
                target = page.evaluate('window.captureTarget')
                assert target['vehicle_id'] == vid and target['category'] == 'intake'
                job = dict(target, id=str(uuid.uuid4()), status='pending', preview='data:image/png;base64,'+encoded)
                page.evaluate('(job) => window.onPhotoJobs([job])', job)
                preview = panel.locator('.used-capture-preview')
                expect(preview).to_be_visible()
                assert preview.evaluate('img => img.decode().then(() => img.naturalWidth)') == 480
                expect(tile.locator('.used-capture-preview')).to_have_attribute('src', job['preview'])
                saved = client.post('/api/used/'+vid+'/upload', data=dict(upload_id=job['id'], stay_id=target['stay_id'], category='intake', key=key), files={'file': ('capture.png', image.getvalue(), 'image/png')})
                saved.raise_for_status()
                page.evaluate('(job) => window.onPhotoJobs([job])', dict(job,status='saved'))
                expect(panel.locator('[data-media="'+job['id']+'"]')).to_be_visible()
                expect(tile.locator('[data-media="'+job['id']+'"]')).to_be_visible()
                panel.locator('[data-p=close]').first.click()
                page.evaluate('window.onPhotoJobs([])')
            whole = page.locator('.used-photo-tile[data-category=intake][data-key=whole]')
            whole.locator('.photo-tile-add').click()
            panel = page.locator('dialog.used-photo-dialog')
            expect(panel.locator('[data-p=delete]')).to_have_count(2)
            page.once('dialog', lambda d: d.accept())
            panel.locator('[data-p=delete]').last.click()
            expect(panel.locator('[data-p=delete]')).to_have_count(1)
            panel.locator('[data-p=close]').first.click()
            page.once('dialog', lambda dialog: dialog.accept())
            page.locator('#modal .modal-head [data-act=close]').click()
            page.locator('[data-act=receipt]').first.click()
            tile = page.locator('.used-photo-tile[data-category=intake][data-key=plate]')
            tile.locator('.photo-tile-add').click()
            panel = page.locator('dialog.used-photo-dialog')
            with page.expect_file_chooser() as chooser:
                panel.locator('[data-p=camera]').click()
            assert chooser.value.element.get_attribute('capture') == 'environment'
            chooser.value.set_files(dict(name='plate.png', mimeType='image/png', buffer=image.getvalue()))
            expect(panel.locator('img[data-media^="pending-"]')).to_be_visible()
            expect(tile.locator('img[data-media^="pending-"]')).to_be_visible()
            browser.close()
finally:
    stop(runtime)
