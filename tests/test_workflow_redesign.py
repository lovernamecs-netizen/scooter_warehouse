import uuid,copy
from test_workflow import env
from test_purchase_stability import body,send,identity,rows,change

def test_month_scan_separate_months_and_stale(env):
 p=body();send(env,p);month=p['rows'][0]['data']['received_date'][:7]
 response=env[1].get('/api/purchases/month',headers=env[2],params={'month':month});assert response.status_code==200,response.text
 data=response.json();assert data['counts']=={'일치':1} and not data['legacy_reference']
 saved=env[1].post('/api/purchases/month',headers=env[2],json={'month':month,'token':data['token'],'reason':'확인','acknowledged':True,'request_id':str(uuid.uuid4())});assert saved.status_code==200,saved.text
 record=rows(env)[0];source=copy.deepcopy(record['data']['source']);source['memo1']='changed';change(env,record,'edit',source=source)
 data=env[1].get('/api/purchases/month',headers=env[2],params={'month':month}).json();assert data['approval']['stale'] and data['counts']['항목 차이']==1
 assert env[1].get('/api/purchases/month',headers=env[2],params={'month':'2025-01'}).json()['count']==0

def test_scan_only_detects_missing_and_does_not_modify(env):
 p=body();send(env,p);month=p['rows'][0]['data']['received_date'][:7];before=rows(env)
 sources=env[1].get('/api/purchases/sources',headers=env[2]).json()['sources']
 result=env[1].post('/api/purchases/source-scan',headers=env[2],json={**p,'rows':[],'source_namespace':sources[0]['id'],'request_id':str(uuid.uuid4())});assert result.status_code==200,result.text
 result=env[1].get('/api/purchases/month',headers=env[2],params={'month':month}).json();assert result['counts']=={'프로그램에만 있음':1};assert before==rows(env)

def test_calendar_groups_identical_vin_preserves_originals(env):
 p=body();send(env,p);p['source_namespace']='second';p['request_id']=str(uuid.uuid4());send(env,p)
 result=env[1].get('/api/purchases/page?month=2026-01',headers=env[2]);assert result.status_code==200,result.text
 data=result.json();assert data['raw_total']==2 and data['total']==1 and data['rows'][0]['duplicate_count']==2
 assert len(rows(env))==2

def test_business_unsold_waiting_and_closing_immutable(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,*_=env
 one=receive();two=receive();vc('move',one,{'slot_id':z['slots'][0]['id']})
 vc('assign',two,{'number':str(uuid.uuid4()),'scheduled':state()['today']})
 day=state()['today'];response=c.get('/api/report/'+day,headers=h);assert response.status_code==200,response.text
 result=response.json()['business'];assert result['totals']['unsold']==1 and result['totals']['waiting']==1
 cmd('close_day',{'day':day})
 before=c.get('/api/report/'+day,headers=h).json()['closing']['snapshot']
 receive();after=c.get('/api/report/'+day,headers=h).json();assert after['closing']['snapshot']==before and after['business']['totals']['count']==3

def test_month_snapshot_remains_unchanged_and_permission(env):
 from sqlalchemy import select
 from server.models import PurchaseReviewEvent
 p=body();send(env,p);month=p['rows'][0]['data']['received_date'][:7]
 data=env[1].get('/api/purchases/month',headers=env[2],params={'month':month}).json()
 response=env[1].post('/api/purchases/month',headers=env[2],json={'month':month,'token':data['token'],'reason':'confirmed','acknowledged':True,'request_id':str(uuid.uuid4())});ident=response.json()['event_id']
 before=env[1].get('/api/purchases/month-snapshot/'+ident,headers=env[2]).json()
 record=rows(env)[0];source=copy.deepcopy(record['data']['source']);source['vat_included']='500';change(env,record,'edit',source=source)
 assert env[1].get('/api/purchases/month-snapshot/'+ident,headers=env[2]).json()==before
 worker=env[1].post('/api/login',json={'username':'worker','password':'test-password-123'}).json()['token']
 response=env[1].post('/api/purchases/month',headers={'Authorization':'Bearer '+worker},json={'month':month});assert response.status_code==403

def test_value_effective_day_and_duplicate_price_warning(env):
 p=body();send(env,p);record=rows(env)[0];old=record['data']['values']['vat_included'];source=copy.deepcopy(record['data']['source']);source['vat_included']='100'
 change(env,record,'edit',source=source,value_effective_day='2099-01-01')
 data=env[1].get('/api/report/'+env[4]()['today'],headers=env[2]).json()['business'];assert data['unlinked'][0]['value']==old
 p['source_namespace']='other-price';p['rows'][0]['data']['vat_included']='200';p=identity(p);send(env,p)
 data=env[1].get('/api/report/'+env[4]()['today'],headers=env[2]).json()['business'];assert data['unlinked'][0]['value'] is None and data['unlinked_count']==1
