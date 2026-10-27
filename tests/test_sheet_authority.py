from datetime import datetime,timezone
from sqlalchemy import select
from test_workflow import env
from test_purchase_sheet import row,apply,preview
from server.models import Stay,Vehicle,Outbound,Closing,PurchaseRecord
from server import vehicle_inventory as inv

def test_unregistered_unmapped_sheet_counts_before_program(env):
 p={'rows':[row(env,model='원문 차종 그대로',color='원문 색상',received_date='2025-01-10')]}
 apply(env,p)
 with env[0].transaction() as s:
  d=inv.detail(s,'2025-01-11');assert d['display']['count']==1;assert d['display']['known_value']==7790000
  v=d['display']['vehicles'][0];assert v['source_model']=='원문 차종 그대로';assert v['value_excluded']==7081818;assert v['kind']=='UNKNOWN'
  assert not list(s.scalars(select(Vehicle)))
  assert inv.detail(s,'2025-01-09')['current']['count']==0
 assert inv.backfill(env[0],limit=2)==2
 with env[0].transaction() as s:assert inv.latest(s,'2025-01-10') is not None

def test_sheet_date_changes_membership_preserves_original_and_dispatch(env):
 vid=env[5]();vehicle=env[6](vid)
 with env[0].transaction() as s:
  st=s.scalar(select(Stay).where(Stay.vehicle_id==vid));st.received_at=datetime(2026,1,10,tzinfo=timezone.utc);st.closed_at=datetime(2026,1,20,tzinfo=timezone.utc)
  s.add(Outbound(stay_id=st.id,vehicle_id=vid,day='2026-01-20',at=st.closed_at,snapshot={'vehicle':vehicle}));s.add(Closing(day='2026-01-20',actor='test',snapshot={'keep':True}))
  inv.store(s,'2026-01-15','AUTO','test');original=inv.latest(s,'2026-01-15').data
 p={'rows':[row(env,vid,received_date='2026-01-01',color='시트 색상',model='시트 차종')]};apply(env,p)
 with env[0].transaction() as s:
  assert inv.detail(s,'2026-01-05')['display']['count']==1
  assert inv.detail(s,'2026-01-21')['display']['count']==0
  d=inv.detail(s,'2026-01-15');assert d['display']['vehicles'][0]['source_model']=='시트 차종';assert d['saved_outdated'];assert inv.latest(s,'2026-01-15').data==original
  st=s.scalar(select(Stay));assert st.received_at.day==10 and st.closed_at.day==20
  assert s.get(Closing,'2026-01-20').snapshot=={'keep':True}

def test_revised_receipt_date_is_versioned_not_second_vehicle(env):
 p={'rows':[row(env,received_date='2026-01-01')]};apply(env,p)
 p['rows'][0]['received_date']='2026-01-05';p['reason']='시트 입고일 정정';apply(env,p)
 with env[0].transaction() as s:
  assert len(list(s.scalars(select(PurchaseRecord))))==2
  assert inv.detail(s,'2026-01-03')['current']['count']==0;assert inv.detail(s,'2026-01-06')['current']['count']==1

def test_later_operational_registration_and_dispatch_never_double_counts(env):
 data=row(env,received_date='2026-01-01');apply(env,{'rows':[data]})
 vid=env[3]('receive',{'vin':data['vin'],'model_id':env[11],'color_id':env[12],'kind':'NEW','year':2026})['vehicle_id']
 vehicle=env[6](vid)
 with env[0].transaction() as s:
  assert inv.detail(s,inv.today())['current']['count']==1
  st=s.scalar(select(Stay));st.closed_at=datetime(2026,1,20,tzinfo=timezone.utc);s.add(Outbound(stay_id=st.id,vehicle_id=vid,day='2026-01-20',at=st.closed_at,snapshot={'vehicle':vehicle}))
 with env[0].transaction() as s:assert inv.detail(s,'2026-01-21')['current']['count']==0

def test_sheet_pending_does_not_count_and_virtual_inspection(env):
 apply(env,{'rows':[row(env,vin='입고예정',received_date='',region='미입고')]})
 with env[0].transaction() as s:assert inv.detail(s,inv.today())['current']['count']==0
 apply(env,{'rows':[row(env,received_date='2026-01-01')]})
 from test_vehicle_inventory import mutate
 with env[0].transaction() as s:vid=inv.detail(s,'2026-01-02')['current']['vehicles'][0]['vehicle_id']
 mutate(env,'inspection',d='2026-01-02',mode='VIN',vehicle_ids=[vid],complete=True,reason='시트 대조')

def test_unaffected_earlier_snapshot_does_not_need_review(env):
 vid=env[5]()
 with env[0].transaction() as s:
  st=s.scalar(select(Stay));st.received_at=datetime(2026,1,1,tzinfo=timezone.utc)
  inv.store(s,'2026-01-02','AUTO','test')
 apply(env,{'rows':[row(env,received_date='2026-02-01')],'choices':{'0':{'kind':'NEW','create':False}}})
 with env[0].transaction() as s:
  assert inv.detail(s,'2026-01-02')['status']=='자동 집계 완료'
  record=s.scalar(select(PurchaseRecord));assert record.data['inventory_kind']=='UNKNOWN'
