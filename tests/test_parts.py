import uuid
import pytest
from sqlalchemy import text
from test_workflow import env
from server.parts import PartsBook

def setup(env):
 db,c,h,*_=env
 def get(d='2026-10-02'):return c.get('/api/parts',params={'day':d,'month':d[:7]},headers=h).json()
 def cmd(action,status=200,**p):
  p={'request_id':str(uuid.uuid4()),'revision':get()['revision'],'action':action,**p};r=c.post('/api/parts/command',headers=h,json=p);assert r.status_code==status,r.text;return r.json()
 def base(d='2026-10-01',q=100):cmd('stocktake',day=d,reason='실사',quantities={i['id']:str(q) for i in get()['items']})
 def preview(t):
  r=c.post('/api/parts/preview',headers=h,json={'day':'2026-10-02','text':t});assert r.status_code==200,r.text;return r.json()['rows']
 return db,c,h,get,cmd,base,preview

def test_baseline_and_arithmetic_copy(env):
 db,c,h,get,cmd,base,prev=setup(env);assert all(r['ending'] is None for r in get()['report']['rows']);cmd('close',422,day='2026-10-02',checked=True);base()
 cmd('movement',day='2026-10-02',kind='IN',reason='공급처',lines=[{'item_id':'SC','qty':20}]);cmd('movement',day='2026-10-02',kind='OUT',reason='업체',lines=[{'item_id':'SC','qty':5}])
 rows=prev('1\t2026. 10. 2\tB2C\t리스\t업체\tNMAX\tSC, ST01');cmd('import',day='2026-10-02',rows=rows,checked=True,external_confirmed=True)
 r=get();assert next(x for x in r['report']['rows'] if x['id']=='SC')['ending']==114;assert r['calendar'][0]['stocktake'];cmd('close',day='2026-10-02',checked=True)
 ex=c.get('/api/parts/export/2026-10-02',headers=h);assert ex.status_code==200 and '114EA' in ex.json()['quantities'];assert len(ex.json()['quantities'].splitlines())==len(r['items'])-2;assert c.get('/api/export',headers=h).status_code==200

def test_unknown_inactive_b2c(env):
 db,c,h,get,cmd,base,prev=setup(env);base();rows=prev('1\t2026. 10. 2\tB2C\t리스\t업체\tNMAX\tRBP, NO');assert 'SC' in rows[0]['codes'] and 'CUP' not in rows[0]['codes'];assert any('NO' in x for x in rows[0]['issues'])
 cmd('import',422,day='2026-10-02',rows=rows,checked=True,external_confirmed=True)
 i=next(x for x in get()['items'] if x['id']=='RBP');i['active']=False;i['aliases']='';cmd('item',item=i);rows[0]['codes']='RBP';cmd('import',422,day='2026-10-02',rows=rows,checked=True,external_confirmed=True)
 rows[0]['codes']='SC';cmd('import',day='2026-10-02',rows=rows,checked=True,external_confirmed=True)

def test_duplicate_atomic_replay(env):
 db,c,h,get,cmd,base,prev=setup(env);base();rows=prev('SC\nSC');assert rows[1]['duplicate'];cmd('import',409,day='2026-10-02',rows=rows,checked=True,external_confirmed=True);assert get()['report']['entries']==[]
 body={'action':'import','request_id':str(uuid.uuid4()),'revision':get()['revision'],'day':'2026-10-02','rows':rows[:1],'checked':True,'external_confirmed':True}
 first=c.post('/api/parts/command',headers=h,json=body);assert first.status_code==200;assert c.post('/api/parts/command',headers=h,json=body).json()==first.json();cmd('import',409,day='2026-10-02',rows=rows[:1],checked=True,external_confirmed=True)

def test_revision_roles(env):
 db,c,h,get,cmd,base,prev=setup(env);rev=get()['revision'];base();cmd('movement',409,revision=rev,day='2026-10-02',kind='IN',reason='test',lines=[{'item_id':'SC','qty':1}]);env[3]('user',{'username':'view','password':'Viewer-Test-123','role':'viewer','active':True});tok=c.post('/api/login',json={'username':'view','password':'Viewer-Test-123'}).json()['token'];vh={'Authorization':'Bearer '+tok}
 assert c.get('/api/parts',headers=vh,params={'day':'2026-10-02','month':'2026-10'}).status_code==200;assert c.post('/api/parts/command',headers=vh,json={'action':'close'}).status_code==403

