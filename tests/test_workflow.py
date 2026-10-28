import os,uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,text
from server.db import Database
from server.app import create_app
from server.models import User
from server.security import hash_password

@pytest.fixture
def env(tmp_path,monkeypatch):
 from cryptography.fernet import Fernet
 private=tmp_path/"customer.key";private.write_bytes(Fernet.generate_key());monkeypatch.setenv("WAREHOUSE_CUSTOMER_KEY_FILE",str(private))
 db=Database(os.getenv('TEST_DATABASE_URL') or 'sqlite:///'+str(tmp_path/'test.db'));db.init()
 with db.transaction() as s:
  if not s.scalar(select(User)):
   for role in ['admin','worker']:s.add(User(username=role,password=hash_password('test-password-123'),role=role))
 c=TestClient(create_app(db));token=c.post('/api/login',json={'username':'admin','password':'test-password-123'}).json()['token'];h={'Authorization':'Bearer '+token}
 customer=c.post('/api/customers',headers=h,json={'name':'합성 테스트 업체','kind':'COMPANY','request_id':str(uuid.uuid4())}).json()['id']
 def cmd(action,payload,status=200,cid=None):
  if action=='assign':payload={'customer_id':customer,**payload}
  r=c.post('/api/command',headers=h,json={'command_id':cid or str(uuid.uuid4()),'action':action,'payload':payload});assert r.status_code==status,r.text;return r.json()
 def state():return c.get('/api/state',headers=h).json()
 suffix=uuid.uuid4().hex[:8]
 brand=cmd('master',{'kind':'brand','name':'Brand'+suffix})['id'];model=cmd('master',{'kind':'model','name':'Model'+suffix,'detail':{'brand_id':brand}})['id'];color=cmd('master',{'kind':'color','name':'White'+suffix,'detail':{'hex':'#ffffff'}})['id'];opt=cmd('master',{'kind':'option','name':'Box'+suffix,'detail':{'capacity':'85L'}})['id'];item=cmd('master',{'kind':'item','name':'Mirror'+suffix})['id']
 cmd('zone',{'name':'Zone'+suffix,'rows':2,'cols':2,'kind':'STORAGE'});z=next(z for z in state()['layout']['zones'] if z['name']=='Zone'+suffix)
 def receive(kind='NEW'):
  vv='L'+uuid.uuid4().hex.upper()[:16];return cmd('receive',{'vin':vv,'model_id':model,'color_id':color,'year':2026,'kind':kind})['vehicle_id']
 def v(id):return next(v for v in state()['vehicles'] if v['id']==id)
 def vc(action,id,extra={},status=200,cid=None):return cmd(action,{'vehicle_id':id,'version':v(id)['version'],**extra},status,cid)
 return db,c,h,cmd,state,receive,v,vc,z,opt,item,model,color

