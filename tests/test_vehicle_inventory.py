import copy,uuid
from datetime import datetime,timezone
import pytest
from sqlalchemy import select,text
from test_workflow import env
from server import vehicle_inventory as inv
from server.models import Stay,Vehicle,Outbound,Adjustment,Closing,VehicleInventorySnapshot as Snapshot,VehicleInventoryEvent as Event,VehicleInventoryFact as Fact,VehicleValuation as Price

@pytest.fixture
def clock(monkeypatch):
 monkeypatch.setattr(inv,'today',lambda:'2026-10-22');monkeypatch.setattr(inv,'now',lambda:datetime(2026,10,22,3,tzinfo=timezone.utc))

def received(env,at='2026-10-19T01:00:00+00:00'):
 vid=env[5]()
 with env[0].transaction() as s:
  st=s.scalar(select(Stay).where(Stay.vehicle_id==vid));st.received_at=datetime.fromisoformat(at)
  s.add(Fact(vehicle_id=vid,effective_at=st.received_at,data=inv.attrs(s,s.get(Vehicle,vid)),actor='test'))
 return vid

def result(env,d='2026-10-20'):
 with env[0].transaction() as s:return inv.detail(s,d)

def mutate(env,action,d='2026-10-20',status=200,**p):
 state=result(env,d);r=env[1].post('/api/vehicle-inventory/command',headers=env[2],json={'request_id':str(uuid.uuid4()),'action':action,'day':d,'token':state['token'],**p});assert r.status_code==status,r.text;return r

def test_cutoff_future_and_real_dispatch_only(env,clock):
 vid=received(env,'2026-10-20T14:59:59.900000+00:00');assert result(env)['current']['count']==1
 other=received(env,'2026-10-20T15:00:00+00:00');assert result(env)['current']['count']==1
 env[7]('assign',vid,{'scheduled':'2026-10-22','options':[],'items':[]});assert result(env)['current']['count']==1
 with env[0].transaction() as s:
  st=s.scalar(select(Stay).where(Stay.vehicle_id==vid));st.closed_at=datetime(2026,10,20,15,tzinfo=timezone.utc);s.add(Outbound(stay_id=st.id,vehicle_id=vid,day='2026-10-21',at=st.closed_at,snapshot={'vehicle':inv.attrs(s,s.get(Vehicle,vid))}))
 assert result(env)['current']['count']==1;assert result(env,'2026-10-21')['current']['count']==1
 mutate(env,'rebuild',d='2026-10-22',reason='test',status=422)
 assert env[1].get('/api/vehicle-inventory',headers=env[2],params={'day':'2026-10-23','month':'2026-10'}).json()['future']

def test_backfill_idempotent_and_immutable(env,clock):
 received(env);assert inv.backfill(env[0])==3;assert inv.backfill(env[0])==0
 before=result(env);assert before['saved']['source']=='RECONSTRUCTED'
 with pytest.raises(Exception):
  with env[0].transaction() as s:s.execute(text('delete from vehicle_inventory_snapshots'))
 assert result(env)['saved']==before['saved']

def test_prices_freeze_and_review(env,clock):
 vid=received(env);inv.backfill(env[0]);original=result(env)['display'];assert original['missing_value']==1
 mutate(env,'price',scope='MODEL',target_id=env[11],kind='NEW',effective_day='2026-10-19',amount=2000000,reason='기본가')
 state=result(env);assert state['status']=='재확인 필요';assert state['display']==original;assert state['current']['known_value']==2000000
 mutate(env,'rebuild',reason='가액 확인');assert result(env)['status']=='정정 완료'
 mutate(env,'price',scope='VEHICLE',target_id=vid,kind='NEW',effective_day='2026-10-20',amount=2500000,reason='개별가');assert result(env)['current']['known_value']==2500000
 mutate(env,'rebuild',reason='개별가 확인');assert len(result(env)['versions'])==3
 mutate(env,'price',scope='MODEL',target_id=env[11],kind='NEW',effective_day='2026-10-22',amount=3000000,reason='현재 가격');assert result(env)['status']=='정정 완료';assert result(env)['display']['known_value']==2500000

