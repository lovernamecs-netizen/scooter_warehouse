import copy,uuid,hashlib,json
from test_workflow import env
from test_purchase_xlsx import fixture
from server.purchase_xlsx import parse

def body(blank=False):
 p=parse(fixture(1),'synthetic.xlsx')
 if blank:p['rows'][0]['data']['vin']=''
 return identity(p)
def identity(p):
 p=copy.deepcopy(p)
 for r in p['rows']:r['source_identity']=hashlib.sha256(json.dumps(r['data'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()+':1'
 p['request_id']=str(uuid.uuid4());return p
def send(env,p):
 r=env[1].post('/api/purchases/import',headers=env[2],json=p);assert r.status_code==200,r.text;return r.json()
def rows(env):return env[1].get('/api/purchases',headers=env[2]).json()['rows']
def change(env,r,action,**kw):
 out=env[1].post('/api/purchases/review',headers=env[2],json={'id':r['id'],'revision':r['revision'],'action':action,'reason':'synthetic audit','request_id':str(uuid.uuid4()),**kw});assert out.status_code==200,out.text

def test_prevents_deleted_row_resurrection(env):
 p=body();send(env,p);r=rows(env)[0];change(env,r,'delete');assert rows(env)[0]['data']['deleted']
 send(env,identity(p));assert rows(env)[0]['data'].get('deleted')

def test_prevents_local_edit_overwrite(env):
 p=body();send(env,p);r=rows(env)[0];source=copy.deepcopy(r['data']['source']);source['memo1']='local change';change(env,r,'edit',source=source)
 send(env,identity(p));assert rows(env)[0]['data']['source']['memo1']=='local change'

def test_prevents_blank_vin_duplicate_on_source_edit(env):
 p=body(True);send(env,p);p['rows'][0]['data']['memo1']='source change';send(env,identity(p));assert len(rows(env))==1

def test_prevents_cross_sheet_identity_collision(env):
 p=body(True);send(env,p);p['sheet']='별도 원장';p['sha256']='a'*64;send(env,identity(p));assert len(rows(env))==2

def test_conflict_review_keeps_or_applies_with_audit(env):
 p=body();send(env,p);r=rows(env)[0];source=copy.deepcopy(r['data']['source']);source['memo1']='local';change(env,r,'edit',source=source)
 result=send(env,identity(p));assert result['conflicts']==1 and result['protected']==1
 conflicts=env[1].get('/api/purchases/conflicts',headers=env[2]).json();event=conflicts['rows'][0]
 response=env[1].post('/api/purchases/review',headers=env[2],json={'action':'resolve_import','event_id':event['id'],'choice':'source','reason':'accept original','request_id':str(uuid.uuid4())});assert response.status_code==200,response.text
 assert rows(env)[0]['data']['source']['memo1']==''
 assert env[1].get('/api/purchases/conflicts',headers=env[2]).json()['count']==0

def test_blank_identical_duplicate_rows_survive_reimport(env):
 p=body(True);p['rows'].append(copy.deepcopy(p['rows'][0]));p['rows'][1]['row']=3;p['rows'][1]['source_identity']=p['rows'][1]['source_identity'].split(':')[0]+':2'
 send(env,p);p['request_id']=str(uuid.uuid4());send(env,p);assert len(rows(env))==2

def test_source_bookmark_includes_undated_and_detects_changes(env):
 p=body(True);p['rows'][0]['data']['received_date']='';p=identity(p);send(env,p)
 sources=env[1].get('/api/purchases/sources',headers=env[2]).json()['sources'];assert len(sources)==1
 params={'namespace':sources[0]['id'],'through':2}
 result=env[1].get('/api/purchases/source-review',headers=env[2],params=params);assert result.status_code==200,result.text
 data=result.json();assert data['count']==1 and not data['stale']
 saved=env[1].post('/api/purchases/source-review',headers=env[2],json={**params,'token':data['token'],'reason':'확정','request_id':str(uuid.uuid4())});assert saved.status_code==200,saved.text
 change(env,rows(env)[0],'delete')
 assert env[1].get('/api/purchases/source-review',headers=env[2],params=params).json()['stale']

def test_bad_price_is_not_missing_vehicle(env):
 p=body();p['rows'][0]['data']['vat_included']='가격 미정';p=identity(p);send(env,p)
 data=rows(env)[0]['data'];assert data['source']['vat_included']=='가격 미정' and data['values']['vat_included'] is None and not data['pending']

def test_repeated_conflict_is_deduplicated_and_stale_can_close(env):
 p=body();send(env,p);r=rows(env)[0];source=copy.deepcopy(r['data']['source']);source['memo1']='local';change(env,r,'edit',source=source)
 send(env,identity(p));send(env,identity(p));conflicts=env[1].get('/api/purchases/conflicts',headers=env[2]).json();assert conflicts['count']==1
 r=rows(env)[0];change(env,r,'delete');revision=rows(env)[0]['revision']
 response=env[1].post('/api/purchases/review',headers=env[2],json={'action':'resolve_import','event_id':conflicts['rows'][0]['id'],'choice':'keep','reason':'old conflict','request_id':str(uuid.uuid4())});assert response.status_code==200,response.text
 assert rows(env)[0]['revision']==revision and rows(env)[0]['data']['deleted']
 assert env[1].get('/api/purchases/conflicts',headers=env[2]).json()['count']==0
