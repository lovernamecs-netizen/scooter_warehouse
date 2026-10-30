import base64,io,uuid,subprocess,sys,os
from pathlib import Path
from PIL import Image
from sqlalchemy import select
from test_workflow import env
from server.models import Setting,User
from server.security import hash_password

def complete_profile(day):return {'mileage':12345,'exterior':'왼쪽 카울 생활 흠집 확인','pad_front':80,'pad_rear':65,'tire_front':70,'tire_rear':60,'oil_changed':True,'oil_date':day,'equipment_checked':True,'repairs_done':True,'washed':True,'description':'보수 및 엔진오일 교환 완료'}
def photo():
 b=io.BytesIO();Image.new('RGB',(20,20),'white').save(b,format='JPEG');return base64.b64encode(b.getvalue()).decode()

def test_used_reconditioning_and_photo_lifecycle(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,*_=env;ident=receive('USED');before=v(ident)
 assert before['used_stock']['status']=='점검 미등록'
 vc('assign',ident,{'number':str(uuid.uuid4()),'scheduled':state()['today']})
 vc('finish_work',ident,{},422)
 profile=complete_profile(state()['today']);bad={**profile,'oil_changed':False}
 vc('used_profile',ident,{'profile':bad,'complete':True});assert v(ident)['used_stock']['ready']
 vc('used_profile',ident,{'profile':bad});assert not v(ident)['used_stock']['ready']
 vc('used_profile',ident,{'profile':{**profile,'tire_front':101},'complete':True},422)
 vc('used_profile',ident,{'profile':profile,'complete':True});assert v(ident)['used_stock']['ready']
 assert v(ident)['vin']==before['vin'] and v(ident)['model_id']==before['model_id']
 for view in ['front','rear','left','right','cockpit','perspective']:vc('used_photo',ident,{'view':view,'jpeg':photo()})
 p=c.get('/api/used/'+ident,headers=h).json();assert p['publication_ready'] and len(p['photos'])==6
 assert 'jpeg' not in c.get('/api/state',headers=h).text
 vc('used_photo',ident,{'view':'front','jpeg':'not-base64'},422)
 vc('used_photo',ident,{'view':'invalid','jpeg':photo()},422)
 vc('finish_work',ident);vc('ready',ident);vc('dispatch',ident)
 out=c.get('/api/outbound',headers=h).json()[0];assert out['snapshot']['vehicle']['used_reconditioning']['mileage']==12345
 p=c.get('/api/used/'+ident,headers=h).json();assert not p['editable'] and len(p['photos'])==6
 vc('used_photo',ident,{'view':'front','remove':True},409)
 vc('reenter',ident,{'reason':'고객 반납'})
 p=c.get('/api/used/'+ident,headers=h).json();assert p['profile']=={} and p['photos']=={} and not p['ready']
 with db.transaction() as s:assert len(list(s.scalars(select(Setting).where(Setting.key.like('used_photo:%')))))==6

def test_photo_access_conflict_equipment_invalidation_and_backup(env,tmp_path):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,*_=env;ident=receive('USED');profile=complete_profile(state()['today'])
 vc('used_profile',ident,{'profile':profile,'complete':True});oldversion=v(ident)['version']
 vc('equipment',ident,{'master_id':opt,'qty':1});assert not v(ident)['used_stock']['ready']
 cmd('used_profile',{'vehicle_id':ident,'version':oldversion,'profile':profile,'complete':True},409)
 with db.transaction() as s:s.add(User(username='viewer_test',password=hash_password('test-password-123'),role='viewer'))
 token=c.post('/api/login',json={'username':'viewer_test','password':'test-password-123'}).json()['token'];vh={'Authorization':'Bearer '+token}
 assert c.get('/api/used/'+ident,headers=vh).status_code==200
 assert c.get('/api/used/'+ident).status_code==401
 result=c.post('/api/command',headers=vh,json={'command_id':str(uuid.uuid4()),'action':'used_photo','payload':{'vehicle_id':ident,'version':v(ident)['version'],'view':'front','jpeg':photo()}});assert result.status_code==403
 vc('used_media',ident,{'category':'intake','key':'whole','original':photo(),'preview':photo()});vc('used_photo',ident,{'view':'front','jpeg':photo()});root=Path(__file__).resolve().parents[1];backup=tmp_path/'used.swh';target='sqlite:///'+str(tmp_path/'restored.db')
 for action,url in [('backup',str(db.engine.url)),('restore',target)]:
  r=subprocess.run([sys.executable,'-m','server.cli',action,'--file',str(backup)],cwd=root,env=dict(os.environ,PYTHONUTF8='1',DATABASE_URL=url,WAREHOUSE_BACKUP_PASSWORD='used-backup-password-123'),capture_output=True,text=True,encoding='utf-8');assert r.returncode==0,r.stdout+r.stderr
 from server.db import Database
 restored=Database(target);restored.init()
 with restored.transaction() as s:
  assert s.scalar(select(Setting).where(Setting.key.like('used_photo:%'))).value['jpeg']==photo()
  from server.photo_store import read_file
  assert read_file(s,s.scalar(select(Setting).where(Setting.key.like('used_media:%'))).value)[0]==base64.b64decode(photo())


def test_new_vehicle_customer_return_becomes_used_without_old_snapshot_change(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,*_=env;ident=receive()
 vc('ubis',ident,{'status':'INSTALLED'});vc('assign',ident,{'number':str(uuid.uuid4()),'scheduled':state()['today']});vc('finish_work',ident);vc('ready',ident);vc('dispatch',ident)
 out=next(x for x in c.get('/api/outbound',headers=h).json() if x['vehicle_id']==ident)
 cmd('adjust_outbound',{'vehicle_id':ident,'outbound_id':out['id'],'version':v(ident)['version'],'kind':'RETURN','reason':'사용 후 고객 반납'})
 assert v(ident)['kind']=='USED'
 assert c.get('/api/used/'+ident,headers=h).json()['profile']=={}
 assert next(x for x in c.get('/api/outbound',headers=h).json() if x['id']==out['id'])['snapshot']==out['snapshot']


def test_incomplete_used_profile_can_complete_and_dispatch_without_fabricating_work(env):
 db,c,h,cmd,state,receive,v,vc,*_=env
 ident=receive('USED')
 profile={'mileage':None,'exterior':'','oil_changed':False,'equipment_checked':False,'repairs_done':False,'washed':False,'damage':{'left':{'status':'damaged','note':'현 상태 출고'}}}
 vc('used_profile',ident,{'profile':profile,'complete':True})
 assert v(ident)['used_stock']['ready']
 assert c.get('/api/used/'+ident,headers=h).json()['ready']
 vc('assign',ident,{'scheduled':state()['today']})
 vc('finish_work',ident);vc('ready',ident);vc('dispatch',ident)
 out=next(x for x in c.get('/api/outbound',headers=h).json() if x['vehicle_id']==ident)
 saved=out['snapshot']['vehicle']['used_reconditioning']
 assert saved['ready'] and not saved['repairs_done'] and not saved['oil_changed'] and not saved['washed']
 assert saved['mileage'] is None and saved['damage']['left']['status']=='damaged'
 assert out['snapshot']['vehicle']['vin']==v(ident)['vin']


def test_used_card_delete_owner_only_preserves_history_and_profile(env):
 from test_customer_privacy import another
 from server.models import Vehicle,Stay
 db,c,h,cmd,state,receive,v,vc,*_=env
 ident=receive('USED');vc('used_profile',ident,{'profile':complete_profile(state()['today'])})
 st=v(ident)['stay_id'];saved=c.get('/api/used/'+ident,headers=h).json()['profile']
 for role in ['admin','worker','viewer']:
  _,other=another(db,role)
  for action in ['delete_vehicle','archive_vehicle']:
   r=c.post('/api/command',headers=other,json={'command_id':str(uuid.uuid4()),'action':action,'payload':{'vehicle_id':ident,'version':v(ident)['version'],'confirmation':'삭제','confirmed_vin':v(ident)['vin'],'reason':'합성 삭제'}})
   assert r.status_code==403
 assert v(ident)['stay_id']==st
 vc('delete_vehicle',ident,{'confirmation':'삭제','reason':'중복 입력 정리'})
 assert v(ident)['archived'] and v(ident)['stay_id'] is None
 with db.read() as session:
  assert session.get(Vehicle,ident) and session.get(Stay,st)
  assert session.get(Setting,'used_profile:'+st).value==saved
 history=c.get('/api/history/'+ident,headers=h).json();assert history[-1]['event']=='DELETED'
 assert not any(x['vehicle_id']==ident for x in c.get('/api/outbound',headers=h).json())
