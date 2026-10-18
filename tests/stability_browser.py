"""Real isolated uvicorn + Chrome, with explicitly labelled response fault injection."""
from pathlib import Path
import json,uuid,httpx,sys,subprocess,os,time
from playwright.sync_api import sync_playwright,expect
from browser_support import start,stop,PASSWORD,CHROME,RESULTS
runtime=start();base=runtime[3];errors=[];console=[];failures=[];checks=[]
try:
 c=httpx.Client(base_url=base,trust_env=False)
 token=c.post('/api/login',json={'username':'admin','password':PASSWORD}).json()['token'];c.headers['Authorization']='Bearer '+token
 def state():return c.get('/api/state').json()
 def cmd(action,payload):
  r=c.post('/api/command',json={'command_id':str(uuid.uuid4()),'action':action,'payload':payload});r.raise_for_status();return r.json()
 st=state();model=next(m['id'] for m in st['masters'] if m['kind']=='model');color=next(m['id'] for m in st['masters'] if m['kind']=='color')
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page(viewport={'width':1366,'height':768})
  page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:console.append(m.text) if m.type=='error' else None);page.on('requestfailed',lambda r:failures.append({'url':r.url.split('?')[0],'failure':r.failure}))
  page.goto(base);page.locator('[name=username]').fill('admin');page.locator('[name=password]').fill('incorrect-test-password');page.locator('#login button').click();expect(page.locator('#login-error')).to_contain_text('비밀번호')
  page.locator('[name=password]').fill(PASSWORD);page.locator('#login button').click();expect(page.locator('.username')).to_have_text('admin');checks.append('real login: wrong and correct password')
  page.locator('[data-act=receipt]').first.click();page.locator('[name=notes]').fill('보존할 합성 초안');page.locator('#model_id').select_option(model);page.locator('#color_id').select_option(color)
  payloads=[(422,{'detail':[{'loc':['body','secret'],'msg':'secret_python','input':'secret-data'}]}),(422,{'detail':{'bad':'secret-data'}}),(500,{'detail':'Traceback secret SELECT *','request_id':'a'*32}),(403,{'detail':'forbidden'}),(429,{'detail':'too many'})]
  for status,body in payloads:
   page.route('**/api/command',lambda route,request,status=status,body=body:route.fulfill(status=status,json=body))
   page.locator('[data-act=save-receipt]').click();expect(page.locator('.system-error')).to_be_visible();assert 'secret' not in page.locator('.system-error').inner_text();assert 'Traceback' not in page.locator('.system-error').inner_text()
   page.keyboard.press('Escape');expect(page.locator('.system-error')).not_to_be_visible();expect(page.locator('#modal')).to_be_visible();assert page.locator('[name=notes]').input_value()=='보존할 합성 초안';page.unroute('**/api/command');page.wait_for_timeout(100)
  for status,body in [(502,'<html><script>bad()</script>private</html>'),(503,'')]:
   page.route('**/api/command',lambda route,request,status=status,body=body:route.fulfill(status=status,body=body,content_type='text/html'))
   page.locator('[data-act=save-receipt]').click();expect(page.locator('.system-error')).to_be_visible();assert 'private' not in page.locator('.system-error').inner_text()
   for width,height in [(1366,768),(1920,1080),(360,400),(884,600)]:
    page.set_viewport_size({'width':width,'height':height});box=page.locator('.system-error').bounding_box();assert box['x']>=0 and box['x']+box['width']<=width;page.locator('.system-error button').scroll_into_view_if_needed()
   page.screenshot(path=str(RESULTS/'error-mobile.png'));page.go_back();expect(page.locator('.system-error')).not_to_be_visible();expect(page.locator('#modal')).to_be_visible();assert page.locator('[name=notes]').input_value()=='보존할 합성 초안';page.unroute('**/api/command')
  page.set_viewport_size({'width':1366,'height':768});checks.append('UI response mocks: 422 array/object, 500, 403, 429, HTML502, empty503; ESC/back preserve form')
  page.locator('[data-act=save-receipt]').click();expect(page.locator('#modal')).to_contain_text('VIN 미등록');st=state();v=next(v for v in st['vehicles'] if v['notes']=='보존할 합성 초안');assert not v['vin'];checks.append('actual browser receipt without VIN, persisted API record')
  page.locator('.vehicle-history summary').first.click();page.locator('[data-act=vehicle-edit]').click();page.locator('[name=vin]').fill('MLHJK05A1P5000031');page.locator('[data-act=save-vehicle]').click();expect(page.locator('#modal')).to_contain_text('MLHJK05A1P5000031');checks.append('later VIN edit')
  page.evaluate('document.querySelector("#modal").close()');page.wait_for_timeout(150)
  page.locator('[data-act=receipt]').first.click();page.locator('#model_id').select_option(model);page.locator('#color_id').select_option(color);page.locator('#vin').fill('MLHJK05A1P5000031');page.locator('[data-act=save-receipt]').click();expect(page.locator('.system-error')).to_be_visible();page.screenshot(path=str(RESULTS/'duplicate-vin.png'));page.locator('.system-error button').click();expect(page.locator('#vin')).to_have_value('MLHJK05A1P5000031');checks.append('actual duplicate VIN rejected; draft retained')
  page.evaluate('document.querySelector("#modal").close()');page.wait_for_timeout(150)
  page.locator('[data-act=receipt]').first.click();page.locator('#model_id').select_option(model);page.locator('#color_id').select_option(color);page.locator('[name=notes]').fill('저장 후 조회 실패')
  before=len(state()['vehicles']);page.route('**/api/state',lambda route:route.abort('failed'))
  page.locator('[data-act=save-receipt]').click();expect(page.locator('.system-error')).to_contain_text('저장은 완료');assert len(state()['vehicles'])==before+1
  page.unroute('**/api/state');page.locator('.system-error button').click();page.locator('[data-act=save-receipt]').click();expect(page.locator('#modal')).to_contain_text('VIN 미등록');assert len(state()['vehicles'])==before+1;checks.append('confirmed save then state failure: same UI save retries original id')
  page.evaluate('document.querySelector("#modal").close()');page.wait_for_timeout(150)
  before=len(state()['vehicles']);page.locator('[data-act=receipt]').first.click();page.locator('#model_id').select_option(model);page.locator('#color_id').select_option(color);page.locator('[name=notes]').fill('응답 유실 합성 주문')
  def lose_response(route):route.fetch();route.abort('failed')
  page.route('**/api/command',lose_response);page.locator('[data-act=save-receipt]').click();expect(page.locator('.system-error')).to_be_visible()
  pending=page.evaluate('JSON.parse(sessionStorage.getItem("warehousePending"))');assert pending and len(state()['vehicles'])==before+1
  replay=c.post('/api/command',json=pending);replay.raise_for_status();assert len(state()['vehicles'])==before+1
  page.unroute('**/api/command');page.locator('.system-error button').click();expect(page.locator('[name=notes]')).to_have_value('응답 유실 합성 주문');checks.append('real server saved then response aborted: pending ID replay does not duplicate')
  page.evaluate('document.querySelector("#modal").close()');page.wait_for_timeout(150);page.reload();expect(page.locator('.username')).to_have_text('admin')
  page.locator('[data-page=settings]').first.click();page.locator('[data-act=retry]').click();expect(page.locator('#toast')).to_contain_text('요청 결과를 확인했습니다.');page.locator('[data-page=dashboard]').first.click()
  page.locator('[data-act=receipt]').first.click();page.locator('#model_id').select_option(model);page.locator('#color_id').select_option(color);before=len(state()['vehicles'])
  page.route('**/api/command',lambda route:route.abort('failed'));page.locator('[data-act=save-receipt]').click();expect(page.locator('.system-error')).to_be_visible();assert len(state()['vehicles'])==before and page.evaluate('sessionStorage.getItem("warehousePending")')
  page.unroute('**/api/command');page.locator('.system-error button').click();checks.append('connection lost before server processing: draft and request retained')
  page.evaluate('document.querySelector("#modal").close()');page.wait_for_timeout(150);page.reload();expect(page.locator('.username')).to_have_text('admin')
  page.locator('[data-page=settings]').first.click();page.locator('[data-act=retry]').click();expect(page.locator('#toast')).to_contain_text('요청 결과를 확인했습니다.');page.locator('[data-page=dashboard]').first.click()
  page.locator('[data-act=receipt]').first.click();page.locator('#model_id').select_option(model);page.locator('#color_id').select_option(color)
  c.post('/api/logout',headers={'Authorization':'Bearer '+page.evaluate('sessionStorage.getItem("warehouseToken")')});page.locator('[data-act=save-receipt]').click();expect(page.locator('.system-error')).to_be_visible();expect(page.locator('.system-error')).to_contain_text('만료');expect(page.locator('#modal')).to_be_visible();checks.append('actual revoked session retains open form')
  token=c.post('/api/login',json={'username':'admin','password':PASSWORD}).json()['token'];c.headers['Authorization']='Bearer '+token
  cmd('user',{'username':'readonly','password':PASSWORD,'role':'viewer','active':True})
  viewer=browser.new_page();viewer.goto(base);viewer.locator('[name=username]').fill('readonly');viewer.locator('[name=password]').fill(PASSWORD);viewer.locator('#login button').click();expect(viewer.locator('.username')).to_have_text('readonly')
  viewer_token=viewer.evaluate('sessionStorage.getItem("warehouseToken")');denied=c.post('/api/command',headers={'Authorization':'Bearer '+viewer_token},json={'command_id':str(uuid.uuid4()),'action':'receive','payload':{}});assert denied.status_code==403;viewer.close();checks.append('actual viewer login and server write denied')
  assert not errors,errors
  checks.append('browser pageerror 0');version=browser.version;browser.close()
 # Restart same isolated DB and confirm persisted state without relying on another test run.
 process,temp,log,_=runtime;subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True);process.wait(timeout=10);log.flush()
 env=dict(os.environ,DATABASE_URL='sqlite:///'+str(Path(temp.name)/'test.db'),PYTHONPATH=str(Path(__file__).resolve().parents[1]),PYTHONUTF8='1');env.pop('TEST_DATABASE_URL',None)
 process=subprocess.Popen([sys.executable,'-X','utf8','-B',str(Path(temp.name)/'run.py')],env=env,stdout=log,stderr=subprocess.STDOUT);runtime=process,temp,log,base
 for _ in range(100):
  try:
   if c.get('/__smoke_identity').json().get('id'):break
  except (httpx.HTTPError,ValueError):pass
  time.sleep(.1)
 else:raise AssertionError('restart failed')
 assert any(v['vin']=='MLHJK05A1P5000031' for v in state()['vehicles']);checks.append('actual uvicorn restart preserves DB/login session')
 (RESULTS/'stability-browser.json').write_text(json.dumps({'checks':checks,'chrome':version,'pageerror':errors,'console_errors_expected_http_failures':console,'network_failures':failures},ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(checks,ensure_ascii=False))
finally:stop(runtime)
