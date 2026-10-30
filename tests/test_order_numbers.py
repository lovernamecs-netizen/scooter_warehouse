from test_customer_privacy import another,new_customer
import uuid
from concurrent.futures import ThreadPoolExecutor
from test_workflow import env
from server.models import Order

def test_shared_sequence_and_retry(env):
 db,c,h,cmd,state,receive,v,vc,*_=env
 other,worker=another(db);assert c.post('/api/customers/access',headers=h,json={'user_id':other,'allowed':True}).status_code==200
 customer=new_customer(c,h)
 ids=[receive() for _ in range(8)]
 requests=[{'command_id':str(uuid.uuid4()),'action':'assign','payload':{'vehicle_id':ident,'version':v(ident)['version'],'scheduled':state()['today'],'number':'ignored','customer_id':customer}} for ident in ids]
 def run(pair):
  i,req=pair;r=c.post('/api/command',headers=h if i%2==0 else worker,json=req);assert r.status_code==200,r.text
 with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(run,enumerate(requests)))
 assert sorted(v(ident)['assignment']['number'] for ident in ids)==[f'ow{i:03d}' for i in range(1,9)]
 r=c.post('/api/command',headers=h,json=requests[0]);assert r.status_code==200
 ident=receive();vc('assign',ident,{'scheduled':state()['today']});assert v(ident)['assignment']['number']=='ow009'

def test_existing_and_failed_assignment(env):
 db,c,h,cmd,state,receive,v,vc,*_=env
 with db.transaction() as s:s.add(Order(number='OW999',notes='preserve'))
 ident=receive();vc('assign',ident,{'scheduled':'invalid'},422)
 vc('assign',ident,{'scheduled':state()['today']});assert v(ident)['assignment']['number']=='ow1000'
