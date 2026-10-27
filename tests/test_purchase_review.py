import uuid,copy
import pytest,httpx
from test_workflow import env
from test_purchase_sheet import row,apply
from server.purchase_sheet import ALL_FIELDS

def act(env,body,code=200):
 response=env[1].post('/api/purchases/review',headers=env[2],json={'request_id':str(uuid.uuid4()),**body});assert response.status_code==code,response.text;return response.json()
def test_restore_confirm_and_conflict(env):
 apply(env,{'rows':[row(env)]})
 record=env[1].get('/api/purchases',headers=env[2]).json()['rows'][0];rid=record['id'];day=record['data']['values']['received_date']
 act(env,{'action':'confirm','through':day,'versions':{rid:1},'reason':'검토 완료'})
 source={k:record['data']['source'].get(k,'') for k in ALL_FIELDS};source['memo1']='수정'
 act(env,{'action':'edit','id':rid,'revision':1,'source':source,'reason':'메모 수정'})
 act(env,{'action':'delete','id':rid,'revision':1,'reason':'오래된 요청'},409)
 status=env[1].get('/api/purchases/review',headers=env[2]).json();assert next(event for event in status['events'] if event['kind']=='CONFIRM')['stale']
 act(env,{'action':'delete','id':rid,'revision':2,'reason':'삭제'})
 act(env,{'action':'restore','id':rid,'revision':3,'restore_revision':1,'reason':'원본 복구'})
 records=env[1].get('/api/purchases',headers=env[2]).json();assert len(records['history'])==4
 assert records['rows'][0]['data']['source']==record['data']['source']
 assert all(h['actor']=='admin' for h in records['history'])
 from sqlalchemy import text
 with pytest.raises(Exception):
  with env[0].transaction() as s:s.execute(text('delete from purchase_review_events'))

def test_file_atomic_and_replay(env):
 from test_purchase_xlsx import fixture
 from server.purchase_xlsx import parse
 body=parse(fixture(251),'test.xlsx');body['request_id']=str(uuid.uuid4())
 bad=copy.deepcopy(body);bad['rows'][-1]['source_identity']='invalid'
 response=env[1].post('/api/purchases/import',headers=env[2],json=bad);assert response.status_code==422
 assert not env[1].get('/api/purchases',headers=env[2]).json()['rows']
 response=env[1].post('/api/purchases/import',headers=env[2],json=body);assert response.status_code==200,response.text
 repeat=env[1].post('/api/purchases/import',headers=env[2],json=body);assert repeat.json()==response.json()
 assert len(env[1].get('/api/purchases',headers=env[2]).json()['rows'])==251

def test_oauth_state_and_user_isolation(monkeypatch):
 from server import google_login as g
 from urllib.parse import urlparse,parse_qs
 for k,v in {'CLIENT_ID':'test','CLIENT_SECRET':'dummy','REDIRECT_URI':'http://127.0.0.1:18771/api/google/callback'}.items():monkeypatch.setenv('WAREHOUSE_GOOGLE_'+k,v)
 start=g.start('user-a');query=parse_qs(urlparse(start['url']).query);assert query['code_challenge_method']==['S256']
 client=httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'access_token':'synthetic','scope':g.SCOPE,'expires_in':3600})))
 g.finish(query['state'][0],'fake-code',client);assert g.token('user-a')=='synthetic';assert g.token('user-b') is None
 with pytest.raises(Exception):g.finish(query['state'][0],'replay',client)
 client.close()

def test_google_read_selected_tab_and_url_restriction(monkeypatch):
 from server.google_purchase import read,file_id
 from test_purchase_xlsx import fixture
 monkeypatch.delenv('WAREHOUSE_GOOGLE_CREDENTIALS',raising=False)
 def transport(request):
  if 'fields=' in str(request.url):return httpx.Response(200,json={'mimeType':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})
  return httpx.Response(200,content=fixture(2))
 with httpx.Client(transport=httpx.MockTransport(transport)) as client:
  result=read('https://docs.google.com/spreadsheets/d/abcdefghijk/edit','재고',client,access_token='synthetic');assert result['count']==2
  with pytest.raises(Exception):read('https://docs.google.com/spreadsheets/d/abcdefghijk/edit','없는탭',client,access_token='synthetic')
 with pytest.raises(Exception):file_id('http://127.0.0.1/private')


def test_google_read_permission_message():
 from server.google_purchase import download,file_id
 assert file_id('  https://docs.google.com/spreadsheets/d/abcdefghijk/edit  ')=='abcdefghijk'
 with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(403,json={'error':{'errors':[{'reason':'accessNotConfigured'}]}}))) as client:
  with pytest.raises(Exception) as exc:download(client,'https://www.googleapis.com/drive/v3/files/abcdefghijk')
  assert '같은 프로젝트' in exc.value.detail


def test_large_file_import_performance(env):
 import time
 from test_purchase_xlsx import fixture
 from server.purchase_xlsx import parse
 body=parse(fixture(3110),'large-synthetic.xlsx');body['request_id']=str(uuid.uuid4())
 started=time.monotonic()
 response=env[1].post('/api/purchases/import',headers=env[2],json=body)
 assert response.status_code==200,response.text
 assert response.json()['saved']==3110
 print('3110-row isolated import seconds:',round(time.monotonic()-started,2))
 repeat=env[1].post('/api/purchases/import',headers=env[2],json=body)
 assert repeat.json()==response.json()