def test_count_vin_inspection_and_correction(env,clock):
 vid=received(env);inv.backfill(env[0]);basis=result(env);key=basis['display']['groups'][0]['key'];stay=basis['display']['vehicles'][0]['stay_id']
 mutate(env,'inspection',mode='COUNT',counts={key:0},reason='미확인 차량');assert result(env)['status']=='재고 차이 발생';assert result(env)['inspection']['data']['vin_mismatch_unresolved']
 mutate(env,'correct',changes=[{'stay_id':stay,'include':False}],reason='중복 집계 확인');assert result(env)['display']['count']==0;assert result(env)['status']=='정정 완료';assert result(env,'2026-10-21')['status']=='재확인 필요'
 mutate(env,'correct',changes=[{'stay_id':stay,'include':True}],reason='역정정');assert result(env)['display']['count']==1
 mutate(env,'inspection',mode='VIN',vehicle_ids=[vid],complete=True,reason='대조');assert result(env)['status']=='실사 확인 완료'
 with env[0].transaction() as s:assert s.get(Vehicle,vid) and s.scalar(select(Stay).where(Stay.vehicle_id==vid)).closed_at is None

def test_permissions_and_retry(env,clock):
 received(env);inv.backfill(env[0]);token=env[1].post('/api/login',json={'username':'worker','password':'test-password-123'}).json()['token'];h={'Authorization':'Bearer '+token};d=result(env)
 payload={'request_id':str(uuid.uuid4()),'action':'rebuild','day':'2026-10-20','token':d['token'],'reason':'test'};assert env[1].post('/api/vehicle-inventory/command',headers=h,json=payload).status_code==403
 r=env[1].post('/api/vehicle-inventory/command',headers=env[2],json=payload);assert r.status_code==200;assert env[1].post('/api/vehicle-inventory/command',headers=env[2],json=payload).json()==r.json();payload['request_id']=str(uuid.uuid4());assert env[1].post('/api/vehicle-inventory/command',headers=env[2],json=payload).status_code==409

def test_void_marks_past_and_preserves_closing(env,clock):
 vid=received(env)
 with env[0].transaction() as s:
  st=s.scalar(select(Stay).where(Stay.vehicle_id==vid));st.closed_at=datetime(2026,10,20,1,tzinfo=timezone.utc);out=Outbound(stay_id=st.id,vehicle_id=vid,day='2026-10-20',at=st.closed_at,snapshot={'vehicle':inv.attrs(s,s.get(Vehicle,vid))});s.add(out);s.flush();oid=out.id;s.add(Closing(day='2026-10-20',actor='test',snapshot={'keep':'original'}))
 inv.backfill(env[0]);assert result(env)['display']['count']==0
 with env[0].transaction() as s:
  s.add(Adjustment(outbound_id=oid,kind='VOID',actor='test',reason='오출고',at=datetime(2026,10,22,1,tzinfo=timezone.utc)));s.add(Stay(vehicle_id=vid,reason='VOID',received_at=datetime(2026,10,22,1,tzinfo=timezone.utc)))
 assert result(env)['status']=='재확인 필요';assert result(env)['current']['count']==1;assert result(env,'2026-10-22')['current']['count']==1
 with env[0].transaction() as s:assert s.get(Closing,'2026-10-20').snapshot=={'keep':'original'}

def test_partial_count_not_full_and_unknown_price(env,clock):
 received(env);other=env[5]('USED')
 with env[0].transaction() as s:s.scalar(select(Stay).where(Stay.vehicle_id==other)).received_at=datetime(2026,10,19,tzinfo=timezone.utc)
 inv.backfill(env[0]);basis=result(env);assert basis['display']['count']==2 and basis['display']['missing_value']==2
 mutate(env,'inspection',mode='COUNT',counts={env[11]+':NEW':1},reason='부분 확인');assert result(env)['status']!='실사 확인 완료';assert result(env)['inspection']['data']['delta'] is None


