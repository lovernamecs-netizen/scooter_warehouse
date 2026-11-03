"""Real isolated server/browser with five years of synthetic ledger entries."""
import json,sqlite3,time,statistics
from contextlib import closing
from datetime import date,timedelta
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,CHROME,PASSWORD,RESULTS,nav,observe
from server import parts

r=start()
try:
 data=parts.initial();ids=[x['id'] for x in data['items']];first=date(2021,1,1)
 data['entries']=[{'id':'start','kind':'STOCKTAKE','day':'2021-01-01','at':'2021-01-01T00:00:00','quantities':dict.fromkeys(ids,1000000),'scope':'START_OF_DAY'}]
 for n in range(100000):
  d=(first+timedelta(days=n*1825//100000)).isoformat()
  data['entries'].append({'id':str(n),'kind':'VEHICLE','day':d,'at':d+'T12:00:00','lines':[{'item_id':ids[n%len(ids)],'delta':-1}]})
 with closing(sqlite3.connect(Path(r[1].name)/'test.db')) as con:
  con.execute('INSERT OR REPLACE INTO parts_book(id,revision,data) VALUES (1,1,?)',(json.dumps(data),));con.commit()
 with httpx.Client(base_url=r[3],trust_env=False,timeout=60) as client:
  token=client.post('/api/login',json={'username':'admin','password':PASSWORD}).json()['token'];client.headers['Authorization']='Bearer '+token
  samples=[]
  for _ in range(3):
   t=time.perf_counter();response=client.get('/api/parts',params={'day':'2025-12-20','month':'2025-12'});response.raise_for_status();samples.append(time.perf_counter()-t)
  result={'ledger_events':len(data['entries']),'years':5,'http_seconds':samples,'median_seconds':statistics.median(samples),'response_bytes':len(response.content)}
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page(viewport={'width':1280,'height':900});errors=observe(page,'long-term-server')
  page.goto(r[3]);page.evaluate('(t)=>sessionStorage.setItem("warehouseToken",t)',token);page.reload();nav(page,'parts')
  expect(page.locator('.month-calendar')).to_be_visible(timeout=60000)
  page.locator('[data-part=day]').first.click();expect(page.locator('.month-calendar-day.is-selected')).to_have_count(1,timeout=60000)
  page.screenshot(path=str(RESULTS/'long-term-desktop.png'),full_page=True)
  page.set_viewport_size({'width':390,'height':844});expect(page.locator('.month-calendar')).to_be_visible()
  assert page.locator('.month-calendar').evaluate('(e)=>e.getBoundingClientRect().right')<=390
  page.screenshot(path=str(RESULTS/'long-term-mobile.png'),full_page=True)
  assert not errors['pageerror'],errors
  result['browser_page_errors']=errors['pageerror'];result['viewports']=['1280x900','390x844'];browser.close()
 (RESULTS/'long-term-server-smoke.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)
finally:stop(r)
