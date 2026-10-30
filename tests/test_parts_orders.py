import copy
import uuid
import pytest
from sqlalchemy import select
from test_workflow import env
from test_parts import setup
from server.parts import PartsBook
from server.parts_orders import build, TEMPLATES
from server.models import Outbound, Assignment, Setting

def configure(env,template='PCX',stock=True):
    db,c,h,get,cmd,base,prev=setup(env)
    if stock:base('2020-01-01',100)
    data=get();rules=data['rules'];rules['models'][env[11]]=copy.deepcopy(TEMPLATES[template]);cmd('rules',rules=rules)
    return get,cmd

def request(channel='B2B',**extra):
    return {'channel':channel,'purposes':{'SC':'INSTALL','CUP':'DELIVERY','WPCX_0':'INSTALL','WNMAX_1':'INSTALL','WPCX_1':'INSTALL'},**extra}

def assigned(env,p=None,template='PCX',stock=True,kind='NEW'):
    get,cmd=configure(env,template,stock);vid=env[5](kind)
    env[7]('assign',vid,{'number':str(uuid.uuid4()),'scheduled':env[4]()['today'],'parts_order':p or request()})
    return vid,get,cmd

def complete(env,vid):
    for kind in ['options','items']:
        for l in env[6](vid)['assignment'][kind]:env[7]('work_line',vid,{'kind':kind,'line_id':l['id'],'done':l['qty']})

def dispatch(env,vid,status=200,**extra):
    a=env[6](vid)['assignment'];return env[7]('dispatch',vid,{'exception_reason':'격리 테스트 미완료 승인','handed':{l['id']:l['done'] for l in a['items']},**extra},status)

def row(get,env,key):return next(r for r in get(env[4]()['today'])['report']['rows'] if r['id']==key)

@pytest.mark.parametrize('template,channel,expected',[
    ('PCX','B2B',{'SC','CUP','MITT','WPCX_0'}),('NMAX','B2B',{'SC','CUP','MITT','WNMAX_1'}),
    ('PCX','B2C',{'SC'}),('NMAX','B2C',{'SC'})])
def test_defaults(env,template,channel,expected):
    vid,get,_=assigned(env,request(channel),template)
    plan=env[6](vid)['assignment']['parts_order'];assert {l['part_id'] for l in plan['lines']}==expected
    assert row(get,env,'SC')['ending']==100

@pytest.mark.parametrize('template,choice,component',[
    ('PCX','EPP','SSP'),('NMAX','EPP','SSN'),('PCX','TOP01','RBP'),('NMAX','TOP02','RBN'),
    ('FORZA350','TOP01','RBF'),('XMAX','TOP01','RBX'),('ADV350','TOP02','RBA')])
def test_sets_and_dedup(env,template,choice,component):
    vid,_,_=assigned(env,request(set=choice,install=[component]),template)
    ls=env[6](vid)['assignment']['parts_order']['lines'];assert len([r for r in ls if r['part_id']==component])==1
    assert not any(l['item']['name']=='짐대' for l in ls)

def test_atomic_actual_dispatch_retry_void(env):
    vid,get,_=assigned(env,request(set='EPP',deliveries=[{'item_id':'SC','qty':2}]))
    complete(env,vid);a=env[6](vid)['assignment'];cid=str(uuid.uuid4());payload={'vehicle_id':vid,'version':env[6](vid)['version'],'exception_reason':'테스트','handed':{l['id']:l['done'] for l in a['items']}}
    result=env[3]('dispatch',payload,cid=cid);assert env[3]('dispatch',payload,cid=cid)==result
    assert row(get,env,'SC')['ending']==97
    out=env[1].get('/api/outbound',headers=env[2]).json()[0]
    assert out['snapshot']['parts_order']['channel']=='B2B'
    env[3]('adjust_outbound',{'outbound_id':out['id'],'version':env[6](vid)['version'],'kind':'VOID','reason':'오확정'})
    assert row(get,env,'SC')['ending']==100
    assert get(env[4]()['today'])['parts_daily']['counts'].get('B2B',0)==0
    env[3]('adjust_outbound',{'outbound_id':out['id'],'version':env[6](vid)['version'],'kind':'VOID','reason':'중복'},status=409)

