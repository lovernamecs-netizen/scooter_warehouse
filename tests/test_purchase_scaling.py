import uuid,json,time,io,sqlite3
from concurrent.futures import ThreadPoolExecutor
from test_workflow import env
from test_purchase_xlsx import fixture
from server.purchase_xlsx import parse
from server.models import PurchaseRecord
from sqlalchemy import select

def imported(env,n=123):
 p=parse(fixture(n),'synthetic.xlsx');p['request_id']=str(uuid.uuid4())
 r=env[1].post('/api/purchases/import',headers=env[2],json=p);assert r.status_code==200,r.text
 return p

def test_bounded_pages_filters_history_and_review(env):
 p=imported(env)
 q=env[1].get('/api/purchases/page',headers=env[2],params={'month':'2026-01'});assert q.status_code==200,q.text
 data=q.json();assert len(data['rows'])==50 and data['count']==123 and data['days']=={'2026-01-02':123} and data['history']==[]
 q=env[1].get('/api/purchases/page',headers=env[2],params={'month':'2026-01','filters':json.dumps({'vin':{'mode':'contains','text':'000122'}})}).json();assert q['count']==1
 record=q['rows'][0]
 history=env[1].get('/api/purchases/history/'+record['id'],headers=env[2]).json();assert history['count']==1
 review=env[1].get('/api/purchases/review-summary',headers=env[2],params={'through':'2026-01-02'}).json();assert len(review['changes'])==50 and review['count']==123
 r=env[1].post('/api/purchases/review',headers=env[2],json={'action':'confirm','through':'2026-01-02','review_token':review['token'],'reason':'test','request_id':str(uuid.uuid4())});assert r.status_code==200,r.text
 result=env[1].get('/api/purchases/requests/'+p['request_id'],headers=env[2]).json();assert result['state']=='committed' and result['result']['saved']==123
 assert env[1].get('/api/purchases/page?month=2026-01').status_code==401

def test_wal_read_does_not_wait_for_writer(env):
 imported(env,1)
 with env[0].transaction() as writer:
  with ThreadPoolExecutor() as pool:
   task=pool.submit(lambda:env[1].get('/api/purchases/page?month=2026-01',headers=env[2]))
   result=task.result(timeout=3);assert result.status_code==200,result.text

def test_raw_numeric_identifier_with_date_style():
 from openpyxl import Workbook
 from server.purchase_sheet import ALL_HEADERS
 book=Workbook();sheet=book.active;sheet.title='재고';sheet.append(['']+ALL_HEADERS);sheet.append(['']*18)
 sheet['G2']='합성차종';sheet['N2']=54687311;sheet['N2'].number_format='yyyy-mm-dd';sheet['R2']=253293322;sheet['R2'].number_format='yyyy-mm-dd';sheet['L2']='=1+1'
 data=io.BytesIO();book.save(data);result=parse(data.getvalue(),'test.xlsx')['rows'][0]
 assert result['data']['serial_number']=='54687311' and result['data']['ubis_number']=='253293322'
 assert result['source_cells']['vat_included']['formula']=='1+1'

def test_sqlite_backup_roundtrip_preserves_purchase_history(env,tmp_path):
 imported(env,2)
 record=env[1].get('/api/purchases/page?month=2026-01',headers=env[2]).json()['rows'][0]
 out=env[1].post('/api/purchases/review',headers=env[2],json={'action':'delete','id':record['id'],'revision':1,'reason':'test','request_id':str(uuid.uuid4())});assert out.status_code==200
 source=sqlite3.connect(env[0].engine.url.database);backup=sqlite3.connect(str(tmp_path/'backup.db'));source.backup(backup);source.close();backup.close()
 restored=sqlite3.connect(str(tmp_path/'restored.db'));saved=sqlite3.connect(str(tmp_path/'backup.db'));saved.backup(restored);saved.close()
 assert restored.execute('select count(*) from purchase_records').fetchone()[0]==3
 assert restored.execute("select count(*) from purchase_review_events where kind='DELETE'").fetchone()[0]==1
 try:restored.execute('delete from purchase_records');assert False
 except sqlite3.DatabaseError:pass
 restored.close()

def test_archive_restore_preserves_import_and_deletion(env,tmp_path):
 from server.photo_backup import backup,restore
 imported(env,2)
 record=env[1].get('/api/purchases/page?month=2026-01',headers=env[2]).json()['rows'][0]
 result=env[1].post('/api/purchases/review',headers=env[2],json={'action':'delete','id':record['id'],'revision':1,'reason':'synthetic','request_id':str(uuid.uuid4())});assert result.status_code==200
 archive=backup(env[0]);restored=restore(archive['file'],tmp_path/'restored-archive',True)
 with sqlite3.connect(restored['database']) as db:
  assert db.execute('select count(*) from purchase_records').fetchone()[0]==3
  assert db.execute("select count(*) from purchase_review_events where kind='IMPORT'").fetchone()[0]==1
  assert db.execute("select count(*) from purchase_review_events where kind='DELETE'").fetchone()[0]==1
  assert db.execute('select count(*) from sessions').fetchone()[0]==0

def test_google_read_route_and_session_isolation(env,monkeypatch):
 from server import google_purchase,google_login
 seen=[]
 monkeypatch.setattr(google_purchase,'read',lambda url,sheet,access_token:seen.append(access_token) or {'count':0})
 request=type('Request',(),{'headers':env[2]})()
 key=google_login.connection_key(env[1].get('/api/state',headers=env[2]).json()['user']['id'],request)
 import time
 google_login._tokens[key]={'access_token':'synthetic-session-token','until':time.time()+60}
 response=env[1].post('/api/purchases/google',headers=env[2],json={'url':'https://docs.google.com/spreadsheets/d/test','sheet':'재고'})
 assert response.status_code==200,response.text
 assert seen==['synthetic-session-token']
 second=env[1].post('/api/login',json={'username':'admin','password':'test-password-123'}).json()['token']
 response=env[1].post('/api/purchases/google',headers={'Authorization':'Bearer '+second},json={'url':'test','sheet':'재고'})
 assert response.status_code==200 and seen[-1] is None
 google_login._tokens.pop(key,None)
