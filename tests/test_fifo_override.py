import uuid
from test_workflow import env

def test_override_reason_required_and_newer_dispatch(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,*_=env
 old,new=receive(),receive();vc('vehicle_edit',old,{'manufactured_month':'2024-01'});vc('vehicle_edit',new,{'manufactured_month':'2026-09'})
 vc('move',old,{'slot_id':z['slots'][0]['id']});before=v(old)
 p={'number':'OVERRIDE-'+str(uuid.uuid4()),'scheduled':state()['today']}
 vc('assign',new,{**p,'fifo_override_reason':'  '},409)
 vc('assign',new,{**p,'fifo_override_reason':'고객 최신 제작 차량 요청'})
 assert v(old)==before and v(new)['assignment']
 hs=c.get('/api/history/'+new,headers=h).json();e=next(x for x in hs if x['event']=='FIFO_OVERRIDE');assert e['data']['reason']=='고객 최신 제작 차량 요청';assert e['data']['older_candidates'][0]['vehicle_id']==old;assert e['data']['selected_manufactured_month']=='2026-09'
 vc('ubis',new,{'status':'INSTALLED'});vc('finish_work',new);vc('ready',new);vc('dispatch',new,{'confirmed_vin':v(new)['vin']});assert not v(new)['stay_id'];assert v(old)==before

def test_worker_override_and_no_exception_for_normal_fifo(env):
 db,c,h,cmd,state,receive,v,vc,z,*_=env
 old,new=receive(),receive();vc('vehicle_edit',old,{'manufactured_month':'2024-01'});vc('vehicle_edit',new,{'manufactured_month':'2026-01'})
 token=c.post('/api/login',json={'username':'worker','password':'test-password-123'}).json()['token']
 r=c.post('/api/command',headers={'Authorization':'Bearer '+token},json={'command_id':str(uuid.uuid4()),'action':'assign','payload':{'vehicle_id':new,'version':v(new)['version'],'number':'worker-exception','scheduled':state()['today'],'fifo_override_reason':'출고 조건에 맞는 신형 선택'}});assert r.status_code==200,r.text
 vc('assign',old,{'number':'normal','scheduled':state()['today']});hs=c.get('/api/history/'+old,headers=h).json();assert not any(x['event']=='FIFO_OVERRIDE' for x in hs)