def test_shortage_rollback_then_exception(env):
    vid,get,cmd=assigned(env,stock=False);complete(env,vid);dispatch(env,vid,422)
    assert env[6](vid)['stay_id'] and env[6](vid)['assignment']
    assert env[1].get('/api/outbound',headers=env[2]).json()==[]
    assert not any(e.get('auto') for e in get(env[4]()['today'])['report']['entries'])
    dispatch(env,vid,stock_exception_reason='관리자 실사 예정')
    assert row(get,env,'SC')['ending'] is None

def test_incomplete_not_consumed(env):
    vid,get,_=assigned(env);dispatch(env,vid);assert row(get,env,'SC')['ending']==100

@pytest.mark.parametrize('template,part', [('ZONTES368G','RBZ'),('HUSKY',None)])
def test_factory_confirmation_no_stock(env,template,part):
    vid,get,_=assigned(env,request(set='TOP01'),template);complete(env,vid);dispatch(env,vid)
    result=get(env[4]()['today']);assert not any(i['code']=='RBH' for i in result['items'])
    assert any(r['source']=='FACTORY' for r in result['parts_daily']['usage'])
    if part:assert row(get,env,part)['ending']==100

def test_factory_override_and_used(env):
    vid,get,_=assigned(env,request(set='TOP01',sources={'RBZ':'WAREHOUSE'}),'ZONTES368G');complete(env,vid);dispatch(env,vid);assert row(get,env,'RBZ')['ending']==99
    vid2=env[5]('USED');env[7]('assign',vid2,{'number':str(uuid.uuid4()),'scheduled':env[4]()['today'],'parts_order':request()});assert not any(r['source']=='FACTORY' for r in env[6](vid2)['assignment']['parts_order']['lines'])

def test_recalculate_completed_guard(env):
    vid,_,_=assigned(env,request(set='EPP'));complete(env,vid)
    env[7]('parts_plan',vid,{'parts_order':request(set='TOP01')},422)
    assert env[6](vid)['assignment']['parts_order']['request']['set']=='EPP'

def test_return_and_correction_preserve_snapshot(env):
    vid,get,cmd=assigned(env,template='FORZA350');complete(env,vid);dispatch(env,vid)
    out=env[1].get('/api/outbound',headers=env[2]).json()[0];original=copy.deepcopy(out['snapshot']);d=out['day']
    cmd('close',day=d,checked=True)
    env[3]('adjust_outbound',{'outbound_id':out['id'],'version':env[6](vid)['version'],'kind':'CORRECTION','reason':'전달 수량 정정','detail':{'category':'items','name':'CUP','delta':1,'line_key':'CUP:DELIVERY'}})
    assert row(get,env,'CUP')['ending']==98;assert get(d)['report']['status']=='재확인 필요'
    env[3]('adjust_outbound',{'outbound_id':out['id'],'version':env[6](vid)['version'],'kind':'RETURN','reason':'차량만 반납'})
    assert row(get,env,'CUP')['ending']==98
    assert env[1].get('/api/outbound',headers=env[2]).json()[0]['snapshot']==original

def test_item_metadata_snapshot_and_alias_collision(env):
    get,cmd=configure(env);i=next(i for i in get()['items'] if i['id']=='SC');i.update(aliases='sc',price=1200);cmd('item',item=i)
    cmd('movement',kind='DAMAGE',day='2026-10-02',reason='파손',lines=[{'item_id':'SC','qty':2}])
    i.update(code='SC-NEW',name='변경명',pack=12,price=1500);cmd('item',item=i)
    event=get()['report']['entries'][0];assert event['lines'][0]['snapshot']['code']=='SC' and event['lines'][0]['snapshot']['price']==1200
    assert row(get,env,'SC')['ending']==98
    other=next(i for i in get()['items'] if i['id']=='YC');other.update(code='s c',aliases='');cmd('item',422,item=other)

