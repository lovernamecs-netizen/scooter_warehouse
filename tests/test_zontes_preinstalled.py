import copy,uuid
import pytest
from sqlalchemy import select
from test_workflow import env
from test_parts_orders import configure,request,complete,dispatch,row
from server.models import Equipment,Outbound

def configured(env):
 get,cmd=configure(env,'ZONTES368G');rules=get()['rules'];rule=rules['models'][env[11]];rule['preinstalled_bracket']=True;rule['defaults']={'B2B':['SC','CUP','MITT'],'B2C':['SC']};cmd('rules',rules=rules);return get,cmd

def assign(env,vid,channel='B2B',**extra):
 return env[7]('assign',vid,{'scheduled':env[4]()['today'],'parts_order':request(channel,**extra)})

@pytest.mark.parametrize('channel,expected',[('B2B',{'SC','CUP','MITT'}),('B2C',{'SC'})])
@pytest.mark.parametrize('choice',['','TOP01','TOP02'])
def test_preinstalled_separate_from_real_work_and_stock(env,channel,expected,choice):
 get,cmd=configured(env);vid=env[5]();v=env[6](vid);assert len(v['equipment'])==1 and v['equipment'][0]['origin']=='FACTORY'
 assign(env,vid,channel,set=choice);v=env[6](vid);expected=expected|({'ST01' if choice=='TOP01' else 'ST02'} if choice else set())
 assert {l['item']['part_id'] for l in v['assignment']['options'] if l['qty']}==expected
 assert all(l['done']==0 for l in v['assignment']['options'])
 assert next(l for l in v['assignment']['parts_order']['lines'] if l['part_id']=='RBZ')['line_id'] is None
 assert row(get,env,'RBZ')['ending']==100
 complete(env,vid);assert row(get,env,'SC')['ending']==100
 cid=str(uuid.uuid4());payload={'vehicle_id':vid,'version':env[6](vid)['version'],'exception_reason':'synthetic','handed':{}}
 first=env[3]('dispatch',payload,cid=cid);assert env[3]('dispatch',payload,cid=cid)==first
 assert row(get,env,'RBZ')['ending']==100
 for part in expected:assert row(get,env,part)['ending']==99
 out=env[1].get('/api/outbound',headers=env[2]).json()[0];assert next(l for l in out['snapshot']['options'] if l['item'].get('part_id')=='RBZ')['origin']=='FACTORY'
 frozen=copy.deepcopy(out);rules=get()['rules'];rules['models'][env[11]]['defaults']['B2B']=['SC'];cmd('rules',rules=rules);assert env[1].get('/api/outbound',headers=env[2]).json()[0]==frozen

def test_resave_and_channel_switch_no_duplicates(env):
 get,_=configured(env);vid=env[5]();assign(env,vid)
 for channel in ['B2C','B2B','B2B']:
  env[7]('parts_plan',vid,{'parts_order':request(channel)})
  a=env[6](vid)['assignment'];ls=[l for l in a['options'] if l['qty']];assert len(ls)==(1 if channel=='B2C' else 3);assert len({l['item']['part_id'] for l in ls})==len(ls)
 assert len([e for e in env[6](vid)['equipment'] if e['item'].get('part_id')=='RBZ'])==1

def test_replacement_and_extra_delivery_count_actual_stock(env):
 get,_=configured(env);vid=env[5]();assign(env,vid,sources={'RBZ':'WAREHOUSE'},deliveries=[{'item_id':'RBZ','qty':2}]);complete(env,vid)
 assert len([e for e in env[6](vid)['equipment'] if e['item'].get('part_id')=='RBZ'])==1
 dispatch(env,vid);assert row(get,env,'RBZ')['ending']==97

def test_extra_delivery_keeps_factory_rack(env):
 get,_=configured(env);vid=env[5]();assign(env,vid,deliveries=[{'item_id':'RBZ','qty':2}]);complete(env,vid);dispatch(env,vid);assert row(get,env,'RBZ')['ending']==98

def test_old_completed_factory_work_is_not_reset(env):
 get,cmd=configure(env,'ZONTES368G');vid=env[5]();assign(env,vid,'B2C');complete(env,vid);before=env[6](vid)
 rules=get()['rules'];rules['models'][env[11]]['preinstalled_bracket']=True;cmd('rules',rules=rules)
 env[7]('parts_plan',vid,{'parts_order':request('B2C')},422);assert env[6](vid)==before

def test_used_has_no_automatic_preinstalled(env):
 get,_=configured(env);vid=env[5]('USED');assert env[6](vid)['equipment']==[];assign(env,vid,'B2C',set='TOP01');a=env[6](vid)['assignment'];assert any(l['item']['part_id']=='RBZ' for l in a['options']);assert not any(l.get('preinstalled') for l in a['parts_order']['lines'])


def test_preinstalled_selection_is_idempotent_and_not_required_work(env):
 get,_=configured(env);vid=env[5]();assign(env,vid,install=['RBZ'],set='TOP01');complete(env,vid)
 assert not any(l['item']['part_id']=='RBZ' for l in env[6](vid)['assignment']['options'])
 env[7]('ubis',vid,{'status':'INSTALLED'});env[7]('finish_work',vid);env[7]('ready',vid)
 env[7]('dispatch',vid,{'handed':{}});assert row(get,env,'RBZ')['ending']==100


def test_topbox_bracket_delivery_retains_factory_and_frozen_closing(env):
 get,cmd=configured(env);vid=env[5]();assign(env,vid,set='TOP01',set_modes={'component':'DELIVERY'});complete(env,vid);dispatch(env,vid)
 out=env[1].get('/api/outbound',headers=env[2]).json()[0];lines=out['snapshot']['parts_order']['lines']
 assert len([l for l in lines if l['part_id']=='RBZ'])==2
 assert row(get,env,'RBZ')['ending']==99
 cmd('close',day=env[4]()['today'],checked=True)
 from server.parts import PartsBook
 with env[0].transaction() as session:before=copy.deepcopy(session.get(PartsBook,1).data['closings'])
 rules=get()['rules'];rules['models'][env[11]]['defaults']['B2B']=['SC'];cmd('rules',rules=rules)
 with env[0].transaction() as session:assert session.get(PartsBook,1).data['closings']==before
 assert env[1].get('/api/outbound',headers=env[2]).json()[0]==out