def test_concurrent_catchup_and_overlap_guard(env,clock):
 received(env)
 from concurrent.futures import ThreadPoolExecutor
 with ThreadPoolExecutor(max_workers=2) as pool:counts=list(pool.map(lambda _:inv.backfill(env[0]),range(2)))
 assert sum(counts)==3
 with env[0].transaction() as s:assert len(list(s.scalars(select(Snapshot))))==3

def test_same_quantity_wrong_vin_and_stale_submission(env,clock):
 first=received(env);other=env[5]();inv.backfill(env[0]);state=result(env)
 mutate(env,'inspection',mode='VIN',vehicle_ids=[other],complete=True,reason='차량 상이')
 data=result(env)['inspection']['data'];assert data['delta']==0 and data['different'];assert data['missing_vehicle_ids']==[first] and data['unexpected_vehicle_ids']==[other]
 payload={'request_id':str(uuid.uuid4()),'action':'inspection','day':'2026-10-20','token':state['token'],'mode':'VIN','vehicle_ids':[first],'complete':True}
 assert env[1].post('/api/vehicle-inventory/command',headers=env[2],json=payload).status_code==409

def test_backup_restore_preserves_new_history_and_parts(env,clock,tmp_path):
 import subprocess,sys,os,json
 from pathlib import Path
 from server.parts import PartsBook
 received(env);inv.backfill(env[0]);mutate(env,'price',scope='MODEL',target_id=env[11],kind='NEW',effective_day='2026-10-19',amount=100,reason='가격')
 mutate(env,'rebuild',reason='확인');mutate(env,'inspection',mode='VIN',vehicle_ids=[env[4]()['vehicles'][0]['id']],complete=True,reason='실사')
 with env[0].transaction() as s:
  original={cls.__tablename__:[(x.id,copy.deepcopy(x.data) if hasattr(x,'data') else x.amount) for x in s.scalars(select(cls))] for cls in [Snapshot,Event,Fact,Price]}
  parts=s.get(PartsBook,1)
  if parts is None:
   parts=PartsBook(id=1,data={'items':[], 'entries':[{'id':'synthetic-entry','qty':7}], 'closings':[], 'audit':[]});s.add(parts)
  parts_before=copy.deepcopy(parts.data)
 backup=tmp_path/'backup.enc';root=Path(__file__).resolve().parents[1];restore_url='sqlite:///'+str(tmp_path/'restored.db')
 for action,url in [('backup',str(env[0].engine.url)),('restore',restore_url)]:
  environment=dict(os.environ,DATABASE_URL=url,WAREHOUSE_BACKUP_PASSWORD='synthetic-backup-password',PYTHONUTF8='1');environment.pop('WAREHOUSE_DATA_DIR',None)
  r=subprocess.run([sys.executable,'-X','utf8','-B','-m','server.cli',action,'--file',str(backup)],cwd=root,env=environment,capture_output=True,text=True);assert r.returncode==0,r.stdout+r.stderr
 from server.db import Database
 restored=Database(restore_url)
 with restored.transaction() as s:
  for cls in [Snapshot,Event,Fact,Price]:assert [(x.id,copy.deepcopy(x.data) if hasattr(x,'data') else x.amount) for x in s.scalars(select(cls))]==original[cls.__tablename__]
  parts=s.get(PartsBook,1);assert (parts.data if parts else None)==parts_before
 restored.engine.dispose()

def test_no_evidence_is_not_confirmed_zero(env,clock):
 received(env);r=result(env,'2026-10-10');assert r['display']['no_evidence'];assert r['saved'] is None
 mutate(env,'rebuild',d='2026-10-10',reason='근거 없음',status=422)