def test_unknown_pack_and_stock_draft_no_write(env):
    get,cmd=configure(env,stock=False);d=get();assert d['stock_draft']['ST02'] is None and d['stock_draft']['SSP']==51
    assert all(r['ending'] is None for r in d['report']['rows'])
    cmd('movement',422,kind='IN',day='2026-10-02',reason='test',lines=[{'item_id':'SC','boxes':1,'loose':0}])
    cmd('movement',kind='IN',day='2026-10-02',reason='test',lines=[{'item_id':'SSP','boxes':2,'loose':1}]);assert get()['report']['entries'][0]['lines'][0]['delta']==5

def test_rule_model_identity_and_unknown_sets(env):
    configure(env,'FORZA350');data=env[1].get('/api/parts',headers=env[2],params={'day':'2026-10-02','month':'2026-10'}).json()
    for mid,p in [('fake-PCX',request()),(env[11],request(set='EPP'))]:
        r=env[1].post('/api/parts/order-preview',headers=env[2],json={'model_id':mid,'plan':p});assert r.status_code==422,r.text

def test_auto_entry_no_manual_cancel_or_import(env):
    vid,get,cmd=assigned(env);complete(env,vid);dispatch(env,vid);d=env[4]()['today'];event=next(e for e in get(d)['report']['entries'] if e.get('auto'))
    cmd('cancel',422,id=event['id'],reason='수동 취소 금지')
    cmd('import',409,day=d,checked=True,rows=[{'source':'a'*64,'outbound_id':event['outbound_id'],'codes':'SC'}])

def test_legacy_explicit_conversion(env):
    get,_=configure(env);vid=env[5]();env[7]('assign',vid,{'number':str(uuid.uuid4()),'scheduled':env[4]()['today'],'options':[{'master_id':env[9],'qty':1}]})
    env[7]('parts_plan',vid,{'parts_order':request()},422)
    env[7]('parts_plan',vid,{'parts_order':request(reason='미완료 기존 주문 검토'),'convert':True})
    assert env[6](vid)['assignment']['parts_order']

def test_concurrent_dispatch_posts_once(env):
    from concurrent.futures import ThreadPoolExecutor
    vid,get,_=assigned(env);complete(env,vid);v=env[6](vid)
    payload={'vehicle_id':vid,'version':v['version'],'exception_reason':'동시성 검사','handed':{l['id']:l['done'] for l in v['assignment']['items']}}
    def submit(_):return env[1].post('/api/command',headers=env[2],json={'command_id':str(uuid.uuid4()),'action':'dispatch','payload':payload}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(submit,range(2)))
    assert sorted(statuses)==[200,409];assert row(get,env,'SC')['ending']==99

def test_failure_after_posting_rolls_back_vehicle_and_ledger(env,monkeypatch):
    from server import parts_orders
    from fastapi import HTTPException
    vid,get,_=assigned(env);complete(env,vid);original=parts_orders.post_dispatch
    def fail(s,u,out):original(s,u,out);raise HTTPException(503,'injected isolated failure')
    monkeypatch.setattr(parts_orders,'post_dispatch',fail);dispatch(env,vid,503)
    assert env[6](vid)['assignment'] and env[6](vid)['stay_id'];assert row(get,env,'SC')['ending']==100
    assert env[1].get('/api/outbound',headers=env[2]).json()==[]

def test_inactive_dispatch_block_and_no_partial_consumption(env):
    vid,get,cmd=assigned(env);complete(env,vid);i=next(i for i in get()['items'] if i['id']=='SC');i['active']=False;cmd('item',item=i)
    dispatch(env,vid,422,stock_exception_reason='이유로 비활성 우회 불가');assert row(get,env,'CUP')['ending']==100

