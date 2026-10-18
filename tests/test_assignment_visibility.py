import uuid
from test_workflow import env

def test_other_worker_assignment_and_cancel_visible_without_move(env):
 db,c,h,cmd,state,receive,v,vc,z,*_=env;vid=receive();vc('move',vid,{'slot_id':z['slots'][0]['id']});location=v(vid)['location'];revision=state()['revision']
 token=c.post('/api/login',json={'username':'worker','password':'test-password-123'}).json()['token'];wh={'Authorization':'Bearer '+token}
 r=c.post('/api/command',headers=wh,json={'command_id':str(uuid.uuid4()),'action':'assign','payload':{'vehicle_id':vid,'version':v(vid)['version'],'number':'TEAM-ORDER','scheduled':state()['today']}});assert r.status_code==200,r.text
 assert state()['revision']>revision and v(vid)['assignment']['number']=='ow001';assert v(vid)['location']==location
 vc('cancel_order',vid,{'reason':'주문 변경'});assert v(vid)['assignment'] is None;assert v(vid)['location']==location
