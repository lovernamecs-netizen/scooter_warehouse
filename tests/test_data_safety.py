import json,sqlite3,zipfile,uuid
from pathlib import Path
import pytest
from sqlalchemy import select
from server.db import Database
from server.storage_paths import require_existing
from server.photo_backup import backup,verify,prune_verified,restore
from server.photo_store import config,upload
from server.models import User,Setting
from test_workflow import env
from test_photo_storage import image,post

def test_explicit_data_location_and_missing_database(tmp_path,monkeypatch):
 monkeypatch.delenv('DATABASE_URL',raising=False)
 monkeypatch.setenv('WAREHOUSE_DATA_DIR',str(tmp_path/'data'))
 db=Database();path=Path(db.engine.url.database)
 assert path==tmp_path/'data/Database/warehouse.db'
 with pytest.raises(RuntimeError):require_existing(db.engine)
 assert not path.exists()
 path.parent.mkdir(parents=True);db.init();require_existing(db.engine)
 with db.transaction() as s:assert config(s)['roots']['default']==str(tmp_path/'data/Photos')
 monkeypatch.setenv('DATABASE_URL','sqlite:///wrong.db')
 with pytest.raises(ValueError):Database()

def test_empty_database_refused(tmp_path):
 p=tmp_path/'empty.db';p.touch();db=Database('sqlite:///'+str(p))
 with pytest.raises(RuntimeError):require_existing(db.engine)
 assert p.stat().st_size==0

def test_actual_startup_refuses_missing_database(tmp_path):
 import os,sys,subprocess,socket
 root=Path(__file__).resolve().parents[1]
 path=tmp_path/'missing.db'
 child_env=dict(os.environ,DATABASE_URL='sqlite:///'+str(path),PYTHONUTF8='1')
 child_env.pop('WAREHOUSE_DATA_DIR',None);child_env.pop('TEST_DATABASE_URL',None)
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 result=subprocess.run([sys.executable,'-X','utf8','-B',str(root/'windows/start_local.py'),'--port',str(port),'--no-browser','--no-dialog'],cwd=tmp_path,env=child_env,capture_output=True,timeout=20)
 assert result.returncode==1 and not path.exists()
 assert (tmp_path/'logs/startup.log').exists()

def test_stage_separated_data_preserves_original(env,tmp_path,monkeypatch):
 from server.data_storage import stage
 from server.photo_store import read_file
 db,c,h,cmd,state,receive,v,*_=env;one=receive('USED');raw=image()
 photo=post(c,h,one,v(one)['stay_id'],raw).json();archive=backup(db)['file']
 destination=tmp_path/'separated';result=stage(archive,destination)
 assert Path(result['database']).is_file() and not (destination/'warehouse.db').exists()
 with pytest.raises(ValueError):stage(archive,destination)
 monkeypatch.delenv('DATABASE_URL',raising=False);monkeypatch.setenv('WAREHOUSE_DATA_DIR',str(destination))
 relocated=Database();require_existing(relocated.engine)
 with relocated.transaction() as s:assert read_file(s,photo)[0]==raw
 with db.transaction() as s:assert read_file(s,photo)[0]==raw

def test_missing_photo_still_preserves_database(env):
 db,c,h,cmd,state,receive,v,*_=env
 one=receive('USED');d=post(c,h,one,v(one)['stay_id'],image()).json()
 with db.transaction() as s:root=Path(config(s)['roots'][d['root_id']])
 (root/d['path']).unlink() # synthetic photo only
 with pytest.raises(Exception):backup(db)
 with db.transaction() as s:r=s.get(Setting,'photo_backup_status').value
 assert not r['ok'] and r['emergency_database']
 with sqlite3.connect(r['emergency_database']) as con:
  assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  assert con.execute('SELECT count(*) FROM vehicles').fetchone()[0]>=1
 assert (Path(db.engine.url.database).parent/'logs/backup-failure.json').exists()

def test_uncommitted_photo_is_in_recovery_archive(env,tmp_path):
 db,c,h,cmd,state,receive,v,*_=env;one=receive('USED');stay=v(one)['stay_id'];ident=str(uuid.uuid4())
 with pytest.raises(RuntimeError):
  with db.transaction() as s:
   upload(s,s.scalar(select(User).where(User.role=='admin')),one,stay,ident,'damage','left',image())
   raise RuntimeError('synthetic interruption')
 result=backup(db)
 with zipfile.ZipFile(result['file']) as z:
  assert any(n.startswith('recovery/') and n.endswith('journal.json') for n in z.namelist())
 restored=tmp_path/'restore';restore(result['file'],restored,True)
 assert list((restored/'recovery').rglob('journal.json'))

def test_pruning_preserves_same_day_unknown_and_legacy(tmp_path):
 def archive(name,day,producer=True):
  import hashlib
  raw=b'synthetic';m={'version':1,'created_at':day+'T00:00:00+00:00','files':{'warehouse.db':{'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}},'roots':{}}
  if producer:m['producer']='ScooterWarehouse-data-safety-1'
  with zipfile.ZipFile(tmp_path/name,'w') as z:z.writestr('warehouse.db',raw);z.writestr('manifest.json',json.dumps(m))
 archive('ScooterWarehouse-old.zip','2026-10-16')
 archive('ScooterWarehouse-today1.zip','2026-10-18');archive('ScooterWarehouse-today2.zip','2026-10-18')
 archive('ScooterWarehouse-legacy.zip','2026-10-15',False)
 (tmp_path/'ScooterWarehouse-unrelated.zip').write_bytes(b'keep')
 prune_verified(tmp_path,1)
 assert not (tmp_path/'ScooterWarehouse-old.zip').exists()
 assert len(list(tmp_path.glob('*.zip')))==4
