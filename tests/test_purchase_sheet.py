import uuid,copy,json
from sqlalchemy import select,text
from test_workflow import env
from server.models import Vehicle,Stay,Outbound,PurchaseRecord,VehicleValuation,Closing
from server.domain import day,today
from server.purchase_sheet import FIELDS,HEADERS

def row(env,vid=None,**values):
 state=env[4]();v=env[6](vid) if vid else None
 result=dict(zip(FIELDS,['', '합성 공급업체','테스트 대표',state['today'],'테스트 보관지역',next(m['name'] for m in state['masters'] if m['id']==env[11]),v['vin'] if v else 'MLHJK05A1P5000001',next(m['name'] for m in state['masters'] if m['id']==env[12]),'테스트 계약자','재고','7,790,000','7,081,818']))
 return {**result,**values}
def preview(env,p):
 r=env[1].post('/api/purchases/preview',headers=env[2],json=p);assert r.status_code==200,r.text;return r.json()
def apply(env,p,code=200):
 body={**p,'request_id':str(uuid.uuid4()),'token':preview(env,p)['token']}
 r=env[1].post('/api/purchases/apply',headers=env[2],json=body);assert r.status_code==code,r.text;return r,body
def test_source_preserved_alias_and_two_pending(env):
 env[3]('master',{'kind':'model','name':'368G-V2','detail':{'brand_id':next(m['id'] for m in env[4]()['masters'] if m['kind']=='brand')}})
 rows=[row(env,model='존테스368T-G-V2'),row(env,vin='입고예정',received_date='',region='미입고'),row(env,vin='입고예정',received_date='',region='미입고')]
 textdata='\t'.join(HEADERS)+'\n'+'\n'.join('\t'.join(r[k] for k in FIELDS) for r in rows)
 p={'text':textdata};data=preview(env,p);assert data['rows'][0]['model_id'];assert data['rows'][0]['data']['model']=='존테스368T-G-V2'
 apply(env,p);r,_=apply(env,p);assert r.json()['unchanged']==3
 with env[0].transaction() as s:
  records=list(s.scalars(select(PurchaseRecord)));assert len(records)==3;assert records[0].data['source']==rows[0];assert len(list(s.scalars(select(Vehicle))))==0
def test_existing_match_prices_and_replay(env):
 vid=env[5]();p={'rows':[row(env,vid)],'apply_prices':True};r,body=apply(env,p)
 replay=env[1].post('/api/purchases/apply',headers=env[2],json=body);assert replay.status_code==200 and replay.json()==r.json()
 r,_=apply(env,p);assert r.json()['unchanged']==1
 with env[0].transaction() as s:
  assert len(list(s.scalars(select(Vehicle))))==1;assert len(list(s.scalars(select(PurchaseRecord))))==1
  from server.vehicle_inventory import detail
  assert detail(s,today())['current']['known_value']==7790000
def test_conflicts_never_overwrite_or_price(env):
 vid=env[5]();before=copy.deepcopy(env[6](vid));p={'rows':[row(env,vid,received_date='2026-01-01',color='다른 색상')],'apply_prices':True}
 assert preview(env,p)['rows'][0]['differences'];apply(env,p);assert env[6](vid)==before
 with env[0].transaction() as s:
  from server.vehicle_inventory import detail
  assert detail(s,'2026-01-02')['current']['known_value']==7790000
  assert detail(s,'2026-01-02')['current']['vehicles'][0]['color']=='다른 색상'
def test_explicit_new_receipt_and_identifiers(env):
 p={'rows':[row(env)],'choices':{'0':{'create':True,'year':2026,'kind':'NEW'}}};apply(env,p)
 v=env[4]()['vehicles'][0];env[7]('vehicle_edit',v['id'],{'serial_number':'00123ABC','ubis_number':'0000456'})
 v=env[6](v['id']);assert v['serial_number']=='00123ABC' and v['ubis_number']=='0000456'
 p['choices']={};r,_=apply(env,p);assert r.json()['unchanged']==1