def test_manual_set_selection_requires_component_and_alternative(env):
    configure(env);c,h=env[1:3]
    def preview(p):return c.post('/api/parts/order-preview',headers=h,json={'model_id':env[11],'plan':p})
    r=preview(request(install=['SE']));assert r.status_code==200 and any(l['part_id']=='SSP' for l in r.json()['lines'])
    assert preview(request(set='EPP',install=['ST01'])).status_code==422

def test_worker_cannot_override_unknown_inventory(env):
    vid,get,_=assigned(env,stock=False);complete(env,vid)
    env[3]('user',{'username':'stockworker','password':'Synthetic-Test-123','role':'worker','active':True})
    tok=env[1].post('/api/login',json={'username':'stockworker','password':'Synthetic-Test-123'}).json()['token'];v=env[6](vid)
    r=env[1].post('/api/command',headers={'Authorization':'Bearer '+tok},json={'command_id':str(uuid.uuid4()),'action':'dispatch','payload':{'vehicle_id':vid,'version':v['version'],'exception_reason':'허용 안 됨','stock_exception_reason':'허용 안 됨'}})
    assert r.status_code==403;assert row(get,env,'SC')['ending'] is None

@pytest.mark.parametrize('template,screen', [('PCX','WPCX_1'),('NMAX','WNMAX_1')])
def test_b2c_screen_only_silver(env,template,screen):
    vid,get,_=assigned(env,request('B2C',screen=True),template);complete(env,vid);dispatch(env,vid)
    assert row(get,env,screen)['ending']==99 and row(get,env,'CUP')['ending']==100
    bad=env[1].post('/api/parts/order-preview',headers=env[2],json={'model_id':env[11],'plan':request('B2C',install=['WPCX_0'])})
    assert bad.status_code==422

def test_category_price_and_old_pack_migration_preserve_history(env):
    get,cmd=configure(env);cmd('category',category={'id':'cat','name':'소모품','active':True})
    item=next(i for i in get()['items'] if i['id']=='MITT');item.update(pack=20,price=0,category_id='cat');cmd('item',item=item)
    cmd('movement',kind='IN',day='2026-10-02',reason='20EA 당시',lines=[{'item_id':'MITT','boxes':1,'loose':0}]);before=get()['report']['entries'][0]
    cmd('review_defaults',checked=True);assert row(get,env,'MITT')['ending']==120
    assert get()['report']['entries'][0]==before and before['lines'][0]['snapshot']['pack']==20 and before['lines'][0]['snapshot']['price']==0
    cmd('category',category={'id':'cat','name':'소모품 변경','active':False});assert get()['categories'][0]['active'] is False
    assert next(i for i in get()['items'] if i['id']=='CUP')['price'] is None

def test_stocktake_box_values_and_export_supplier_order(env):
    from server.parts import quantity,exports,report,initial
    data=initial();items={i['id']:i for i in data['items']}
    for key,value,total in [('SSP','25/1',51),('RBP','7/2',44),('RBN','14/0',56),('RBF','4/3',19),('RBX','2/2',8),('RBA','4/0',16)]:assert quantity(items[key],value)==total
    data['entries']=[{'id':'test','kind':'STOCKTAKE','day':'2026-10-01','at':'2026-10-01','quantities':{k:None for k in items}}]
    data['entries'][0]['quantities'].update(WPCX_0=51,WPCX_1=46,WNMAX_0=None,WNMAX_1=40)
    items['WPCX_1']['order']=11;items['WPCX_0']['active']=False
    result=exports(data,report(data,'2026-10-02'));assert '51EA/46EA' in result['quantities'] and '-/40EA' in result['quantities']

