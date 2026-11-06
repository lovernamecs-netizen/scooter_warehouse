import base64,io,json,uuid
from concurrent.futures import ThreadPoolExecutor
import httpx,pytest
from PIL import Image
from sqlalchemy import select
from test_workflow import env
from server import insurance_libresms as libre,insurance_dispatch as jobs,insurance_coolsms as sms,insurance_settings as settings
from server.insurance_api import InsuranceSend
from server.models import Setting

@pytest.fixture
def setup(env,monkeypatch):
    db,c,h,*_=env
    monkeypatch.setattr(libre,'health',lambda cfg:{'online':True})
    calls=[]
    monkeypatch.setattr(libre,'send',lambda cfg,phone,message,image:(calls.append((phone,message,image)) or {'state':'accepted','provider':'libresms','title':'test accepted','delivery_confirmed':False}))
    monkeypatch.setattr(settings,'credentials',lambda:('fake','fake','01011112222'))
    monkeypatch.setattr(sms,'credentials',settings.credentials)
    cfg={'enabled':True,'url':'http://100.64.1.2:8686','sender':'01011112222','name':'합성 전용폰','interval':2,'private_network_confirmed':True}
    response=c.put('/api/insurance/libresms/settings',headers=h,json=cfg);assert response.status_code==200,response.text
    stream=io.BytesIO();Image.new('RGB',(100,100),'white').save(stream,'JPEG')
    data={'provider':'libresms','request_id':str(uuid.uuid4()),'phone':'01033334444','plate':'123가4567','text':'{차량번호} 합성 안내','jpeg_base64':base64.b64encode(stream.getvalue()).decode()}
    return db,c,h,data,calls,cfg

@pytest.mark.parametrize('url',['http://127.0.0.1:8765','http://169.254.169.254:8080','http://example.com:8686','http://8.8.8.8:8686','http://100.64.1.2:8686/sendmms','http://name:password@100.64.1.2:8686','http://100.64.1.2:8686?to=x'])
def test_reject_arbitrary_targets(url):
    with pytest.raises(ValueError):libre.validate_url(url)

def test_explicit_opt_in_and_private_endpoint(env):
    db,c,h,*_=env
    assert c.get('/api/insurance/libresms/settings',headers=h).json()['enabled'] is False
    assert c.put('/api/insurance/libresms/settings',headers=h,json={'enabled':True,'url':'http://192.168.1.2:8686','sender':'01011112222'}).status_code==422
    worker={'Authorization':'Bearer '+c.post('/api/login',json={'username':'worker','password':'test-password-123'}).json()['token']}
    for route in ['/api/insurance/libresms/settings','/api/insurance/libresms/queue']:assert c.get(route,headers=worker).status_code==403
    assert c.post('/api/insurance/libresms/health',headers=worker).status_code==403

def test_queue_persists_no_network_until_worker_and_clears_images(setup):
    db,c,h,data,calls,cfg=setup
    assert c.post('/api/insurance/mms/send',headers=h,json=data).json()['state']=='queued'
    assert not calls
    with db.read() as s:
        job=s.get(jobs.InsuranceDispatch,data['request_id']);assert data['phone'] not in job.payload and data['jpeg_base64'] not in job.payload
    jobs.recover(db);jobs.process_once(db);assert len(calls)==1
    assert c.get('/api/insurance/libresms/queue',headers=h).json()[0]['state']=='accepted'
    with db.read() as s:assert not s.get(jobs.InsuranceDispatch,data['request_id']).payload
    repeated=c.post('/api/insurance/mms/send',headers=h,json={**data,'request_id':str(uuid.uuid4())}).json();assert repeated['repeated_request'] and len(calls)==1

def test_offline_cancel_and_config_snapshot(setup,monkeypatch):
    db,c,h,data,calls,cfg=setup
    c.post('/api/insurance/mms/send',headers=h,json=data)
    monkeypatch.setattr(libre,'health',lambda cfg:{'online':False});jobs.process_once(db);assert not calls
    assert c.get('/api/insurance/libresms/queue',headers=h).json()[0]['state']=='queued'
    assert c.post('/api/insurance/libresms/queue/'+data['request_id']+'/cancel',headers=h).json()['state']=='cancelled'
    assert c.post('/api/insurance/libresms/queue/'+data['request_id']+'/cancel',headers=h).status_code==409
    new={**data,'request_id':str(uuid.uuid4())};c.post('/api/insurance/mms/send',headers=h,json=new)
    c.put('/api/insurance/libresms/settings',headers=h,json={**cfg,'url':'http://100.64.1.3:8686'})
    monkeypatch.setattr(libre,'health',lambda cfg:{'online':True});jobs.process_once(db);assert not calls

def test_restart_processing_unknown_no_fallback(setup,monkeypatch):
    db,c,h,data,calls,cfg=setup;c.post('/api/insurance/mms/send',headers=h,json=data)
    with db.transaction() as s:s.get(jobs.InsuranceDispatch,data['request_id']).state='processing'
    jobs.recover(db);jobs.process_once(db);assert not calls
    assert c.get('/api/insurance/libresms/queue',headers=h).json()[0]['state']=='unknown'
    paid=[];monkeypatch.setattr(sms,'send_one',lambda data:paid.append(1))
    outcome=c.post('/api/insurance/mms/send',headers=h,json={**data,'provider':'coolsms','request_id':str(uuid.uuid4())}).json()
    assert outcome['state']=='unknown' and outcome['provider']=='libresms' and not paid

