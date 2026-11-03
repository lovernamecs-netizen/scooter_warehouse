import json,sqlite3,hashlib,zipfile
from datetime import datetime,timezone,timedelta
from pathlib import Path
import pytest
from sqlalchemy import select,event,insert,text
from test_workflow import env
from server import photo_backup
from server.models import Setting,Stay,Outbound,Adjustment,History,LONG_TERM_INDEXES
from server.parts_orders import daily,month_counts

def test_month_counts_and_daily_queries_are_bounded(env):
 db,c,h,cmd,state,receive,v,*_=env;vid=receive();queries=[]
 snap={'vehicle':{'vin':'SYNTHETIC','model':'합성','kind':'NEW'},'options':[],'items':[],'parts_order':{'channel':'B2B','lines':[{'key':'SC:INSTALL','item':{'name':'거치대'},'purpose':'INSTALL','source':'WAREHOUSE','qty':1}]}}
 at=datetime(2025,12,20,3,tzinfo=timezone.utc)
 with db.transaction() as s:
  s.execute(insert(Stay),[{'id':'stay'+str(i),'vehicle_id':vid,'received_at':at-timedelta(days=1),'closed_at':at} for i in range(1000)])
  s.execute(insert(Outbound),[{'id':'out'+str(i),'stay_id':'stay'+str(i),'vehicle_id':vid,'at':at,'day':'2025-12-20','snapshot':snap} for i in range(1000)])
  s.add(Adjustment(outbound_id='out0',kind='VOID',reason='합성 취소',actor='test'))
  s.add(Adjustment(outbound_id='out1',kind='RETURN',reason='합성 반품',actor='test'))
  s.add(Adjustment(outbound_id='out2',kind='CORRECTION',reason='합성 보정',actor='test',detail={'line_key':'SC:INSTALL','delta':2}))
 def query(*args):queries.append(1)
 event.listen(db.engine,'before_cursor_execute',query)
 with db.read() as s:
  queries.clear();result=daily(s,'2025-12-20');assert len(queries)==2
  queries.clear();counts=month_counts(s,'2025-12');assert len(queries)==1
 assert result['counts']==counts['2025-12-20']=={'B2B':999}
 assert result['usage'][0]['qty']==1001
 event.remove(db.engine,'before_cursor_execute',query)
 print('1000_OUTBOUNDS_DAILY_QUERIES=2 MONTH_COUNTS_QUERIES=1')

def test_cleanup_failure_is_not_backup_failure(env,monkeypatch):
 db=env[0]
 def denied(*args):raise PermissionError('synthetic permission failure')
 monkeypatch.setattr(photo_backup,'prune_verified',denied)
 result=photo_backup.backup(db);assert Path(result['file']).exists()
 with db.read() as s:
  status=s.get(Setting,'photo_backup_status').value
  assert status['ok'] and status['cleanup_warning'] and status['last_success_at']
  assert 'emergency_database' not in status

def test_invalid_database_snapshot_cannot_replace_last_good_backup(env,monkeypatch):
 db=env[0];good=photo_backup.backup(db);path=Path(good['file']);before=hashlib.sha256(path.read_bytes()).hexdigest();connect=sqlite3.connect
 class BadCheck(sqlite3.Connection):
  def execute(self,sql,*args,**kw):
   if sql=='PRAGMA integrity_check':
    class Result:
     def fetchone(self):return ('synthetic damaged page',)
    return Result()
   return super().execute(sql,*args,**kw)
 def injected(*args,**kwargs):return connect(*args,**dict(kwargs,factory=BadCheck))
 monkeypatch.setattr(photo_backup.sqlite3,'connect',injected)
 with pytest.raises(ValueError,match='무결성'):photo_backup.backup(db)
 assert hashlib.sha256(path.read_bytes()).hexdigest()==before
 with db.read() as s:assert not s.get(Setting,'photo_backup_status').value['ok']
 assert len(list(path.parent.glob('ScooterWarehouse-*.zip')))==1

def test_retention_preserves_required_verified_backup_dates(tmp_path,monkeypatch):
 calls=[];original=photo_backup.verify
 for n in range(1,6):
  data=b'synthetic recovery';manifest={'version':1,'producer':'ScooterWarehouse-data-safety-1','created_at':f'2025-01-{n:02}T00:00:00+00:00','roots':{},'files':{'warehouse.db':{'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}}}
  with zipfile.ZipFile(tmp_path/f'ScooterWarehouse-{n}.zip','w') as z:z.writestr('warehouse.db',data);z.writestr('manifest.json',json.dumps(manifest))
 def verified(p):calls.append(p.name);return original(p)
 monkeypatch.setattr(photo_backup,'verify',verified);photo_backup.prune_verified(tmp_path,3)
 assert len(calls)==5
 assert len(list(tmp_path.glob('*.zip')))==3

def test_additive_indexes_upgrade_existing_tables_and_reentry(env):
 db=env[0];env[5]()
 with db.transaction() as s:
  before=list(s.execute(text('select * from vehicles')))
  for index in LONG_TERM_INDEXES:index.drop(s.connection(),checkfirst=True)
 db.init();db.init()
 with db.read() as s:
  assert list(s.execute(text('select * from vehicles')))==before
  names=set(s.execute(text("select name from sqlite_master where type='index'")).scalars())
  assert {i.name for i in LONG_TERM_INDEXES}<=names
  plan=str(list(s.execute(text("EXPLAIN QUERY PLAN SELECT * FROM adjustments WHERE outbound_id='x' AND kind='VOID'"))))
  assert 'ix_adjustment_outbound_kind' in plan