def test_used_existing_no_double_equipment_or_inventory(env):
    vid,get,_=assigned(env,request('B2C'),kind='USED');complete(env,vid);dispatch(env,vid)
    out=env[1].get('/api/outbound',headers=env[2]).json()[0]
    env[3]('adjust_outbound',{'outbound_id':out['id'],'version':env[6](vid)['version'],'kind':'RETURN','reason':'차량 반품'})
    env[7]('assign',vid,{'number':str(uuid.uuid4()),'scheduled':env[4]()['today'],'parts_order':request('B2C',sources={'SC':'EXISTING'},reason='기존 장착 실물 확인')})
    complete(env,vid);dispatch(env,vid)
    assert row(get,env,'SC')['ending']==99
    latest=env[1].get('/api/outbound',headers=env[2]).json()[0]
    assert sum(l['qty'] for l in latest['snapshot']['options'] if l['item'].get('part_id')=='SC')==1

def test_ready_does_not_consume_and_reports_match(env):
    vid,get,_=assigned(env);complete(env,vid);env[7]('ubis',vid,{'status':'INSTALLED'});env[7]('finish_work',vid);env[7]('ready',vid)
    assert row(get,env,'SC')['ending']==100
    dispatch(env,vid);d=env[4]()['today'];r=env[1].get('/api/report/'+d,headers=env[2]).json()
    assert r['parts_daily']==get(d)['parts_daily'] and r['dispatched']==sum(r['parts_daily']['counts'].values())
    out=env[1].get('/api/outbound',headers=env[2]).json()[0];env[3]('adjust_outbound',{'outbound_id':out['id'],'version':env[6](vid)['version'],'kind':'VOID','reason':'실물 미출고'})
    r=env[1].get('/api/report/'+d,headers=env[2]).json();assert r['dispatched']==0 and r['parts_daily']==get(d)['parts_daily']

def test_external_preview_provenance_and_unknown_rbh(env):
    get,cmd=configure(env);model=next(m for m in get()['models'] if m['id']==env[11])['name']
    r=env[1].post('/api/parts/preview',headers=env[2],json={'day':'2026-10-02','text':f'1\t2026-10-02\tB2B\t신차\t합성\t{model}\tSE, RBH'}).json()['rows'][0]
    assert 'SE' in r['raw_codes'] and 'SSP' in r['set_codes'] and 'CUP' in r['default_codes'];assert any('RBH' in x for x in r['issues'])

def test_kst_business_boundary():
    from datetime import datetime,timezone
    from server.domain import day
    assert day(datetime(2026,10,15,15,0,tzinfo=timezone.utc))=='2026-10-16'
    assert day(datetime(2026,10,15,14,59,tzinfo=timezone.utc))=='2026-10-15'

@pytest.mark.parametrize('choice,item,component',[('TOP01','ST01','RBP'),('TOP02','ST02','RBP'),('EPP','SE','SSP')])
@pytest.mark.parametrize('item_mode,component_mode',[('DELIVERY','DELIVERY'),('DELIVERY','OMIT'),('INSTALL','DELIVERY'),('OMIT','DELIVERY')])
def test_set_component_fulfilment(env,choice,item,component,item_mode,component_mode):
    vid,get,_=assigned(env,request(set=choice,set_modes={'item':item_mode,'component':component_mode}))
    ls=env[6](vid)['assignment']['parts_order']['lines']
    for ident,mode in [(item,item_mode),(component,component_mode)]:
        matches=[r for r in ls if r['part_id']==ident]
        assert len(matches)==(0 if mode=='OMIT' else 1)
        if matches:assert matches[0]['purpose']==mode and matches[0]['source']=='WAREHOUSE'
    complete(env,vid);dispatch(env,vid)
    for ident,mode in [(item,item_mode),(component,component_mode)]:assert row(get,env,ident)['ending']==(100 if mode=='OMIT' else 99)

