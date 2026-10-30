from browser_support import nav
import json,uuid,httpx
from datetime import date,timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,observe,PASSWORD,CHROME,RESULTS
from server.db import Database
from server.vehicle_inventory import backfill
runtime=start(demo=True)
try:
 c=httpx.Client(base_url=runtime[3],trust_env=False,timeout=30);token=c.post('/api/login',json={'username':'admin','password':PASSWORD}).json()['token'];c.headers['Authorization']='Bearer '+token
 s=c.get('/api/state').json();today=s['today'];past=(date.fromisoformat(today)-timedelta(days=2)).isoformat();received=(date.fromisoformat(today)-timedelta(days=3)).isoformat()
 models=[m for m in s['masters'] if m['kind']=='model'][:2];color=next(m for m in s['masters'] if m['kind']=='color')
 for n,m in enumerate(models):
  r=c.post('/api/command',json={'command_id':str(uuid.uuid4()),'action':'receive','payload':{'vin':f'MLHJK05A1P500000{n}','kind':'NEW','model_id':m['id'],'color_id':color['id'],'year':2026,'received_date':received}});r.raise_for_status()
 testdb=Database('sqlite:///'+str(Path(runtime[1].name)/'test.db'));backfill(testdb);testdb.engine.dispose()
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});errors=observe(page,'vehicle-inventory')
  page.goto(runtime[3]);page.evaluate('(t)=>sessionStorage.setItem("warehouseToken",t)',token);page.reload();nav(page,'closing');page.locator('#vehicle-inventory').locator('xpath=ancestor::details[1]').locator('summary').first.click();expect(page.locator('.vi-panel')).to_be_visible();expect(page.locator('.vi-panel')).to_contain_text('오늘 예상 재고')
  page.locator(f'[data-vinv=day][data-day="{past}"]').click();expect(page.locator('.vi-panel')).to_contain_text('가액 미등록');expect(page.locator('.vi-panel')).to_contain_text('저장 버전 1')
  page.locator('[data-vinv=price]').first.click();page.locator('#vi-form [name=amount]').fill('2000000');page.locator('#vi-form [name=effective_day]').fill(received);page.locator('#vi-form [name=reason]').fill('합성 기본 가액');page.locator('[data-vinv=save-price]').click();expect(page.locator('.vi-panel')).to_contain_text('재확인 필요')
  page.locator('[data-vinv=rebuild]').click();page.locator('#vi-form [name=reason]').fill('가격 근거 확인');page.locator('#vi-form [name=approve]').check();page.locator('[data-vinv=save-rebuild]').click();expect(page.locator('.vi-panel')).to_contain_text('저장 버전 2')
  page.locator('[data-vinv=inspect-count]').click();inputs=page.locator('#vi-form [data-count]');assert inputs.count()==2
  for item in inputs.all():item.fill('1')
  page.locator('#vi-form [name=complete]').check();page.locator('#vi-form [name=reason]').fill('합성 수량 대조');page.locator('[data-vinv=save-count]').click();expect(page.locator('.vi-panel')).to_contain_text('실사 확인 완료')
  page.locator('[data-vinv=correct]').click();page.locator('#vi-form [data-correct]').first.select_option('false');page.locator('#vi-form [name=reason]').fill('합성 중복 집계 정정');page.locator('#vi-form [name=approve]').check();page.locator('[data-vinv=save-correct]').click();expect(page.locator('.vi-panel')).to_contain_text('저장 버전 3');expect(page.locator('.vi-panel')).to_contain_text('정정 완료')
  page.screenshot(path=str(RESULTS/'vehicle-calendar-desktop.png'),full_page=True)
  page.set_viewport_size({'width':390,'height':844});expect(page.locator('#vehicle-inventory .month-calendar')).to_be_visible();assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');page.screenshot(path=str(RESULTS/'vehicle-calendar-mobile.png'),full_page=True)
  page.locator('[data-vinv=month][data-delta="-1"]').click();expect(page.locator('#vehicle-inventory .month-calendar')).to_be_visible();page.locator('[data-vinv=today]').click();expect(page.locator('.vi-panel')).to_contain_text('오늘 예상 재고');assert page.locator('[data-vinv=rebuild]').count()==0
  # Existing daily closing still appears beneath the calendar.
  expect(page.locator('#report-day')).to_be_visible();assert not errors['pageerror'] and not errors['console_error'] and not errors['requestfailed'],errors
  (RESULTS/'vehicle-inventory-browser.json').write_text(json.dumps({'passed':True,'checks':['calendar','today provisional','past snapshot','price','stale warning','rebuild version','count inspection','admin correction','mobile','month navigation','legacy closing retained'],'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8');browser.close()
 print('PASS isolated vehicle inventory browser workflow')
finally:stop(runtime)
