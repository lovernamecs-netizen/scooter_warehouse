import json,sqlite3,uuid,zipfile
from contextlib import closing
from sqlalchemy import select,event
from test_workflow import env
from server.models import Vehicle,User,Setting
from server.domain import state,vehicle_dto
from server import photo_backup

def test_state_batch_equivalence_and_bounded_queries(env):
 db,c,h,cmd,read,receive,v,vc,z,opt,item,model,color=env
 ident=receive();vc('move',ident,{'slot_id':z['slots'][0]['id']});vc('assign',ident,{'scheduled':read()['today']})
 with db.transaction() as s:s.add_all([Vehicle(vin='L'+str(i).zfill(16),model_id=model,color_id=color,year=2026) for i in range(1000)])
 count=[]
 def query(*args):count.append(1)
 event.listen(db.engine,'before_cursor_execute',query)
 with db.read() as s:
  u=s.scalar(select(User).where(User.username=='admin'));actual=state(s,u)['vehicles'];queries=len(count)
  expected=[vehicle_dto(s,row,u) for row in s.scalars(select(Vehicle))]
 assert actual==expected
 assert queries<100,queries
 print('STATE_BATCH_QUERIES',queries)
 full=c.get('/api/state',headers=h);version=c.get('/api/state/version',headers=h)
 print('STATE_NETWORK_BYTES',len(full.content),'VERSION_BYTES',len(version.content))
 event.remove(db.engine,'before_cursor_execute',query)

def test_state_version_auth_revision_and_grants(env):
 from test_customer_privacy import another
 db,c,h,cmd,read,receive,*_=env
 assert c.get('/api/state/version').status_code==401
 before=c.get('/api/state/version',headers=h);assert before.headers['cache-control']=='no-store'
 assert before.json()['revision']==read()['revision']
 receive();assert c.get('/api/state/version',headers=h).json()['revision']>before.json()['revision']
 ident,other=another(db)
 assert not c.get('/api/state/version',headers=other).json()['user']['customer_access']
 assert c.post('/api/customers/access',headers=h,json={'user_id':ident,'allowed':True}).status_code==200
 assert c.get('/api/state/version',headers=other).json()['user']['customer_access']
 assert len(before.content)<2000

def test_customer_kind_filtered_before_pagination(env):
 db,c,h,*_=env
 for kind,total in [('PERSON',25),('COMPANY',23)]:
  for i in range(total):
   r=c.post('/api/customers',headers=h,json={'name':'합성검색 '+str(i),'kind':kind,'request_id':str(uuid.uuid4())});assert r.status_code==200
 first=c.post('/api/customers/search',headers=h,json={'query':'합성검색','kind':'COMPANY'}).json()
 assert len(first['items'])==20 and all(x['kind']=='COMPANY' for x in first['items'])
 second=c.post('/api/customers/search',headers=h,json={'query':'합성검색','kind':'COMPANY','after':first['next']}).json()
 assert len(second['items'])==3
 assert not {x['id'] for x in first['items']} & {x['id'] for x in second['items']}

def test_backup_verify_does_not_hold_operational_writer(env,monkeypatch,tmp_path):
 db,*_=env;original=photo_backup.verify;done=[]
 def verify(path):
  if not done:
   with closing(sqlite3.connect(db.engine.url.database,timeout=.2)) as con:
    con.execute('BEGIN IMMEDIATE');con.execute("INSERT INTO settings(key,value) VALUES ('audit_concurrent_write','{}')");con.commit()
   done.append(True)
  return original(path)
 monkeypatch.setattr(photo_backup,'verify',verify)
 result=photo_backup.backup(db);assert done
 with zipfile.ZipFile(result['file']) as z:(tmp_path/'snapshot.db').write_bytes(z.read('warehouse.db'))
 with closing(sqlite3.connect(tmp_path/'snapshot.db')) as con:
  assert con.execute("select count(*) from settings where key='audit_concurrent_write'").fetchone()[0]==0
  assert con.execute('pragma integrity_check').fetchone()[0]=='ok'
 with db.read() as s:assert s.get(Setting,'audit_concurrent_write') is not None