def test_concurrent_same_content_and_request_binding(setup):
    db,c,h,data,calls,cfg=setup
    with ThreadPoolExecutor(max_workers=4) as pool:responses=list(pool.map(lambda _:c.post('/api/insurance/mms/send',headers=h,json={**data,'request_id':str(uuid.uuid4())}),range(4)))
    assert all(r.status_code==200 for r in responses)
    assert len(c.get('/api/insurance/libresms/queue',headers=h).json())==1
    ident=responses[0].json()['request_id']
    assert c.post('/api/insurance/mms/send',headers=h,json={**data,'request_id':ident,'phone':'01099998888'}).status_code==409
    assert c.post('/api/insurance/mms/send',headers=h,json={**data,'request_id':ident,'provider':'coolsms'}).status_code==409

def test_transport_exact_json_and_failure_unknown(monkeypatch):
    cfg={'url':'http://100.64.1.2:8686'};calls=[]
    monkeypatch.setattr(libre,'request',lambda url,path,payload=None:(calls.append((url,path,payload)) or (200,{'Success':True})))
    r=libre.send(cfg,'01033334444','한글 안내',b'jpeg');assert r['state']=='accepted' and not r['delivery_confirmed']
    assert calls[0][1]=='/sendmms' and calls[0][2]=={'to':'01033334444','message':'한글 안내','image':base64.b64encode(b'jpeg').decode()}
    for value in [(200,{'success':False}),(302,{'success':True}),(200,{'other':'yes'})]:
        monkeypatch.setattr(libre,'request',lambda *a: value);assert libre.send(cfg,'01033334444','x',b'jpeg')['state']=='unknown'
    def timeout(*a):raise httpx.ReadTimeout('synthetic timeout')
    monkeypatch.setattr(libre,'request',timeout);assert libre.send(cfg,'01033334444','x',b'jpeg')['state']=='unknown'

def test_health_never_sends_and_cool_remains_default(setup,monkeypatch):
    db,c,h,data,calls,cfg=setup;paid=[]
    monkeypatch.setattr(sms,'send_one',lambda data:(paid.append(1) or {'state':'accepted','title':'test','delivery_confirmed':False}))
    body=dict(data);body.pop('provider');r=c.post('/api/insurance/mms/send',headers=h,json=body).json()
    assert r['state']=='accepted' and len(paid)==1 and not calls
    duplicate=c.post('/api/insurance/mms/send',headers=h,json={**data,'request_id':str(uuid.uuid4())}).json();assert duplicate['provider']=='coolsms' and duplicate['repeated_request']

def test_backup_contains_pending_job_and_restore_does_not_send(setup,tmp_path):
    db,c,h,data,calls,cfg=setup
    from server.photo_backup import backup,restore
    from server.db import Database
    c.post('/api/insurance/mms/send',headers=h,json=data)
    dest=tmp_path/'restore';restore(backup(db)['file'],dest,True)
    copy=Database('sqlite:///'+str(dest/'warehouse.db'))
    with copy.read() as s:assert s.get(jobs.InsuranceDispatch,data['request_id']).state=='unknown'
    assert not libre.config(copy)['enabled'];jobs.process_once(copy)
    assert not calls;copy.engine.dispose()


def test_two_devices_independent_queue_and_cross_device_dedupe(setup,monkeypatch):
    db,c,h,data,calls,cfg=setup
    second={**cfg,'device_id':'phone2','name':'합성 업무폰 2','url':'http://100.64.1.3:8686','sender':'01022223333'}
    assert c.put('/api/insurance/libresms/settings',headers=h,json=second).status_code==200
    assert c.get('/api/insurance/libresms/settings?device_id=phone1',headers=h).json()['sender']==cfg['sender']
    assert c.get('/api/insurance/libresms/settings?device_id=phone2',headers=h).json()['sender']==second['sender']
    assert c.get('/api/insurance/libresms/settings?device_id=phone3',headers=h).status_code==422
    first=c.post('/api/insurance/mms/send',headers=h,json=data).json()
    duplicate=c.post('/api/insurance/mms/send',headers=h,json={**data,'device_id':'phone2','request_id':str(uuid.uuid4())}).json()
    assert duplicate['request_id']==first['request_id'] and duplicate['repeated_request']
    other={**data,'device_id':'phone2','request_id':str(uuid.uuid4()),'phone':'01044445555'}
    assert c.post('/api/insurance/mms/send',headers=h,json=other).json()['state']=='queued'
    monkeypatch.setattr(libre,'health',lambda config:{'online':config['device_id']=='phone2'})
    sent=[]
    monkeypatch.setattr(libre,'send',lambda config,*args:(sent.append(config['device_id']) or {'state':'accepted','provider':'libresms','title':'mock','delivery_confirmed':False}))
    jobs.process_once(db,'phone1');jobs.process_once(db,'phone2')
    assert sent==['phone2']
    rows=c.get('/api/insurance/libresms/queue',headers=h).json()
    assert next(r for r in rows if r['id']==data['request_id'])['state']=='queued'
    assert next(r for r in rows if r['id']==other['request_id'])['device_id']=='phone2'