@pytest.mark.parametrize('modes',[{'item':'BAD'},{'unknown':'INSTALL'},{'item':'OMIT','component':'OMIT'}])
def test_invalid_set_modes(env,modes):
    configure(env);vid=env[5]()
    env[7]('assign',vid,{'number':'invalid','scheduled':env[4]()['today'],'parts_order':request(set='EPP',set_modes=modes)},422)

def test_factory_bracket_delivered_from_stock(env):
    vid,get,_=assigned(env,request(set='TOP01',set_modes={'item':'DELIVERY','component':'DELIVERY'}),'ZONTES368G')
    ls=env[6](vid)['assignment']['parts_order']['lines'];r=next(r for r in ls if r['part_id']=='RBZ')
    assert r['purpose']=='DELIVERY' and r['source']=='WAREHOUSE'
    complete(env,vid);dispatch(env,vid);assert row(get,env,'RBZ')['ending']==99

def test_set_override_cannot_readd_omitted_component(env):
    configure(env);vid=env[5]()
    env[7]('assign',vid,{'number':'conflict','scheduled':env[4]()['today'],'parts_order':request(set='EPP',set_modes={'component':'OMIT'},install=['SSP'])},422)

@pytest.mark.parametrize('template,purpose',[('PCX','INSTALL'),('NMAX','INSTALL'),('FORZA350','DELIVERY'),('XMAX','INSTALL'),('ADV350','INSTALL'),('ZONTES368G','INSTALL'),('HUSKY','INSTALL')])
def test_b2b_cup_model_purpose(env,template,purpose):
    vid,get,_=assigned(env,request(),template)
    cup=next(r for r in env[6](vid)['assignment']['parts_order']['lines'] if r['part_id']=='CUP')
    assert cup['purpose']==purpose and cup['qty']==1
    complete(env,vid);dispatch(env,vid);assert row(get,env,'CUP')['ending']==99


def test_b2b_mitt_is_posted_once_only_at_actual_dispatch(env):
 vid,get,_=assigned(env);assert row(get,env,'MITT')['ending']==100
 complete(env,vid);env[7]('ubis',vid,{'status':'INSTALLED'});env[7]('finish_work',vid);env[7]('ready',vid)
 assert row(get,env,'MITT')['ending']==100
 a=env[6](vid)['assignment'];cid=str(uuid.uuid4());payload={'vehicle_id':vid,'version':env[6](vid)['version'],'handed':{l['id']:l['done'] for l in a['items']}}
 env[3]('dispatch',payload,cid=cid);env[3]('dispatch',payload,cid=cid)
 for key in ['SC','CUP','MITT']:assert row(get,env,key)['ending']==99


def test_approved_default_repair_preserves_completed_work_and_ledger(env):
 from server.b2b_defaults_repair import repair
 from server.parts import load
 from server.models import User
 get,cmd=configure(env);rules=get()['rules'];rules['defaults']['B2B']=['SC','CUP'];cmd('rules',rules=rules)
 vid=env[5]();env[7]('assign',vid,{'scheduled':env[4]()['today'],'parts_order':request()});complete(env,vid)
 env[7]('ubis',vid,{'status':'INSTALLED'});env[7]('finish_work',vid);env[7]('ready',vid)
 a=env[6](vid)['assignment'];before=copy.deepcopy(a['options'])
 with env[0].transaction() as s:
  _,data=load(s);entries=copy.deepcopy(data['entries']);closings=copy.deepcopy(data['closings'])
  result=repair(s,s.scalar(select(User).where(User.username=='admin')),a['id']);assert result['existing_work_preserved']
  _,after=load(s);assert entries==after['entries'] and closings==after['closings']
 updated=env[6](vid)['assignment'];assert not updated['ready']
 for old in before:assert next(x for x in updated['options'] if x['id']==old['id'])==old
 mitt=next(x for x in updated['options'] if x['item'].get('part_id')=='MITT');assert mitt['qty']==1 and mitt['done']==0
 assert row(get,env,'MITT')['ending']==100
