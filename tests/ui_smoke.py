from playwright.sync_api import sync_playwright
from pathlib import Path
import json,uuid,subprocess,os,time,sys
server=subprocess.Popen([sys.executable,"-m","uvicorn","server.app:app","--port","8765"],cwd=str(Path(__file__).resolve().parents[1]),env=dict(os.environ,DATABASE_URL="sqlite:////tmp/warehouse-ui.db"),stdout=open("/tmp/warehouse-ui-server.log","w"),stderr=subprocess.STDOUT)
time.sleep(1)
test_vin='L'+uuid.uuid4().hex[:16].upper()
out=Path('/tmp/warehouse-ui');out.mkdir(exist_ok=True)
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':1050},device_scale_factor=1)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8765');page.locator('[name=username]').fill('admin');page.locator('[name=password]').fill('LocalTestOnly-1234');page.locator('#login button').click();page.get_by_role('heading',name='창고 운영 현황').wait_for()
 page.locator('[data-act=receipt]').first.click();page.locator('#vin').fill(test_vin);page.locator('#model_id').select_option(label='PCX125');page.locator('#color_id').select_option(label='화이트');page.locator('[data-act=save-receipt]').click();page.get_by_role('heading',name='PCX125 · 차량 상세').wait_for()
 page.locator('[data-act=ubis-set]').click();page.locator('[data-act=save-ubis]').click();page.locator('[data-act=move]').click();page.locator('[data-act=slot-click]').filter(has_text='빈자리').first.click();page.locator('[data-act=save-move]').click();page.wait_for_timeout(400)
 page.locator('.sidebar [data-page=stock]').click();page.locator('tr[data-act=detail]').first.click();page.locator('[data-act=assign]').click();page.locator('[name=number]').fill('UI-'+uuid.uuid4().hex[:8]);page.locator('[data-act=add-line][data-kind=options]').click();page.locator('.line-master').select_option(label='충전거치대');page.locator('[data-act=add-line][data-kind=items]').click();page.locator('.line-master').nth(1).select_option(label='순정 미러');page.locator('.line-qty').nth(1).fill('2');page.locator('[data-act=save-assign]').click();page.locator('[data-act=work-all]').first.wait_for();page.locator('[data-act=work-all]').first.click();page.wait_for_timeout(200);page.locator('[data-act=work-all]').nth(1).click();page.wait_for_timeout(200);page.locator('[data-action=finish_work]').click();page.wait_for_timeout(200);page.locator('[data-action=ready]').click();page.wait_for_timeout(200)
 page.screenshot(path=str(out/'pc-work.png'),full_page=True)
 page.locator('[data-act=close]').click();page.locator('.sidebar [data-page=dashboard]').click();page.get_by_role('heading',name='창고 운영 현황').wait_for();page.screenshot(path=str(out/'pc-dashboard.png'),full_page=True)
 page.locator('.sidebar [data-page=map]').click();page.screenshot(path=str(out/'pc-map.png'),full_page=True)
 page.locator('.sidebar [data-page=settings]').click();page.get_by_role('heading',name='설정·데이터 교환').wait_for();page.screenshot(path=str(out/'pc-settings.png'),full_page=True)
 page.set_viewport_size({'width':390,'height':844});page.locator('.bottom-nav [data-page=dashboard]').click();page.get_by_role('heading',name='창고 운영 현황').wait_for();page.screenshot(path=str(out/'mobile-home.png'),full_page=True)
 assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'mobile page overflow'
 page.locator('.bottom-nav [data-page=work]').click();page.locator('.vehicle-card').first.click();page.locator('[data-act=dispatch]').click();page.locator('#confirm-vin').fill(test_vin);page.locator('input[id^=hand-]').fill('2');page.locator('[data-act=save-dispatch]').click();page.wait_for_timeout(500);assert not page.locator('#modal').is_visible()
 print(json.dumps({'page_errors':errors,'workflow':'receipt -> ubis -> move -> assign -> work -> dispatch','screenshots':str(out)},ensure_ascii=False));assert not errors
 browser.close()
server.terminate()
