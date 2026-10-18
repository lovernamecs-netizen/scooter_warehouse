import uuid
from sqlalchemy import select
from test_workflow import env
from server.models import Master,Setting

def test_catalog_idempotent_and_vehicle_preserved(env):
 db,c,h,cmd,state,receive,v,vc,z,*_=env;ident=receive();before=v(ident);db.init();db.init();assert v(ident)==before
 for kind,name in [('item','겨울토시'),('item','여름토시'),('option','짐대')]:assert len([x for x in state()['masters'] if x['kind']==kind and x['name']==name])==1

def test_common_staging_without_physical_place(env):
 db,c,h,cmd,state,receive,v,vc,z,*_=env;ident=receive();vc('ubis',ident,{'status':'INSTALLED'});vc('assign',ident,{'number':str(uuid.uuid4()),'scheduled':state()['today']});vc('finish_work',ident);vc('ready',ident,{'warehouse_id':'nonexistent-ignored'});loc=v(ident)['location'];assert loc['kind']=='DISPATCH_STAGING' and loc['warehouse_id'] is None and loc['slot_id'] is None
 assert v(ident)['stay_id'];vc('move',ident,{'slot_id':z['slots'][0]['id']});assert not v(ident)['assignment']['ready']

def test_box_rack_separate_completion_and_outbound(env):
 db,c,h,cmd,state,receive,v,vc,z,*_=env;box=cmd('master',{'kind':'option','name':'EPP 박스','detail':{'category':'장착품'}})['id'];ident=receive();vc('ubis',ident,{'status':'INSTALLED'});vc('assign',ident,{'number':str(uuid.uuid4()),'scheduled':state()['today'],'options':[{'master_id':box,'qty':1}]});opts=v(ident)['assignment']['options'];assert len(opts)==2;bl=next(x for x in opts if x['master_id']==box);rl=next(x for x in opts if x['item']['name']=='짐대');assert rl['qty']==1 and rl['required'];vc('work_line',ident,{'kind':'options','line_id':bl['id'],'done':1});vc('finish_work',ident,{},422);vc('work_line',ident,{'kind':'options','line_id':rl['id'],'done':1});vc('finish_work',ident);vc('ready',ident);vc('dispatch',ident,{'confirmed_vin':v(ident)['vin']});out=c.get('/api/outbound',headers=h).json()[0];assert {l['item']['name'] for l in out['snapshot']['options']}=={'EPP 박스','짐대'}
 report=c.get('/api/report/'+state()['today'],headers=h).json();assert report['new_options']['짐대']==1 and report['new_options']['EPP 박스']==1

def test_existing_rack_no_double_install(env):
 db,c,h,cmd,state,receive,v,vc,z,*_=env;box=cmd('master',{'kind':'option','name':'탑박스 85L','detail':{}})['id'];rack=next(m['id'] for m in state()['masters'] if m['name']=='짐대');ident=receive('USED');vc('equipment',ident,{'master_id':rack,'qty':1});vc('assign',ident,{'number':str(uuid.uuid4()),'scheduled':state()['today'],'options':[{'master_id':box,'qty':1}]});assert len(v(ident)['assignment']['options'])==1
