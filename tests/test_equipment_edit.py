import copy,uuid
from sqlalchemy import select
from test_workflow import env
from test_parts_orders import configure,request,complete,dispatch,row
from server.models import Equipment,OptionLine

def setup_cancelled(env):
 get,_=configure(env,'HUSKY');vid=env[5]()
 env[7]('assign',vid,{'scheduled':env[4]()['today'],'parts_order':request('B2C')});complete(env,vid)
 original=env[6](vid)['assignment'];equipment=next(e for e in env[6](vid)['equipment'] if e['item'].get('part_id')=='SC')
 env[7]('cancel_order',vid,{'reason':'synthetic cancellation'})
 env[7]('assign',vid,{'scheduled':env[4]()['today'],'parts_order':request('B2C',omit_lines=['SC:INSTALL'])})
 return get,vid,equipment,original

def action(env,vid,e,mode,**kw):return env[7]('equipment_edit',vid,{'equipment_id':e['id'],'mode':mode,'reason':'실제 상태 확인','confirmed':True,**kw})

def test_carry_cancelled_installation_posts_once(env):
 get,vid,e,old=setup_cancelled(env);v=env[6](vid);assert next(x for x in v['equipment'] if x['id']==e['id'])['can_carry']
 complete(env,vid);dispatch(env,vid,422)
 cid=str(uuid.uuid4());payload={'vehicle_id':vid,'version':env[6](vid)['version'],'equipment_id':e['id'],'mode':'carry','reason':'실제 장착 유지','confirmed':True}
 first=env[3]('equipment_edit',payload,cid=cid);assert env[3]('equipment_edit',payload,cid=cid)==first
 v=env[6](vid);sc=next(l for l in v['assignment']['options'] if l['item'].get('part_id')=='SC');assert sc['done']==1 and sc['qty']==1
 assert not v['assignment']['ready'];assert len([x for x in v['equipment'] if x['item'].get('part_id')=='SC'])==1;assert row(get,env,'SC')['ending']==100
 with env[0].transaction() as s:assert s.get(OptionLine,e['line_id']).done==1 and s.get(Equipment,e['id']).qty==0
 complete(env,vid);dispatch(env,vid);assert row(get,env,'SC')['ending']==99
 frozen=copy.deepcopy(env[1].get('/api/outbound',headers=env[2]).json())
 env[7]('reenter',vid,{'reason':'test return'});env[7]('equipment_edit',vid,{'equipment_id':env[6](vid)['equipment'][0]['id'],'mode':'correct','reason':'bad','confirmed':True},409)
 assert env[1].get('/api/outbound',headers=env[2]).json()==frozen

def test_correct_cancelled_then_replan(env):
 get,vid,e,old=setup_cancelled(env);action(env,vid,e,'correct');env[7]('parts_plan',vid,{'parts_order':request('B2C')})
 sc=next(l for l in env[6](vid)['assignment']['options'] if l['item'].get('part_id')=='SC');assert sc['done']==0;assert row(get,env,'SC')['ending']==100
 complete(env,vid);dispatch(env,vid);assert row(get,env,'SC')['ending']==99

def test_correct_current_then_exclude(env):
 get,vid,e,old=setup_cancelled(env);action(env,vid,e,'carry');current=next(e for e in env[6](vid)['equipment'] if e['item'].get('part_id')=='SC');action(env,vid,current,'correct')
 env[7]('parts_plan',vid,{'parts_order':request('B2C',omit_lines=['SC:INSTALL'])});complete(env,vid);dispatch(env,vid);assert row(get,env,'SC')['ending']==100

def test_correction_requires_confirmation_reason_and_ownership(env):
 get,vid,e,old=setup_cancelled(env);before=env[6](vid)
 for extra in [{'confirmed':False},{'reason':''}]:env[7]('equipment_edit',vid,{'equipment_id':e['id'],'mode':'correct','reason':'reason','confirmed':True,**extra},422)
 other=env[5]();env[7]('equipment_edit',other,{'equipment_id':e['id'],'mode':'correct','reason':'reason','confirmed':True},422);assert env[6](vid)==before

def test_carry_conflict_is_atomic(env):
 get,vid,e,old=setup_cancelled(env);v=env[6](vid);request_bad=copy.deepcopy(v['assignment']['parts_order']['request']);request_bad['sources']={'SC':'EXISTING'};request_bad['reason']='legacy';request_bad['omit_lines']=[]
 env[7]('parts_plan',vid,{'parts_order':request_bad});before=env[6](vid)
 env[7]('equipment_edit',vid,{'equipment_id':e['id'],'mode':'carry','reason':'confirmed','confirmed':True},409);assert env[6](vid)==before


def test_carry_build_failure_rolls_back_equipment(env):
 get,vid,e,old=setup_cancelled(env)
 from server.parts import PartsBook
 with env[0].transaction() as session:
  book=session.get(PartsBook,1);data=copy.deepcopy(book.data);next(i for i in data['items'] if i['id']=='SC')['active']=False;book.data=data
 before=env[6](vid)
 env[7]('equipment_edit',vid,{'equipment_id':e['id'],'mode':'carry','reason':'confirmed','confirmed':True},422)
 assert env[6](vid)==before

def test_worker_allowed_viewer_forbidden(env):
 get,vid,e,old=setup_cancelled(env)
 from server.models import User
 from server.security import hash_password
 with env[0].transaction() as session:session.add(User(username='readonly',password=hash_password('test-password-123'),role='viewer'))
 client=env[1];token=client.post('/api/login',json={'username':'readonly','password':'test-password-123'}).json()['token'];headers={'Authorization':'Bearer '+token}
 body={'command_id':str(uuid.uuid4()),'action':'equipment_edit','payload':{'vehicle_id':vid,'version':env[6](vid)['version'],'equipment_id':e['id'],'mode':'carry','reason':'confirmed','confirmed':True}}
 assert client.post('/api/command',headers=headers,json=body).status_code==403
 readonly=next(v for v in client.get('/api/state',headers=headers).json()['vehicles'] if v['id']==vid);assert not any(e['can_correct'] or e['can_carry'] for e in readonly['equipment'])
 token=client.post('/api/login',json={'username':'worker','password':'test-password-123'}).json()['token'];assert client.post('/api/command',headers={'Authorization':'Bearer '+token},json=body).status_code==200
