import errno,uuid
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from test_workflow import env
from server.models import Setting
from server.app import create_app

def test_unexpected_exception_rolls_back_and_redacts(env):
 db,c,h,cmd,state,*_=env
 def fail(s,*args):
  s.add(Setting(key='must_rollback',value={'x':1}));s.flush()
  raise RuntimeError('secret_password SELECT hidden.sql C:/private/token')
 with patch('server.domain.execute',fail):r=c.post('/api/command',headers=h,json={'command_id':str(uuid.uuid4()),'action':'master','payload':{}})
 assert r.status_code==500,r.text
 data=r.json();assert len(data['request_id'])==32 and data['detail']==data['message']
 assert 'secret_password' not in r.text and 'SELECT' not in r.text
 with db.transaction() as s:assert s.get(Setting,'must_rollback') is None
 log=(Path(db.engine.url.database).parent/'logs/errors.log').read_text(encoding='utf-8')
 assert data['request_id'] in log and 'RuntimeError' in log and 'secret_password' not in log

def test_validation_no_raw_inputs(env):
 db,c,h,*_=env
 r=c.post('/api/command',headers=h,json=['secret_private_input'])
 assert r.status_code==422 and r.json()['code']=='VALIDATION_ERROR'
 assert 'secret_private_input' not in r.text and 'loc' not in r.text

def test_disk_full_and_backup_error_redacted(env):
 db,c,h,*_=env
 with patch('server.photo_backup.backup',side_effect=OSError(errno.ENOSPC,'secret-path')):
  r=c.post('/api/photo-backup',headers=h)
 assert r.status_code==503 and r.json()['code']=='STORAGE_FULL' and 'secret-path' not in r.text

def test_real_lifespan_and_header(env):
 db,c,h,*_=env
 with TestClient(create_app(db)) as live:
  r=live.get('/health');assert r.status_code==200 and r.json()['version']=='1.0.31'
  assert len(r.headers['x-request-id'])==32
  r=live.get('/health',headers={'content-length':'invalid'});assert r.status_code==400

def test_photo_write_failure_has_no_metadata(env):
 from test_photo_storage import post,image
 db,c,h,cmd,state,receive,v,*_=env
 ident=receive('USED');stay=v(ident)['stay_id'];raw=image()
 for code,status in [(errno.ENOSPC,503),(errno.EACCES,500)]:
  with patch('server.photo_store.atomic',side_effect=OSError(code,'private photo path')):
   r=post(c,h,ident,stay,raw)
  assert r.status_code==status and 'private photo path' not in r.text
  assert not c.get('/api/used/'+ident,headers=h).json()['media']
