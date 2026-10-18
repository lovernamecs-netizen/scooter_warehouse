import uuid
from test_workflow import env

def test_dispatch_without_vin_confirmation_preserves_snapshot(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,*_=env
 ident=receive();vc('move',ident,{'slot_id':z['slots'][0]['id']});vc('ubis',ident,{'status':'INSTALLED'})
 vc('assign',ident,{'number':str(uuid.uuid4()),'scheduled':state()['today'],'options':[{'master_id':opt,'qty':1}],'items':[{'master_id':item,'qty':2}]})
 a=v(ident)['assignment'];vc('work_line',ident,{'kind':'options','line_id':a['options'][0]['id'],'done':1});vc('work_line',ident,{'kind':'items','line_id':a['items'][0]['id'],'done':2});vc('finish_work',ident);vc('ready',ident)
 cid=str(uuid.uuid4());payload={'vehicle_id':ident,'version':v(ident)['version'],'handed':{a['items'][0]['id']:2}}
 cmd('dispatch',payload,cid=cid);cmd('dispatch',payload,cid=cid)
 assert not v(ident)['stay_id'] and not v(ident)['location']
 outs=[x for x in c.get('/api/outbound',headers=h).json() if x['vehicle_id']==ident];assert len(outs)==1
 assert outs[0]['snapshot']['options'][0]['qty']==1 and outs[0]['snapshot']['items'][0]['qty']==2
 assert outs[0]['snapshot']['vehicle']['vin']==v(ident)['vin']
 report=c.get('/api/report/'+state()['today'],headers=h).json();assert report['dispatched']==1
 assert any(x['event']=='DISPATCHED' for x in c.get('/api/history/'+ident,headers=h).json())