def test_revision_and_immutable_history(env):
 vid=env[5]();p={'rows':[row(env,vid)]};apply(env,p)
 p['rows'][0]['contractor']='변경 계약자';apply(env,p,422);p['reason']='계약자 변경';apply(env,p)
 with env[0].transaction() as s:
  records=list(s.scalars(select(PurchaseRecord).order_by(PurchaseRecord.revision)));assert len(records)==2;assert records[0].data['source']['contractor']=='테스트 계약자'
 import pytest
 with pytest.raises(Exception):
  with env[0].transaction() as s:s.execute(text('delete from purchase_records'))
def test_closed_vehicle_links_without_reentry(env):
 vid=env[5]();v=env[6](vid)
 with env[0].transaction() as s:
  st=s.scalar(select(Stay).where(Stay.vehicle_id==vid));st.closed_at=st.received_at;s.add(Outbound(stay_id=st.id,vehicle_id=vid,day=today(),at=st.received_at,snapshot={'vehicle':v}));s.add(Closing(day=today(),actor='test',snapshot={'original':True}))
 p={'rows':[row(env,vid)]};assert '출고' in preview(env,p)['rows'][0]['status'];apply(env,p)
 with env[0].transaction() as s:
  assert len(list(s.scalars(select(Stay))))==1;assert s.get(Closing,today()).snapshot=={'original':True}
def test_stale_preview_and_duplicate_invalid_rows(env):
 vid=env[5]();p={'rows':[row(env,vid)]};token=preview(env,p)['token'];env[7]('vehicle_edit',vid,{'notes':'changed'})
 r=env[1].post('/api/purchases/apply',headers=env[2],json={**p,'token':token,'request_id':str(uuid.uuid4())});assert r.status_code==409
 p={'rows':[row(env),row(env)]};assert preview(env,p)['rows'][1]['errors'];apply(env,p,422)
 p={'rows':[row(env,vat_included='NaN')]};assert preview(env,p)['rows'][0]['errors'];apply(env,p,422)
def test_worker_price_permission_and_pending_edit(env):
 p={'rows':[row(env,received_date='',vin='입고예정',region='미입고')]};apply(env,p)
 with env[0].transaction() as s:rec=s.scalar(select(PurchaseRecord));rid=rec.record_id
 p={'rows':[row(env)],'choices':{'0':{'record_id':rid,'create':True,'kind':'NEW','year':2026}},'reason':'실제 입고 확인'};apply(env,p)
 with env[0].transaction() as s:assert len(list(s.scalars(select(PurchaseRecord))))==2;assert len(list(s.scalars(select(Vehicle))))==1
 token=env[1].post('/api/login',json={'username':'worker','password':'test-password-123'}).json()['token'];p={'rows':[row(env)],'apply_prices':True};body={**p,'token':preview(env,p)['token'],'request_id':str(uuid.uuid4())}
 assert env[1].post('/api/purchases/apply',headers={'Authorization':'Bearer '+token},json=body).status_code==200

def test_purchase_price_preserves_saved_inventory(env,monkeypatch):
 from server import vehicle_inventory as inv
 from datetime import datetime,timezone
 from server.models import VehicleInventoryFact
 monkeypatch.setattr(inv,'today',lambda:'2026-10-23')
 vid=env[5]()
 with env[0].transaction() as s:
  st=s.scalar(select(Stay).where(Stay.vehicle_id==vid));st.received_at=datetime(2026,1,1,tzinfo=timezone.utc)
  s.add(VehicleInventoryFact(vehicle_id=vid,effective_at=st.received_at,data=inv.attrs(s,s.get(Vehicle,vid)),actor='test'))
  inv.store(s,'2026-01-02','RECONSTRUCTED','test');before=inv.detail(s,'2026-01-02')['display']
 apply(env,{'rows':[row(env,vid,received_date='2026-01-01')],'apply_prices':True})
 with env[0].transaction() as s:
  detail=inv.detail(s,'2026-01-02');assert detail['versions'][0]['data']==before;assert detail['display']['known_value']==7790000;assert detail['status']=='재확인 필요';assert detail['current']['known_value']==7790000

