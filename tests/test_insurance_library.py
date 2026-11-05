import base64,io,json,uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from PIL import Image
from sqlalchemy import select,func,event
from test_workflow import env
from server.insurance_library import InsuranceDocument,InsuranceDocumentSearch,SETTING,MARKER,save,listing,configure
from server import insurance_library as lib,photo_backup
from server.models import User,Setting
from server.security import hash_password

def payload(color='white',plate='123가4567',source='보험A.jpg'):
    stream=io.BytesIO();Image.new('RGB',(600,850),color).save(stream,'JPEG')
    return {'source':source,'plate':plate,'page':1,'review_required':True,'jpeg_base64':base64.b64encode(stream.getvalue()).decode()}
@pytest.fixture
def shared(env,tmp_path):
    db,c,h,*_=env
    folder=tmp_path/'library'
    r=c.put('/api/insurance/library/settings',headers=h,json={'path':str(folder)});assert r.status_code==200,r.text
    return db,c,h,folder

def test_admins_share_worker_denied_encrypted_and_deduplicated(shared):
    db,c,h,folder=shared
    with db.transaction() as s:s.add(User(username='admin2',role='admin',password=hash_password('synthetic-password')))
    admin2={'Authorization':'Bearer '+c.post('/api/login',json={'username':'admin2','password':'synthetic-password'}).json()['token']}
    worker={'Authorization':'Bearer '+c.post('/api/login',json={'username':'worker','password':'test-password-123'}).json()['token']}
    a=c.post('/api/insurance/library',headers=h,json=payload()).json();ident=a['document']['id'];assert not a['duplicate']
    b=c.post('/api/insurance/library',headers=admin2,json=payload(source='다른이름.jpg')).json();assert b['duplicate'] and b['metadata_differs'] and b['document']['id']==ident
    c.post('/api/insurance/library',headers=h,json=payload('blue'))
    r=c.get('/api/insurance/library',headers=admin2,params={'q':'123 가-4567'}).json();assert len(r['documents'])==2 and all(x['same_plate_count']==2 for x in r['documents'])
    image=c.get('/api/insurance/library/'+ident+'/image',headers=admin2);assert image.status_code==200 and image.content==base64.b64decode(payload()['jpeg_base64'])
    for method,path,data in [('get','/api/insurance/library',None),('get','/api/insurance/library/settings',None),('get','/api/insurance/library/'+ident+'/image',None),('post','/api/insurance/library',payload()),('put','/api/insurance/library/settings',{'path':str(folder)})]:
        response=getattr(c,method)(path,headers=worker,**({'json':data} if data else {}));assert response.status_code==403
    assert c.get('/api/insurance/library').status_code==401
    with db.read() as s:
        row=s.get(InsuranceDocument,ident);assert '123가4567' not in row.encrypted_meta and '보험A' not in row.encrypted_meta
        assert not (folder/row.file).read_bytes().startswith(b'\xff\xd8')
    assert 'jpeg_base64' not in json.dumps(r)

def test_root_change_keeps_previous_documents_and_rejects_used_folder(shared,tmp_path):
    db,c,h,old=shared;a=c.post('/api/insurance/library',headers=h,json=payload()).json()['document']
    occupied=tmp_path/'occupied';occupied.mkdir();(occupied/'keep.txt').write_text('keep')
    assert c.put('/api/insurance/library/settings',headers=h,json={'path':str(occupied)}).status_code==409
    assert (occupied/'keep.txt').read_text()=='keep'
    assert c.put('/api/insurance/library/settings',headers=h,json={'path':'relative/path'}).status_code==422
    assert c.put('/api/insurance/library/settings',headers=h,json={'path':str(Path(lib.__file__).resolve().parents[1]/'web')}).status_code==422
    new=tmp_path/'new-root';assert c.put('/api/insurance/library/settings',headers=h,json={'path':str(new)}).status_code==200
    c.post('/api/insurance/library',headers=h,json=payload('blue'))
    assert len(list(old.glob('*.enc')))==1 and len(list(new.glob('*.enc')))==1
    assert c.get('/api/insurance/library/'+a['id']+'/image',headers=h).status_code==200
    from server.app import create_app
    from fastapi.testclient import TestClient
    with TestClient(create_app(db)) as second:assert len(second.get('/api/insurance/library',headers=h).json()['documents'])==2

def test_backup_restore_preserves_roots_and_encrypted_documents(shared,tmp_path):
    db,c,h,folder=shared;entry=c.post('/api/insurance/library',headers=h,json=payload()).json()['document']
    archive=photo_backup.backup(db)['file'];report=photo_backup.verify(archive)
    assert any(x.startswith('insurance/') and x.endswith('.enc') for x in report['manifest']['files'])
    restored=tmp_path/'restored';photo_backup.restore(archive,restored,True)
    from server.db import Database
    copy=Database('sqlite:///'+str(restored/'warehouse.db'))
    with copy.transaction() as s:u=s.scalar(select(User).where(User.username=='admin'));cfg=lib.config(s)
    assert all(Path(p).is_relative_to(restored) for p in cfg['roots'].values())
    raw,_=lib.content(copy,u,entry['id']);assert raw==base64.b64decode(payload()['jpeg_base64'])
    copy.engine.dispose()

def test_concurrent_duplicate_and_corruption_detection(shared):
    db,c,h,folder=shared
    with db.transaction() as s:u=s.scalar(select(User).where(User.username=='admin'))
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:save(db,u,payload()),range(4)))
    assert sum(not r['duplicate'] for r in results)==1
    with db.read() as s:row=s.scalar(select(InsuranceDocument));ident=row.id;file=folder/row.file
    file.write_bytes(b'corrupt')
    assert c.get('/api/insurance/library/'+ident+'/image',headers=h).status_code==503
    with pytest.raises(ValueError):photo_backup.backup(db)

def test_failed_write_never_creates_committed_document(shared,monkeypatch):
    db,c,h,folder=shared
    def failure(*a):raise OSError('synthetic disk full')
    monkeypatch.setattr(lib,'atomic',failure)
    assert c.post('/api/insurance/library',headers=h,json=payload()).status_code==503
    assert c.get('/api/insurance/library',headers=h).json()['documents']==[]

def test_indexed_pagination_large_metadata(shared):
    db,c,h,folder=shared
    from server.customer_privacy import encrypt
    with db.transaction() as s:
        actor=s.scalar(select(User).where(User.username=='admin'))
        for n in range(1500):
            ident=f'{n:020d}'+uuid.uuid4().hex
            meta={'source':f'POLICY{n:05d}.jpg','plate':'','page':1,'review_required':True}
            s.add(InsuranceDocument(id=ident,digest=ident,plate_token='',root_id='test',file=ident,encrypted_meta=encrypt(json.dumps(meta)),cipher_digest='',size=1,actor_id=actor.id,created_at='2026-11-05T00:00:00+00:00'))
            for term in lib.terms(meta['source']):s.add(InsuranceDocumentSearch(document_id=ident,term=term))
    calls=[]
    def track(conn,cursor,statement,params,context,many):calls.append(statement)
    event.listen(db.engine,'before_cursor_execute',track)
    try:
        with db.transaction() as s:u=s.scalar(select(User).where(User.username=='admin'))
        first=listing(db,u);assert len(first['documents'])==50 and first['next_cursor']
        second=listing(db,u,cursor=first['next_cursor']);assert not ({x['id'] for x in first['documents']}&{x['id'] for x in second['documents']})
        result=listing(db,u,'policy01499');assert len(result['documents'])==1
        assert len(calls)<20
    finally:event.remove(db.engine,'before_cursor_execute',track)
