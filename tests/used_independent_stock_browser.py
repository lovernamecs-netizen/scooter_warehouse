"""Isolated stock and map UI regression, synthetic vehicles only."""
import uuid
import httpx
from playwright.sync_api import sync_playwright, expect
from browser_support import start, stop, CHROME, PASSWORD, nav

runtime = start()
try:
    client = httpx.Client(base_url=runtime[3], trust_env=False)
    token = client.post('/api/login', json={'username':'admin','password':PASSWORD}).json()['token']
    client.headers['Authorization'] = 'Bearer '+token
    state = client.get('/api/state').json()
    model = next(m['id'] for m in state['masters'] if m['kind']=='model')
    color = next(m['id'] for m in state['masters'] if m['kind']=='color')
    ids = {}
    for kind, vin in [('USED','MLHJK05A1P5000098'),('NEW','MLHJK05A1P5000099')]:
        response = client.post('/api/command', json={'command_id':str(uuid.uuid4()),'action':'receive','payload':{
            'kind':kind,'vin':vin,'model_id':model,'color_id':color,'year':2026}})
        response.raise_for_status()
        ids[kind] = response.json()['vehicle_id']
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME)
        page = browser.new_page(viewport={'width':1280,'height':900})
        errors = []
        page.on('pageerror',lambda e: errors.append(str(e)))
        page.goto(runtime[3])
        page.evaluate('(t)=>sessionStorage.setItem("warehouseToken",t)', token)
        page.reload()
        nav(page,'map')
        unplaced = page.locator('.panel').filter(has=page.get_by_role('heading',name='전체 창고 공통 · 미배치 차량'))
        expect(unplaced).not_to_contain_text('MLHJK05A1P5000098')
        expect(unplaced).to_contain_text('MLHJK05A1P5000099')
        nav(page,'used')
        page.locator('[data-act=detail][data-id="'+ids['USED']+'"]').click()
        expect(page.locator('#modal')).to_contain_text('중고차 재고')
        expect(page.locator('#modal .vehicle-location-lead')).not_to_contain_text('미배치')
        expect(page.locator('#modal .split').first).to_contain_text('재고')
        page.locator('#modal [data-act=close]').first.click()
        nav(page,'stock')
        page.locator('[data-act=detail][data-id="'+ids['USED']+'"]').first.click()
        expect(page.locator('#modal')).to_contain_text('중고차 재고')
        assert not errors, errors
        browser.close()
    print('Map excludes unplaced used vehicles; used inventory and details remain accessible')
finally:
    stop(runtime)