def test_additive_migration_keeps_vehicle_and_history(env):
 vid=env[5]();before=env[6](vid)
 with env[0].transaction() as s:
  s.execute(text('ALTER TABLE vehicles DROP COLUMN serial_number'));s.execute(text('ALTER TABLE vehicles DROP COLUMN ubis_number'))
 env[0].init();assert env[6](vid)==before


def test_sheet_only_identifiers_preserved_on_paste_and_revision(env):
 source=row(env);p={'rows':[source],'choices':{'0':{'identifiers':{'serial_number':'000-SERIAL','ubis_number':'000-UBIS'}}}}
 apply(env,p)
 records=env[1].get('/api/purchases',headers=env[2]).json()['rows'];record=records[0]
 assert record['identifiers']==p['choices']['0']['identifiers']
 assert record['data']['source']==source
 assert not env[4]()['vehicles']
 result,_=apply(env,{'rows':[source]});assert result.json()['unchanged']==1
 p['choices']['0']['record_id']=record['id'];p['choices']['0']['identifiers']['ubis_number']='';p['reason']='번호 정정'
 apply(env,p)
 data=env[1].get('/api/purchases',headers=env[2]).json()
 assert data['rows'][0]['identifiers']=={'serial_number':'000-SERIAL','ubis_number':''}
 assert len(data['history'])==2 and data['history'][0]['data']['identifiers']['ubis_number']=='000-UBIS'

def test_sheet_identifiers_sync_linked_vehicle_and_retry(env):
 vid=env[5]();p={'rows':[row(env,vid)],'choices':{'0':{'identifiers':{'serial_number':'000-S','ubis_number':'000-U'}}}}
 result,body=apply(env,p);version=env[6](vid)['version']
 assert env[6](vid)['serial_number']=='000-S' and env[6](vid)['ubis_number']=='000-U'
 assert env[1].post('/api/purchases/apply',headers=env[2],json=body).json()==result.json()
 assert env[6](vid)['version']==version
 result,_=apply(env,{'rows':p['rows']});assert result.json()['unchanged']==1
 assert env[6](vid)['version']==version
 invalid={**p,'choices':{'0':{'identifiers':{'serial_number':'X'*121}}}}
 assert env[1].post('/api/purchases/preview',headers=env[2],json=invalid).status_code==422


def test_seventeen_columns_and_legacy_preservation(env):
 from server.purchase_sheet import ALL_FIELDS,ALL_HEADERS
 data={**row(env),'serial_number':'054687311','memo1':' 메모 원문 ','memo2':'둘째 메모','ubis_installation':'유비스','ubis_number':'0253293322'}
 p={'text':'\t'.join(ALL_HEADERS)+'\n'+'\t'.join(data[k] for k in ALL_FIELDS)}
 apply(env,p);result,_=apply(env,p);assert result.json()['unchanged']==1
 rec=env[1].get('/api/purchases',headers=env[2]).json()['rows'][0]
 assert rec['data']['source']==data and rec['identifiers']['serial_number']=='054687311'
 result,_=apply(env,{'rows':[row(env)]});assert result.json()['unchanged']==1
 for mark,num in [('유비스',''),('','123'),('기타','123')]:
  bad={'rows':[{**data,'ubis_installation':mark,'ubis_number':num}]}
  assert preview(env,bad)['rows'][0]['errors'];apply(env,bad,422)
 p={'rows':[{**data,'ubis_installation':'','ubis_number':''}],'reason':'미설치 확인'};apply(env,p)
 assert env[1].get('/api/purchases',headers=env[2]).json()['rows'][0]['identifiers']['ubis_number']==''


def test_seventeen_markdown_and_trailing_empty_cells(env):
 from server.purchase_sheet import ALL_FIELDS,parse
 data={**row(env),'serial_number':'054687311','memo1':'','memo2':'','ubis_installation':'','ubis_number':''}
 tsv='\t'.join(data[k] for k in ALL_FIELDS)
 assert parse({'text':tsv})[0]==data
 markdown='| '+' | '.join(data[k] for k in ALL_FIELDS)+' |\n|'+ '|'.join([':---:']*17)+'|'
 assert parse({'text':markdown})[0]==data
 apply(env,{'text':tsv})