def test_historical_change_stocktake_boundary(env):
 db,c,h,get,cmd,base,prev=setup(env);base();cmd('close',day='2026-10-02',checked=True);base('2026-10-05',50);cmd('close',day='2026-10-06',checked=True);cmd('movement',day='2026-10-02',kind='OUT',reason='누락',lines=[{'item_id':'SC','qty':5}]);assert get()['report']['status']=='재확인 필요';assert get('2026-10-06')['report']['status']=='확정';assert c.get('/api/parts/export/2026-10-02',headers=h).status_code==422

def test_cancel_preserves_original(env):
 db,c,h,get,cmd,base,prev=setup(env);base();cmd('movement',day='2026-10-02',kind='OUT',reason='오입력',lines=[{'item_id':'SC','qty':3}]);ident=get()['report']['entries'][0]['id'];cmd('cancel',id=ident,reason='수량 오류');assert next(x for x in get()['report']['rows'] if x['id']=='SC')['ending']==100
 with db.transaction() as s:assert any(e['id']==ident for e in s.get(PartsBook,1).data['entries'])
 cmd('cancel',422,id=ident,reason='중복 취소')

def test_b2b_used_wrong_day(env):
 db,c,h,get,cmd,base,prev=setup(env);base();rows=prev('1\t2026. 10. 3\tB2B\t중고\t업체\tPCX125\tSC');assert 'CUP' in rows[0]['codes'] and 'MITT' not in rows[0]['codes'] and 'WPCX' not in rows[0]['codes'];assert any('중고' in x for x in rows[0]['issues']);cmd('import',422,day='2026-10-02',rows=rows,checked=True,external_confirmed=True)

def test_pack_code_preservation(env):
 db,c,h,get,cmd,base,prev=setup(env);base();i=next(x for x in get()['items'] if x['id']=='RBP');i['pack']=12;i['aliases']='';cmd('item',item=i);r=next(x for x in get()['report']['rows'] if x['id']=='RBP');assert r['ending']==100 and r['display']=='8/4';i['code']='OTHER';cmd('item',item=i);assert 'RBP' in next(x for x in get()['items'] if x['id']=='RBP')['aliases']

def test_preserve_vehicle_rows(env):
 db,c,h,get,cmd,base,prev=setup(env);ident=env[5]();env[7]('move',ident,{'slot_id':env[8]['slots'][0]['id']});tables=['vehicles','stays','placements','outbound','history','zones','slots','orders','assignments']
 def snap():
  with db.transaction() as s:return {t:list(s.execute(text('select * from '+t)).mappings()) for t in tables}
 before=snap();base();cmd('movement',day='2026-10-02',kind='OUT',reason='반출',lines=[{'item_id':'SC','qty':1}]);cmd('close',day='2026-10-02',checked=True);db.init();assert before==snap()

def test_negative_fraction_block(env):
 db,c,h,get,cmd,base,prev=setup(env);base(q=1);cmd('movement',day='2026-10-02',kind='OUT',reason='초과',lines=[{'item_id':'SC','qty':2}]);cmd('close',422,day='2026-10-02',checked=True);cmd('movement',422,day='2026-10-02',kind='IN',reason='bad',lines=[{'item_id':'SC','qty':1.5}])

def test_linked_outbound_dedup_and_void_warning(env):
 db,c,h,get,cmd,base,prev=setup(env);base();vid=env[5]();env[7]('assign',vid,{'number':str(uuid.uuid4()),'scheduled':env[4]()['today']});env[7]('dispatch',vid,{'confirmed_vin':env[6](vid)['vin'],'exception_reason':'검증용 출고'})
 out=c.get('/api/outbound',headers=h).json()[0];d=out['day'];rows=prev('SC');rows[0]['outbound_id']=out['id'];rows[0]['source_day']=''
 cmd('import',day=d,rows=rows,checked=True)
 rows[0]['source']='a'*64;cmd('import',409,day=d,rows=rows,checked=True)
 env[3]('adjust_outbound',{'outbound_id':out['id'],'version':env[6](vid)['version'],'kind':'VOID','reason':'오출고'})
 assert get(d)['report']['warnings'];cmd('close',422,day=d,checked=True)

def test_same_day_stocktake_includes_movements_and_does_not_double_deduct(env):
 db,c,h,get,cmd,base,prev=setup(env);base();cmd('movement',day='2026-10-02',kind='OUT',reason='실사 전 반출',lines=[{'item_id':'SC','qty':10}]);base('2026-10-02',80)
 row=next(x for x in get()['report']['rows'] if x['id']=='SC');assert row['ending']==80 and row['count_difference']==-10
 assert next(x for x in get('2026-10-03')['report']['rows'] if x['id']=='SC')['opening']==80