def test_full_lifecycle_immutable_statistics(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,model,color=env;id=receive();vv=v(id)
 cmd('receive',{'vin':vv['vin'],'model_id':model,'color_id':color,'year':2026},409)
 vc('move',id,{'slot_id':z['slots'][0]['id']});vc('ubis',id,{'status':'INSTALLED'})
 vc('assign',id,{'number':str(uuid.uuid4()),'scheduled':state()['today'],'options':[{'master_id':opt,'qty':1}],'items':[{'master_id':item,'qty':2}]});vc('finish_work',id,{},422)
 a=v(id)['assignment'];vc('work_line',id,{'kind':'options','line_id':a['options'][0]['id'],'done':1});vc('work_line',id,{'kind':'items','line_id':a['items'][0]['id'],'done':2});vc('finish_work',id);vc('ready',id)
 cid=str(uuid.uuid4());p={'vehicle_id':id,'version':v(id)['version'],'confirmed_vin':v(id)['vin'],'handed':{a['items'][0]['id']:2}}
 first=cmd('dispatch',p,cid=cid);assert cmd('dispatch',p,cid=cid)==first;assert v(id)['stay_id'] is None
 assert not next(zz for zz in state()['layout']['zones'] if zz['id']==z['id'])['slots'][0]['stay_id'];vc('dispatch',id,p,409)
 r=c.get('/api/report/'+state()['today'],headers=h).json();assert r['dispatched']>=1;assert sum(r['options'].values())>=1;assert sum(r['items'].values())>=2
 before=c.get('/api/outbound',headers=h).json();m=next(m for m in state()['masters'] if m['id']==opt);cmd('master',{**m,'name':'Renamed'+uuid.uuid4().hex});assert c.get('/api/outbound',headers=h).json()==before
 with pytest.raises(Exception):
  with db.transaction() as s:s.execute(text("UPDATE outbound SET day='2000-01-01'"))

def test_move_collision_rollback_versions_concurrent(env):
 db,c,h,cmd,state,receive,v,vc,z,*_=env;a,b=receive(),receive()
 for id in [a,b]:vc('ubis',id,{'status':'INSTALLED'})
 vc('move',a,{'slot_id':z['slots'][0]['id']});vc('move',b,{'slot_id':z['slots'][1]['id']});old=v(a);vc('move',a,{'slot_id':z['slots'][1]['id']},409);assert v(a)['location']==old['location'];vc('vehicle_edit',a,{'notes':'Changed'})
 cmd('move',{'vehicle_id':a,'version':old['version'],'slot_id':z['slots'][2]['id']},409)
 ids=[receive(),receive()]
 for id in ids:vc('ubis',id,{'status':'INSTALLED'})
 versions=[v(id)['version'] for id in ids]
 def run(i):return c.post('/api/command',headers=h,json={'command_id':str(uuid.uuid4()),'action':'move','payload':{'vehicle_id':ids[i],'version':versions[i],'slot_id':z['slots'][2]['id']}}).status_code
 with ThreadPoolExecutor(max_workers=2) as ex:assert sorted(ex.map(run,[0,1]))==[200,409]

def test_grid_shrink_preserves_occupant(env):
 db,c,h,cmd,state,receive,v,vc,z,*_=env;id=receive();vc('ubis',id,{'status':'INSTALLED'});vc('move',id,{'slot_id':z['slots'][-1]['id']});err=cmd('zone',{**z,'rows':1,'cols':1},409);assert v(id)['vin'] in str(err);assert v(id)['location']['slot_id']==z['slots'][-1]['id'];vc('move',id,{'slot_id':z['slots'][0]['id']});cmd('zone',{**z,'rows':1,'cols':1});zz=next(x for x in state()['layout']['zones'] if x['id']==z['id']);assert zz['slots'][0]['id']==z['slots'][0]['id'];cmd('slot',{'id':z['slots'][0]['id'],'version':zz['version'],'label':'FIRST','enabled':False},409)

def test_roles_exception_dispatch_return(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,*_=env;id=receive('USED');vc('equipment',id,{'master_id':opt,'qty':1});vc('assign',id,{'number':str(uuid.uuid4()),'scheduled':state()['today'],'items':[{'master_id':item,'qty':2}]})
 token=c.post('/api/login',json={'username':'worker','password':'test-password-123'}).json()['token'];p={'vehicle_id':id,'version':v(id)['version'],'confirmed_vin':v(id)['vin'],'exception_reason':'미준비 인계 승인'}
 r=c.post('/api/command',headers={'Authorization':'Bearer '+token},json={'command_id':str(uuid.uuid4()),'action':'dispatch','payload':p});assert r.status_code==403;cmd('dispatch',p)
 o=next(x for x in c.get('/api/outbound',headers=h).json() if x['vehicle_id']==id);assert o['snapshot']['options'][0]['origin']=='EXISTING';assert o['snapshot']['items']==[]
 cmd('adjust_outbound',{'outbound_id':o['id'],'version':v(id)['version'],'kind':'RETURN','reason':'반품'});assert v(id)['stay_id'] and v(id)['location'] is None;assert next(x for x in c.get('/api/outbound',headers=h).json() if x['id']==o['id'])['snapshot']==o['snapshot']

def test_import_preview_apply_duplicate_export(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,model,color=env;ms=state()['masters'];mn=next(m['name'] for m in ms if m['id']==model);cn=next(m['name'] for m in ms if m['id']==color);vv='L'+uuid.uuid4().hex.upper()[:16];content=f'vin,model,color,year\n{vv},{mn},{cn},2026\n'.encode();r=c.post('/api/import/preview',headers=h,files={'file':('test.csv',content,'text/csv')});assert r.status_code==200,r.text;job=r.json();assert not job['rows'][0]['error'];cmd('import_apply',{'id':job['id']});cmd('import_apply',{'id':job['id']},409);assert c.get('/api/export',headers=h).content[:2]==b'PK'

def test_auth_and_vin_validation(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,model,color=env;assert c.get('/api/state').status_code==401;cmd('receive',{'vin':'INVALID','model_id':model,'color_id':color,'year':2026},422);cmd('receive',{'vin':'LOOOOOOOOOOOOOOOO1','model_id':model,'color_id':color,'year':2026},422)

def test_closing_immutable(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,*_=env;d='2020-01-01';r=c.get('/api/report/'+d,headers=h).json();cmd('close_day',{'day':d});assert c.get('/api/report/'+d,headers=h).json()['closing']['snapshot']['dispatched']==r['dispatched'];cmd('close_day',{'day':d},409)
 with pytest.raises(Exception):
  with db.transaction() as s:s.execute(text("DELETE FROM closings WHERE day='2020-01-01'"))

def test_command_reuse_different_payload(env):
 db,c,h,cmd,state,receive,v,vc,*_=env;id=receive();cid=str(uuid.uuid4());p={'vehicle_id':id,'version':v(id)['version'],'notes':'one'};cmd('vehicle_edit',p,cid=cid);p['notes']='two';cmd('vehicle_edit',p,409,cid)

def test_dispatch_rollback_after_snapshot_insert(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,*_=env;id=receive();vc('ubis',id,{'status':'INSTALLED'});vc('move',id,{'slot_id':z['slots'][0]['id']});vc('assign',id,{'number':str(uuid.uuid4()),'scheduled':state()['today']});vc('finish_work',id);vc('ready',id)
 if not db.sqlite:pytest.skip('SQLite fault injection; PostgreSQL covered by CI lifecycle')
 with db.transaction() as s:s.execute(text("CREATE TRIGGER injected_failure BEFORE INSERT ON history WHEN NEW.event='DISPATCHED' BEGIN SELECT RAISE(ABORT, 'injected transaction failure'); END"))
 vc('dispatch',id,{'confirmed_vin':v(id)['vin']},409)
 assert v(id)['stay_id'];assert v(id)['location']['kind']=='DISPATCH_STAGING';assert v(id)['assignment']['ready'];assert not any(o['vehicle_id']==id for o in c.get('/api/outbound',headers=h).json())

def test_cancel_order_preserves_installed_equipment(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,*_=env;id=receive('USED');vc('assign',id,{'number':str(uuid.uuid4()),'scheduled':state()['today'],'options':[{'master_id':opt,'qty':1}]});line=v(id)['assignment']['options'][0];vc('work_line',id,{'kind':'options','line_id':line['id'],'done':1});vc('plan_line',id,{'kind':'options','line_id':line['id'],'qty':0},422);vc('cancel_order',id,{'reason':'주문 취소'});assert not v(id)['assignment'];assert v(id)['equipment'][0]['qty']==1
 vc('assign',id,{'number':str(uuid.uuid4()),'scheduled':state()['today']});vc('used_profile',id,{'profile':{'mileage':10000,'exterior':'점검 완료','pad_front':80,'pad_rear':80,'tire_front':80,'tire_rear':80,'oil_changed':True,'oil_date':state()['today'],'equipment_checked':True,'repairs_done':True,'washed':True,'description':''},'complete':True});vc('finish_work',id);vc('ready',id);vc('dispatch',id,{'confirmed_vin':v(id)['vin']});o=next(x for x in c.get('/api/outbound',headers=h).json() if x['vehicle_id']==id);assert o['snapshot']['options'][0]['origin']=='EXISTING'

def test_encrypted_backup_restore(env,tmp_path):
 import subprocess,sys
 from pathlib import Path
 db,c,h,cmd,state,receive,v,vc,*_=env;id=receive();root=Path(__file__).resolve().parents[1];source=str(db.engine.url);target='sqlite:///'+str(tmp_path/'restored.db');backup=tmp_path/'backup.swh'
 if not db.sqlite:pytest.skip('Backup roundtrip run on isolated SQLite target')
 for action,url in [('backup',source),('restore',target)]:
  r=subprocess.run([sys.executable,'-m','server.cli',action,'--file',str(backup)],cwd=root,env=dict(os.environ,DATABASE_URL=url,WAREHOUSE_BACKUP_PASSWORD='test-backup-password-123',PYTHONUTF8='1'),capture_output=True,text=True,encoding='utf-8');assert r.returncode==0,r.stderr+r.stdout
 assert backup.read_bytes()[:4]==b'SWH1';restored=Database(target)
 from server.models import Vehicle,Stay
 with restored.transaction() as s:assert s.get(Vehicle,id).vin==v(id)['vin'];assert s.scalar(select(Stay).where(Stay.vehicle_id==id)) is not None

def test_korean_day_boundary():
 from datetime import datetime,timezone
 from server.domain import day
 assert day(datetime(2026,10,1,14,59,59,tzinfo=timezone.utc))=='2026-10-01'
 assert day(datetime(2026,10,1,15,0,0,tzinfo=timezone.utc))=='2026-10-02'

def test_export_formula_is_text():
 from server.integration import workbook
 from openpyxl import load_workbook
 import io
 data=workbook({'TEST':[{'vin':'00123456789012345','notes':'=HYPERLINK("http://example.com")'}]});w=load_workbook(io.BytesIO(data));assert w['TEST']['B2'].data_type=='s';assert w['TEST']['A2'].value=='00123456789012345'

def test_archive_is_not_a_shipment_and_can_reenter(env):
 db,c,h,cmd,state,receive,v,vc,z,*_=env;id=receive();vc('ubis',id,{'status':'INSTALLED'});vc('move',id,{'slot_id':z['slots'][0]['id']});vv=v(id)['vin'];vc('archive_vehicle',id,{'confirmed_vin':vv,'reason':'잘못 등록한 시험 차량'});assert v(id)['archived'];assert v(id)['stay_id'] is None;assert not any(o['vehicle_id']==id for o in c.get('/api/outbound',headers=h).json());vc('reenter',id,{'reason':'재등록 확인'});assert v(id)['stay_id'];assert not v(id)['archived']


def test_pending_vin_direct_placement_and_delete(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,model,color=env
 base={'vin':'','model_id':model,'color_id':color,'year':2026}
 one=cmd('receive',base)['vehicle_id'];two=cmd('receive',base)['vehicle_id']
 assert v(one)['vin']=='' and v(one)['vin_pending'] and v(one)['reference']!=v(two)['reference']
 vc('vehicle_edit',one,{'vin':'','notes':'later'})
 before=len(state()['vehicles'])
 uninstalled=cmd('receive',{**base,'slot_id':z['slots'][1]['id']})['vehicle_id'];assert v(uninstalled)['ubis']=='NOT_INSTALLED'
 assert len(state()['vehicles'])==before+1
 placed=cmd('receive',{**base,'ubis_installed':True,'slot_id':z['slots'][0]['id']})['vehicle_id']
 assert v(placed)['location']['slot_id']==z['slots'][0]['id'] and v(placed)['ubis']=='INSTALLED'
 cmd('receive',{**base,'ubis_installed':True,'slot_id':z['slots'][0]['id']},409)
 assert len(state()['vehicles'])==before+2
 vc('assign',one,{'number':str(uuid.uuid4()),'scheduled':state()['today']})
 vc('dispatch',one,{'confirmed_vin':''},422)
 vc('delete_vehicle',one,{'confirmation':'삭제','reason':'오입력'},409)
 vv='L'+uuid.uuid4().hex.upper()[:16]
 vc('vehicle_edit',one,{'vin':vv})
 assert not v(one)['vin_pending'] and v(one)['vin']==vv
 vc('vehicle_edit',two,{'vin':vv},409)
 vc('delete_vehicle',placed,{'confirmation':'삭제','reason':'오입력'})
 assert v(placed)['stay_id'] is None and v(placed)['archived']
 assert not next(zz for zz in state()['layout']['zones'] if zz['id']==z['id'])['slots'][0]['stay_id']
 assert c.get('/api/history/'+placed,headers=h).json()[-1]['event']=='DELETED'
 worker=c.post('/api/login',json={'username':'worker','password':'test-password-123'}).json()['token']
 r=c.post('/api/command',headers={'Authorization':'Bearer '+worker},json={'command_id':str(uuid.uuid4()),'action':'delete_vehicle','payload':{'vehicle_id':two,'version':v(two)['version'],'confirmation':'삭제','reason':'x'}})
 assert r.status_code==403
 vc('ubis',one,{'status':'INSTALLED'});vc('finish_work',one);vc('ready',one);vc('dispatch',one,{'confirmed_vin':vv})
 vc('delete_vehicle',one,{'confirmation':'삭제','reason':'x'},409)

def test_import_multiple_blank_vins(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,model,color=env
 ms=state()['masters'];mn=next(m['name'] for m in ms if m['id']==model);cn=next(m['name'] for m in ms if m['id']==color)
 content=f'vin,model,color,year\n,{mn},{cn},2026\n,{mn},{cn},2026\n'.encode()
 result=c.post('/api/import/preview',headers=h,files={'file':('pending.csv',content,'text/csv')})
 assert result.status_code==200,result.text
 job=result.json();assert len(job['rows'])==2 and all(not row['error'] for row in job['rows'])
 ids=cmd('import_apply',{'id':job['id']})['ids'];assert len(set(ids))==2
 assert all(v(id)['vin']=='' and v(id)['vin_pending'] for id in ids)

def test_multi_warehouse_boundaries_and_occupied_protection(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,model,color=env
 rect=[[0,0],[1000,0],[1000,1000],[0,1000]]
 def wh(payload,status=200):return cmd('warehouse',{'revision':state()['revision'],**payload},status)
 assert state()['layout']['warehouses'][0]['id']=='main'
 p={'name':'Small '+str(uuid.uuid4()),'width':1400,'height':1000,'points':rect,'active':True}
 ident=wh(p)['id'];p['id']=ident
 zone=cmd('zone',{'name':'Small slots','rows':3,'cols':10,'kind':'UBIS_WAIT','warehouse_id':ident})
 # zone command returns generic ok; get actual zone through the layout.
 zz=next(a for a in state()['layout']['zones'] if a['warehouse_id']==ident)
 assert len(zz['slots'])==30
 id=receive();vc('move',id,{'slot_id':zz['slots'][0]['id']});assert v(id)['location']['warehouse_id']==ident
 wh({**p,'active':False},409)
 wh({**p,'width':400},409)
 cmd('zone',{**zz,'warehouse_id':'main'},409)
 wh({**p,'points':[[0,0],[1000,1000],[0,1000],[1000,0]]},422)
 assert v(id)['location']['slot_id']==zz['slots'][0]['id']
 vc('ubis',id,{'status':'INSTALLED'});vc('move',id,{'slot_id':z['slots'][0]['id']})
 assert v(id)['location']['warehouse_id']=='main'
 wh({**p,'active':False});vc('move',id,{'slot_id':zz['slots'][0]['id']},409)
 wh(p);assert next(a for a in state()['layout']['zones'] if a['id']==zz['id'])['slots'][0]['id']==zz['slots'][0]['id']
 w3=wh({'name':'Shape '+str(uuid.uuid4()),'width':1000,'height':1000,'points':[[0,0],[1000,0],[1000,500],[500,500],[500,1000],[0,1000]]})['id']
 cmd('zone',{'warehouse_id':w3,'name':'outside','rows':1,'cols':1,'x':700,'y':700},409)
 cmd('zone',{'warehouse_id':w3,'name':'inside','rows':1,'cols':1,'x':20,'y':20})
 from server.warehouses import fits
 assert not fits({'width':1000,'height':1000,'points':[[0,0],[1000,0],[1000,1000],[650,1000],[650,350],[350,350],[350,1000],[0,1000]]},100,600,800,100)
 # Stale metadata edits cannot overwrite another user's changes.
 cmd('warehouse',{**p,'revision':state()['revision']-1},409)

def test_legacy_warehouse_mapping_preserves_locations(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,model,color=env
 from server.models import Setting,Zone
 id=receive();vc('ubis',id,{'status':'INSTALLED'});vc('move',id,{'slot_id':z['slots'][0]['id']})
 with db.transaction() as s:
  item=s.get(Setting,'warehouses');s.delete(item)
  zone=s.get(Zone,z['id']);zone.x=3000;zone.y=1500
 before=state();w=before['layout']['warehouses'][0]
 assert w['width']>3000 and w['height']>1500
 cmd('warehouse',{**w,'name':'기존 창고 이름 변경','revision':before['revision']})
 after=v(id);assert after['location']['slot_id']==z['slots'][0]['id']
 assert after['location']['warehouse']=='기존 창고 이름 변경'

def test_manufacturing_month_snapshot(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,model,color=env
 base={'model_id':model,'color_id':color,'year':2026}
 for month in ['2025-00','2025-13','2025-1','2025-01-01','2199-01']:cmd('receive',{**base,'manufactured_month':month},422)
 id=cmd('receive',{**base,'vin':'L1234567890123456','manufactured_month':'2025-03'})['vehicle_id']
 assert v(id)['manufactured_month']=='2025-03' and v(id)['year']==2026
 vc('vehicle_edit',id,{'manufactured_month':'2025-04'})
 hist=c.get('/api/history/'+id,headers=h).json()
 assert next(x for x in hist if x['event']=='VEHICLE_EDITED')['data']['manufactured_month']=={'from':'2025-03','to':'2025-04'}
 vc('equipment',id,{'master_id':opt,'qty':1});vc('assign',id,{'number':'MONTH-SNAPSHOT','scheduled':state()['today']})
 vc('dispatch',id,{'confirmed_vin':v(id)['vin'],'exception_reason':'스냅샷 검증'})
 before=next(x for x in c.get('/api/outbound',headers=h).json() if x['vehicle_id']==id)
 assert before['snapshot']['vehicle']['manufactured_month']=='2025-04' and before['snapshot']['options'][0]['qty']==1
 vc('vehicle_edit',id,{'manufactured_month':'2025-05'})
 assert next(x for x in c.get('/api/outbound',headers=h).json() if x['vehicle_id']==id)['snapshot']==before['snapshot']
 assert v(receive())['manufactured_month'] is None
 import io
 from openpyxl import load_workbook
 wb=load_workbook(io.BytesIO(c.get('/api/export',headers=h).content),read_only=True)
 assert 'manufactured_month' in next(wb['VEHICLES'].values);wb.close()

def test_manufacturing_month_import(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,model,color=env
 ms=state()['masters'];mn=next(m['name'] for m in ms if m['id']==model);cn=next(m['name'] for m in ms if m['id']==color)
 for month,valid in [('2024-08',True),('2024-13',False)]:
  content=f'vin,model,color,year,manufactured_month\n,{mn},{cn},2025,{month}\n'.encode()
  r=c.post('/api/import/preview',headers=h,files={'file':('test.csv',content,'text/csv')});assert r.status_code==200
  job=r.json();assert bool(job['rows'][0]['error']) is not valid
  if valid:
   cmd('import_apply',{'id':job['id']});assert any(x['manufactured_month']==month for x in state()['vehicles'])

def test_additive_v1_upgrade(env):
 db,c,h,cmd,state,receive,v,vc,*_=env
 if not db.sqlite:pytest.skip('SQLite migration fixture')
 id=receive();before=v(id)
 with db.transaction() as s:
  s.execute(text('ALTER TABLE vehicles DROP COLUMN manufactured_month'))
  s.execute(text("UPDATE settings SET value=:value WHERE key='schema_version'"),{'value':'{"version":1}'})
 db.init();db.init()
 assert v(id)['vin']==before['vin'] and v(id)['stay_id']==before['stay_id'] and v(id)['manufactured_month'] is None


def test_staging_stock_cancel_return_and_actual_dispatch(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,*_=env
 ident=receive('USED');vc('move',ident,{'slot_id':z['slots'][0]['id']})
 vc('assign',ident,{'number':str(uuid.uuid4()),'scheduled':state()['today'],'options':[{'master_id':opt}]})
 line=v(ident)['assignment']['options'][0];assert line['qty']==1
 vc('work_line',ident,{'kind':'options','line_id':line['id'],'done':1});vc('used_profile',ident,{'profile':{'mileage':10000,'exterior':'점검 완료','pad_front':80,'pad_rear':80,'tire_front':80,'tire_rear':80,'oil_changed':True,'oil_date':state()['today'],'equipment_checked':True,'repairs_done':True,'washed':True,'description':''},'complete':True});vc('finish_work',ident)
 old=v(ident);vc('ready',ident,{'warehouse_id':'main'})
 vc('vehicle_edit',ident,{'model_id':old['model_id'],'notes':'출고대기 정보 수정'})
 vv=v(ident);assert vv['stay_id']==old['stay_id'] and vv['equipment']==old['equipment']
 assert vv['location']['kind']=='DISPATCH_STAGING' and vv['state']=='출고대기'
 assert not next(x for x in state()['layout']['zones'] if x['id']==z['id'])['slots'][0]['stay_id']
 report=c.get('/api/report/'+state()['today'],headers=h).json();assert report['current_stock']==1 and report['dispatched']==0
 vc('cancel_order',ident,{'reason':'배정 취소'});assert v(ident)['location']['kind']=='DISPATCH_STAGING' and not v(ident)['assignment']
 vc('move',ident,{'slot_id':z['slots'][0]['id']});assert v(ident)['location']['slot_id']==z['slots'][0]['id']
 vc('assign',ident,{'number':str(uuid.uuid4()),'scheduled':state()['today']});vc('finish_work',ident);vc('ready',ident)
 vc('start_work',ident);assert v(ident)['location']['kind']=='DISPATCH_STAGING' and not v(ident)['assignment']['ready']
 vc('finish_work',ident);vc('ready',ident);vc('dispatch',ident,{'confirmed_vin':v(ident)['vin']})
 assert not v(ident)['stay_id'] and not v(ident)['location']
 r=c.get('/api/report/'+state()['today'],headers=h).json();assert r['current_stock']==0 and r['dispatched']==1 and sum(r['options'].values())==1
 from server.domain import staging
 with db.transaction() as sess:assert not staging(sess)

def test_staging_block_disable_and_atomic_failure(env):
 db,c,h,cmd,state,receive,v,vc,z,*_=env
 w=cmd('warehouse',{'revision':state()['revision'],'name':'대기창고','width':500,'height':500})['id']
 ident=receive('USED');vc('move',ident,{'slot_id':z['slots'][0]['id']});vc('assign',ident,{'number':str(uuid.uuid4()),'scheduled':state()['today']});vc('used_profile',ident,{'profile':{'mileage':10000,'exterior':'점검 완료','pad_front':80,'pad_rear':80,'tire_front':80,'tire_rear':80,'oil_changed':True,'oil_date':state()['today'],'equipment_checked':True,'repairs_done':True,'washed':True,'description':''},'complete':True});vc('finish_work',ident)
 before=v(ident)
 with db.transaction() as s:s.execute(text("CREATE TRIGGER staging_fail BEFORE INSERT ON history WHEN NEW.event='READY' BEGIN SELECT RAISE(ABORT, 'test failure'); END"))
 vc('ready',ident,{'warehouse_id':w},409);assert v(ident)==before
 with db.transaction() as s:s.execute(text('DROP TRIGGER staging_fail'))
 vc('ready',ident,{'warehouse_id':w})
 warehouse=next(x for x in state()['layout']['warehouses'] if x['id']==w)
 cmd('warehouse',{**warehouse,'active':False,'revision':state()['revision']}) # virtual staging does not occupy this warehouse
 vc('move',ident,{'slot_id':z['slots'][0]['id']});assert not v(ident)['assignment']['ready']
 cmd('warehouse',{**warehouse,'active':False,'revision':state()['revision']})

def test_accessory_single_duplicate_and_legacy_preserved(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,*_=env;ident=receive('USED')
 base={'number':str(uuid.uuid4()),'scheduled':state()['today']}
 vc('assign',ident,{**base,'options':[{'master_id':opt,'qty':2}]},422);assert not v(ident)['assignment']
 vc('assign',ident,{**base,'options':[{'master_id':opt},{'master_id':opt}]},409);assert not v(ident)['assignment']
 vc('assign',ident,{**base,'options':[{'master_id':opt}],'items':[{'master_id':item,'qty':2}]})
 vc('plan_line',ident,{'kind':'options','master_id':opt,'qty':1},409)
 vc('equipment',ident,{'master_id':opt},409)
 line=v(ident)['assignment']['options'][0]
 # Represent an order saved by version 1.0.7: update must not rewrite its old quantity.
 from server.models import OptionLine
 with db.transaction() as s:s.get(OptionLine,line['id']).qty=2
 vc('work_line',ident,{'kind':'options','line_id':line['id'],'done':2})
 assert v(ident)['equipment'][0]['qty']==2
 vc('cancel_order',ident,{'reason':'legacy equipment preserved'});assert v(ident)['equipment'][0]['qty']==2

def test_grid_edits_and_move_fault_preserve_identity(env):
 db,c,h,cmd,state,receive,v,vc,z,*_=env;ident=receive('USED');vc('move',ident,{'slot_id':z['slots'][-1]['id']});before=v(ident)
 def zone():return next(x for x in state()['layout']['zones'] if x['id']==z['id'])
 cmd('zone',{**zone(),'rows':3,'cols':3,'name':'확장창고구역','x':80,'y':80})
 assert v(ident)['id']==before['id'] and v(ident)['stay_id']==before['stay_id'] and v(ident)['location']['slot_id']==before['location']['slot_id']
 after=v(ident);layout=zone();cmd('zone',{**layout,'rows':1,'cols':1},409);assert v(ident)==after and zone()==layout
 cmd('zone',{**layout,'x':19000},422);assert v(ident)==after and zone()==layout
 with db.transaction() as s:s.execute(text("CREATE TRIGGER move_fail BEFORE INSERT ON history WHEN NEW.event='MOVED' BEGIN SELECT RAISE(ABORT, 'test move failure'); END"))
 vc('move',ident,{'slot_id':z['slots'][0]['id']},409);assert v(ident)==after
 # Opening the same database again retains the same vehicle and placement.
 reopened=Database(str(db.engine.url));reopened.init()
 from server.models import Vehicle,Placement
 with reopened.transaction() as s:assert s.get(Vehicle,ident).vin==before['vin'] and s.get(Placement,before['stay_id']).slot_id==before['location']['slot_id']


def test_existing_equipment_duplicate_and_cancelled_plan_restore(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,*_=env;ident=receive('USED')
 vc('equipment',ident,{'master_id':opt});vc('equipment',ident,{'master_id':opt},409)
 base={'number':str(uuid.uuid4()),'scheduled':state()['today']}
 vc('assign',ident,{**base,'options':[{'master_id':opt}]},409)
 e=v(ident)['equipment'][0];vc('equipment',ident,{'id':e['id'],'qty':2},422);vc('equipment',ident,{'id':e['id'],'qty':0})
 vc('assign',ident,{**base,'options':[{'master_id':opt}]});line=v(ident)['assignment']['options'][0]
 vc('plan_line',ident,{'kind':'options','line_id':line['id'],'qty':0});vc('plan_line',ident,{'kind':'options','master_id':opt,'qty':1})
 vc('plan_line',ident,{'kind':'options','line_id':line['id'],'qty':1},409)


def test_uninstalled_warehouse_moves_grid_edit_and_completion_gate(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,model,color=env
 ident=receive();vc('move',ident,{'slot_id':z['slots'][0]['id']})
 assert v(ident)['ubis']=='NOT_INSTALLED' and v(ident)['state']=='재고'
 cmd('zone',{**z,'name':'미장착도 보관 가능','rows':3,'cols':3})
 wid=cmd('warehouse',{'revision':state()['revision'],'name':'제2창고','width':800,'height':700})['id']
 cmd('zone',{'warehouse_id':wid,'name':'정규 재고','kind':'STORAGE','rows':2,'cols':2})
 zz=next(x for x in state()['layout']['zones'] if x['warehouse_id']==wid)
 vc('move',ident,{'slot_id':zz['slots'][0]['id']});assert v(ident)['location']['warehouse_id']==wid
 vc('assign',ident,{'number':str(uuid.uuid4()),'scheduled':state()['today']});vc('start_work',ident)
 old=v(ident);vc('finish_work',ident,{},422);assert v(ident)==old
 vc('ubis',ident,{'status':'INSTALLED'});vc('finish_work',ident);assert v(ident)['assignment']['work']=='COMPLETED'
 vc('ubis',ident,{'status':'REMOVED'});vc('ready',ident,{},422);assert v(ident)['location']['slot_id']==zz['slots'][0]['id']

def test_fifo_guard_same_model_color_kind_and_concurrency(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,model,color=env
 old,new,unknown,used=[receive(k) for k in ['NEW','NEW','NEW','USED']]
 vc('vehicle_edit',old,{'manufactured_month':'2024-01'});vc('vehicle_edit',new,{'manufactured_month':'2025-01'});vc('vehicle_edit',used,{'manufactured_month':'2023-01'})
 base={'number':str(uuid.uuid4()),'scheduled':state()['today']}
 vc('assign',new,base,409);vc('assign',unknown,base,409);assert not v(new)['assignment']
 vc('assign',old,base);vc('assign',new,{**base,'number':str(uuid.uuid4())})
 assert v(new)['assignment'] and not v(used)['assignment']
 # If an older vehicle is registered while a form is open, final save rechecks FIFO.
 fresh=receive();vc('vehicle_edit',fresh,{'manufactured_month':'2020-01'})
 vc('assign',unknown,{**base,'number':str(uuid.uuid4())},409)
 # A different color must not be substituted.
 other=cmd('master',{'kind':'color','name':'RED','detail':{'hex':'#ff0000'}})['id'];vc('vehicle_edit',unknown,{'color_id':other})
 vc('assign',unknown,{**base,'number':str(uuid.uuid4())})

@pytest.mark.parametrize('axis',['rows','cols'])
def test_split_merge_preserve_slots_vehicles_orders_and_history(env,axis):
 from server.models import Slot,Placement,History
 db,c,h,cmd,state,receive,v,vc,z,opt,item,*_=env
 ids=[receive('USED') for _ in z['slots']]
 for ident,sl in zip(ids,z['slots']):vc('move',ident,{'slot_id':sl['id']})
 vc('assign',ids[0],{'number':str(uuid.uuid4()),'scheduled':state()['today'],'options':[{'master_id':opt}]})
 original={ident:v(ident) for ident in ids};slot_ids={sl['id'] for sl in z['slots']}
 p={'revision':state()['revision'],'zone_id':z['id'],'mode':'split','axis':axis,'cut':1,'name':'SPLIT-B','x':500,'y':20}
 before=state();resp=c.post('/api/layout/preview',headers=h,json=p);assert resp.status_code==200,resp.text;plan=resp.json()
 assert state()['revision']==before['revision'] and state()['vehicles']==before['vehicles']
 cmd('restructure',{**p,'preview_token':'wrong'},409)
 cmd('restructure',{**p,'preview_token':plan['token']})
 b=next(x for x in state()['layout']['zones'] if x['name']=='SPLIT-B')
 assert {sl['id'] for zz in state()['layout']['zones'] for sl in zz['slots']}==slot_ids
 for ident in ids:
  cur=v(ident);old=original[ident]
  assert cur['vin']==old['vin'] and cur['stay_id']==old['stay_id'] and cur['location']['slot_id']==old['location']['slot_id'] and cur['assignment']==old['assignment']
 p={'revision':state()['revision'],'zone_id':z['id'],'other_id':b['id'],'mode':'merge','axis':axis}
 plan=c.post('/api/layout/preview',headers=h,json=p).json();assert 'token' in plan,plan
 cmd('restructure',{**p,'preview_token':plan['token']})
 assert not next(x for x in state()['layout']['zones'] if x['id']==b['id'])['active']
 assert {sl['id'] for zz in state()['layout']['zones'] for sl in zz['slots']}==slot_ids
 assert all(v(ident)['location']['zone_id']==z['id'] for ident in ids)
 with db.transaction() as sess:
  assert len(list(sess.scalars(select(Placement))))==len(ids)
  assert len(list(sess.scalars(select(History).where(History.event=='LAYOUT_RESTRUCTURED'))))==len(ids)*2


def test_restructure_conflict_rollback_duplicates_and_hidden_slots(env):
 from server.models import Slot
 db,c,h,cmd,state,receive,v,vc,z,opt,item,*_=env
 ident=receive('USED');vc('move',ident,{'slot_id':z['slots'][0]['id']})
 cmd('zone',{'name':'DONOR','kind':'STORAGE','rows':2,'cols':2,'x':500,'y':20});b=next(x for x in state()['layout']['zones'] if x['name']=='DONOR')
 original_slots={sl['id'] for zz in state()['layout']['zones'] for sl in zz['slots']}
 # Shrink target leaves historical disabled slots at coordinates needed by donor.
 cmd('zone',{**z,'cols':1})
 cmd('zone',{**b,'cols':1})
 p={'revision':state()['revision'],'zone_id':z['id'],'other_id':b['id'],'mode':'merge','axis':'cols'}
 plan=c.post('/api/layout/preview',headers=h,json=p).json();assert 'token' in plan,plan
 with db.transaction() as sess:sess.execute(text("CREATE TRIGGER merge_failure BEFORE INSERT ON history WHEN NEW.event='ZONE_RESTRUCTURED' BEGIN SELECT RAISE(ABORT,'injected'); END"))
 before=state();cmd('restructure',{**p,'preview_token':plan['token']},409);assert state()['layout']==before['layout'];assert v(ident)==next(x for x in before['vehicles'] if x['id']==ident)
 with db.transaction() as sess:sess.execute(text('DROP TRIGGER merge_failure'))
 cmd('restructure',{**p,'preview_token':plan['token']});after=state()
 assert {sl['id'] for zz in after['layout']['zones'] for sl in zz['slots']}==original_slots
 merged=next(x for x in after['layout']['zones'] if x['id']==z['id']);labels=[sl['label'] for sl in merged['slots']];assert len(labels)==len(set(labels))
 # All old preview requests are rejected after another command changed the revision.
 cmd('restructure',{**p,'preview_token':plan['token']},409)
 p={'revision':state()['revision'],'zone_id':z['id'],'mode':'split','axis':'cols','cut':1,'name':'OUTSIDE','x':1900,'y':900}
 assert c.post('/api/layout/preview',headers=h,json=p).status_code==409
 token=c.post('/api/login',json={'username':'worker','password':'test-password-123'}).json()['token']
 assert c.post('/api/layout/preview',headers={'Authorization':'Bearer '+token},json=p).status_code==403
