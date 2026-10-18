import base64,io,zipfile,uuid
from unittest.mock import patch
from PIL import Image
from test_workflow import env
from test_used_stock import complete_profile

def png():
 out=io.BytesIO();Image.new('RGB',(32,24),'red').save(out,'PNG');return out.getvalue()

def test_registration_atomic_receipt_and_profile(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,model,color=env
 start=len(state()['vehicles']);profile={**complete_profile(state()['today']),'mileage':-1}
 base={'model_id':model,'color_id':color,'year':2026,'kind':'USED'}
 cmd('receive',{**base,'used_profile':profile},422);assert len(state()['vehicles'])==start
 profile.update(mileage=12000,equipment_notes='사제 짐대, 열선그립')
 one=cmd('receive',{**base,'used_profile':profile})['vehicle_id'];two=cmd('receive',base)['vehicle_id']
 first=c.get('/api/used/'+one,headers=h).json();second=c.get('/api/used/'+two,headers=h).json()
 assert first['registration']!=second['registration'];assert first['registration'].startswith('USED-')
 assert first['profile']['equipment_notes']=='사제 짐대, 열선그립'
 old=v(one)['plate'];vc('used_record',one,{'vehicle':{'plate':'변경시도'},'profile':{**profile,'tire_front':120}},422);assert v(one)['plate']==old
 vc('used_record',one,{'vehicle':{'plate':'서울가1234'},'profile':profile,'complete':True});assert v(one)['used_stock']['ready']

def test_original_download_zip_roles_and_stay_isolation(env):
 from server.models import User
 from server.security import hash_password
 db,c,h,cmd,state,receive,v,vc,*_=env;one=receive('USED');two=receive('USED');raw=png();encoded=base64.b64encode(raw).decode()
 for category,key in [('intake','plate'),('damage','left'),('wear','pad_front'),('product','front')]:vc('used_media',one,{'category':category,'key':key,'original':encoded,'preview':encoded})
 page=c.get('/api/used/'+one,headers=h).json();assert len(page['media'])==4
 assert 'original' not in page['media'][0] and 'preview' not in page['media'][0]
 assert encoded not in c.get('/api/state',headers=h).text
 ident=page['media'][0]['id'];url='/api/used/'+one+'/photos/'+ident
 assert c.get(url,headers=h).content==raw;assert c.get('/api/used/'+two+'/photos/'+ident,headers=h).status_code==404;assert c.get(url).status_code==401
 with zipfile.ZipFile(io.BytesIO(c.get('/api/used/'+one+'/download?category=product',headers=h).content)) as z:
  assert len(z.namelist())==1 and z.namelist()[0].startswith('product/');assert z.read(z.namelist()[0])==raw
 with db.transaction() as s:s.add(User(username='readonly',password=hash_password('test-password-123'),role='viewer'))
 token=c.post('/api/login',json={'username':'readonly','password':'test-password-123'}).json()['token'];viewer={'Authorization':'Bearer '+token}
 assert c.get(url,headers=viewer).status_code==200
 r=c.post('/api/command',headers=viewer,json={'command_id':str(uuid.uuid4()),'action':'used_media','payload':{'vehicle_id':one,'version':v(one)['version'],'category':'product','key':'front','original':encoded,'preview':encoded}});assert r.status_code==403
 vc('used_media',one,{'category':'damage','key':'bad','original':encoded,'preview':encoded},422)
 vc('used_media',one,{'category':'product','key':'front','original':encoded,'preview':encoded});p=c.get('/api/used/'+one,headers=h).json();assert len([x for x in p['media'] if x['category']=='product'])==1

def test_damage_validation_and_ready_gate(env):
 db,c,h,cmd,state,receive,v,vc,*_=env;ident=receive('USED');p=complete_profile(state()['today'])
 vc('used_profile',ident,{'profile':{**p,'washed':False},'complete':True},422)
 vc('used_profile',ident,{'profile':{**p,'damage':{'left':{'status':'damaged','note':'카울 흠집'}}}})
 assert c.get('/api/used/'+ident,headers=h).json()['profile']['damage']['left']['note']=='카울 흠집'
 vc('used_profile',ident,{'profile':{**p,'damage':{'unknown':{'status':'normal'}}}},422)

def test_ocr_requires_permission_and_reports_missing_engine(env):
 db,c,h,*_=env
 with patch('server.vin_ocr.Path.is_file',return_value=False):
  r=c.post('/api/vin/ocr',headers=h,json={'image':base64.b64encode(png()).decode()});assert r.status_code==503
 assert c.post('/api/vin/ocr',json={'image':''}).status_code==401
