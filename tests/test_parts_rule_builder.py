import copy,uuid
import pytest
from test_workflow import env
from test_parts_orders import configure,assigned,request
from server.parts import PartsBook
from server.parts_orders import build

def test_rule_item_lifecycle_and_frozen_order(env):
    vid,get,cmd=assigned(env,request('B2C'))
    before=copy.deepcopy(env[6](vid)['assignment'])
    cmd('item',item={'code':'NEWCARD','name':'새 품목','purpose':'INSTALL'})
    new=next(i for i in get()['items'] if i['code']=='NEWCARD')
    rules=get()['rules'];rules['defaults']['B2C'].append(new['id']);cmd('rules',rules=rules)
    new.update(code='RENAMED',name='수정된 품목');cmd('item',item=new)
    assert new['id'] in get()['rules']['defaults']['B2C']
    with env[0].transaction() as s:
        plan=build(s.get(PartsBook,1).data,env[11],'NEW',{'channel':'B2C','purposes':{'SC':'INSTALL'}})
    assert next(l for l in plan['lines'] if l['part_id']==new['id'])['item']['name']=='수정된 품목'
    assert env[6](vid)['assignment']==before
    new['active']=False;cmd('item',item=new)
    rev=get()['revision'];cmd('rules',422,rules=get()['rules']);assert get()['revision']==rev
    rules=get()['rules'];rules['defaults']['B2C'].remove(new['id']);cmd('rules',rules=rules)
    assert env[6](vid)['assignment']==before

def test_modes_effective_and_explicit_override(env):
    get,cmd=configure(env)
    rules=get()['rules'];rules['default_purposes']={'B2C':{'SC':'DELIVERY'}};rules['sets']['EPP']['modes']={'item':'DELIVERY','component':'INSTALL'};cmd('rules',rules=rules)
    with env[0].transaction() as s:
        data=s.get(PartsBook,1).data
        plan=build(data,env[11],'NEW',{'channel':'B2C','set':'EPP'})
        assert next(l for l in plan['lines'] if l['part_id']=='SC')['purpose']=='DELIVERY'
        assert next(l for l in plan['lines'] if l['part_id']=='SE')['purpose']=='DELIVERY'
        plan=build(data,env[11],'NEW',{'channel':'B2C','set':'EPP','purposes':{'SC':'INSTALL'},'set_modes':{'item':'INSTALL'}})
        assert all(l['purpose']=='INSTALL' for l in plan['lines'])

@pytest.mark.parametrize('bad',[[],None,{'B2C':[]},{'B2C':{'SC':'BAD'}}])
def test_invalid_modes_atomic(env,bad):
    get,cmd=configure(env);before=get()['rules'];rules=copy.deepcopy(before);rules['default_purposes']=bad;cmd('rules',422,rules=rules);assert get()['rules']==before

def test_rules_stale_and_replay(env):
    get,cmd=configure(env);rules=get()['rules'];body={'action':'rules','rules':rules,'revision':get()['revision'],'request_id':str(uuid.uuid4())}
    c,h=env[1:3];first=c.post('/api/parts/command',headers=h,json=body);assert first.status_code==200
    assert c.post('/api/parts/command',headers=h,json=body).json()==first.json()
    body['request_id']=str(uuid.uuid4());assert c.post('/api/parts/command',headers=h,json=body).status_code==409

def test_worker_cannot_change_rules(env):
    get,cmd=configure(env)
    env[3]('user',{'username':'rule-worker','password':'Worker-Test-123','role':'worker','active':True})
    token=env[1].post('/api/login',json={'username':'rule-worker','password':'Worker-Test-123'}).json()['token']
    before=get()['rules']
    result=env[1].post('/api/parts/command',headers={'Authorization':'Bearer '+token},json={'action':'rules','rules':before,'revision':get()['revision'],'request_id':str(uuid.uuid4())})
    assert result.status_code==403 and get()['rules']==before
