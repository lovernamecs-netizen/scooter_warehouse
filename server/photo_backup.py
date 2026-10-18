"""Consistent SQLite + immutable photo backup; verified restore to a NEW directory."""
import hashlib,json,sqlite3,tempfile,zipfile,os,shutil,threading,time
from pathlib import Path
from contextlib import closing
from datetime import datetime
from sqlalchemy import select
from .models import Setting
from .photo_store import config,read_file,stamp,safe,atomic
from .used_stock import put
LOCK=threading.Lock()

def emergency_database(db,destination):
 # A partial recovery point is NEVER represented as a complete photo backup.
 if not db.sqlite:raise ValueError('SQLite only')
 dest=Path(destination)/'EmergencyDB';dest.mkdir(parents=True,exist_ok=True)
 target=dest/('DatabaseOnly-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite')
 with tempfile.TemporaryDirectory(dir=dest) as temp:
  snapshot=Path(temp)/'snapshot.sqlite'
  source_path=Path(db.engine.url.database).resolve()
  with closing(sqlite3.connect(source_path.as_uri()+'?mode=ro',uri=True)) as source,closing(sqlite3.connect(snapshot)) as output:
   source.backup(output)
   if output.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Emergency DB integrity failure')
  os.replace(snapshot,target)
 return str(target)

def prune_verified(dest,retention):
 # Preserve every archive within the newest N backup dates. Never delete unknown files.
 valid=[]
 for path in sorted(dest.glob('ScooterWarehouse-*.zip'),reverse=True):
  try:
   report=verify(path)
   # Archives created before this policy are retained for manual review.
   if report['manifest'].get('producer')!='ScooterWarehouse-data-safety-1':continue
   valid.append((path,report['created_at'][:10]))
  except Exception:continue
 days=sorted({day for _,day in valid},reverse=True)
 keep=set(days[:retention])
 for path,day in valid:
  if day not in keep:path.unlink()

def backup(db):
 if not LOCK.acquire(blocking=False):raise ValueError('백업이 이미 진행 중입니다.')
 try:
  with db.transaction() as s:
   if s.bind.dialect.name!='sqlite':raise ValueError('사진 통합 백업은 SQLite 전용입니다.')
   cfg=config(s);dest=Path(cfg['backup_path']);dest.mkdir(parents=True,exist_ok=True)
   name='ScooterWarehouse-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.zip';target=dest/name
   manifest={'version':1,'created_at':stamp(),'files':{},'roots':cfg['roots'],'producer':'ScooterWarehouse-data-safety-1'}
   with tempfile.TemporaryDirectory(dir=dest) as tmp:
    snapshot=Path(tmp)/'warehouse.db'
    # BEGIN IMMEDIATE blocks app writers. Another read connection sees the last committed state.
    with closing(sqlite3.connect(s.bind.url.database)) as source,closing(sqlite3.connect(snapshot)) as output:source.backup(output)
    with zipfile.ZipFile(Path(tmp)/name,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
     def add(name,raw):z.writestr(name,raw);manifest['files'][name]={'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
     h=hashlib.sha256()
     with snapshot.open('rb') as source:
      while chunk:=source.read(1024*1024):h.update(chunk)
     z.write(snapshot,'warehouse.db');manifest['files']['warehouse.db']={'size':snapshot.stat().st_size,'sha256':h.hexdigest()}
     for row in s.scalars(select(Setting).where(Setting.key.startswith('used_media:'))):
      d=row.value
      if 'root_id' not in d:continue
      # Include soft-deleted/replaced originals for audit and recovery.
      for preview in [False,True]:
       raw,_,_=read_file(s,d,preview);rel=d['thumbnail'] if preview else d['path'];add('photos/'+d['root_id']+'/'+rel,raw)
     folders=set()
     for row in s.scalars(select(Setting).where(Setting.key.startswith('used_media:'))):
      d=row.value
      if 'root_id' in d:folders.add((d['root_id'],d['vehicle_id'],d['stay_id']))
     for root_id,vehicle_id,stay_id in folders:
      directory=safe(cfg['roots'][root_id],vehicle_id+'/'+stay_id+'/Metadata')
      for metadata in directory.glob('*.json'):add('photos/'+root_id+'/'+vehicle_id+'/'+stay_id+'/Metadata/'+metadata.name,metadata.read_bytes())
     # Preserve interrupted uploads not yet referenced by the DB for manual recovery.
     for root_id,root_path in cfg['roots'].items():
      for journal in (Path(root_path)/'.journal').glob('*.json'):
       if s.get(Setting,'photo_upload:'+journal.stem):continue
       raw_journal=journal.read_bytes();entry=json.loads(raw_journal)
       prefix='recovery/'+root_id+'/'+journal.stem+'/'
       add(prefix+'journal.json',raw_journal)
       for field in ['path','thumbnail']:
        source=safe(root_path,entry[field])
        if source.is_file():add(prefix+field+'/'+source.name,source.read_bytes())
     z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
    verify(Path(tmp)/name)
    os.replace(Path(tmp)/name,target)
   put(s,'photo_backup_status',{'ok':True,'at':stamp(),'file':str(target),'files':len(manifest['files'])})
  # Prune only our own verified-format archives, after a successful new backup.
  prune_verified(dest,cfg['retention'])
  return {'file':str(target),'files':len(manifest['files']),'at':manifest['created_at']}
 except Exception as e:
  failure={'ok':False,'at':stamp(),'error':'통합 백업 실패. 사진 누락·저장 공간·경로 권한을 확인하세요.'}
  try:
   if 'dest' in locals():failure['emergency_database']=emergency_database(db,dest)
  except Exception:failure['emergency_failed']=True
  try:
   with db.transaction() as s:
    previous=s.get(Setting,'photo_backup_status')
    if previous:failure['last_success_at']=previous.value.get('at') if previous.value.get('ok') else previous.value.get('last_success_at')
    put(s,'photo_backup_status',failure)
  except Exception:pass
  try:
   from .storage_paths import log_root
   folder=log_root(db);folder.mkdir(parents=True,exist_ok=True)
   atomic(folder/'backup-failure.json',json.dumps(failure,ensure_ascii=False).encode('utf-8'))
  except Exception:pass
  raise
 finally:LOCK.release()
def verify(path):
 with zipfile.ZipFile(path) as z:
  names=z.namelist()
  if len(names)!=len(set(names)):raise ValueError('중복 ZIP 항목')
  m=json.loads(z.read('manifest.json'))
  if m.get('version')!=1 or set(names)!=(set(m['files'])|{'manifest.json'}) or 'warehouse.db' not in m['files']:raise ValueError('백업 목록 오류')
  for name,item in m['files'].items():
   if name.startswith('/') or '..' in Path(name).parts or '\\' in name:raise ValueError('안전하지 않은 백업 경로')
   h=hashlib.sha256();size=0
   with z.open(name) as f:
    while chunk:=f.read(1024*1024):h.update(chunk);size+=len(chunk)
   if h.hexdigest()!=item['sha256'] or size!=item['size']:raise ValueError('백업 무결성 오류: '+name)
  return {'created_at':m['created_at'],'files':len(m['files']),'bytes':sum(v['size'] for v in m['files'].values()),'manifest':m}
def restore(path,destination,confirm=False):
 report=verify(path)
 if not confirm:return {k:v for k,v in report.items() if k!='manifest'}
 dest=Path(destination).resolve()
 if dest.exists():raise ValueError('복구 대상은 존재하지 않는 새 폴더여야 합니다. 운영 폴더는 덮어쓰지 않습니다.')
 dest.parent.mkdir(parents=True,exist_ok=True)
 tmp=Path(tempfile.mkdtemp(prefix='.restore-',dir=dest.parent))
 try:
  with zipfile.ZipFile(path) as z:
   for name in report['manifest']['files']:
    p=safe(tmp,name);p.parent.mkdir(parents=True,exist_ok=True)
    with z.open(name) as src,p.open('wb') as out:shutil.copyfileobj(src,out)
  with closing(sqlite3.connect(tmp/'warehouse.db')) as con:
   if con.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('복구 DB 무결성 오류')
   row=con.execute("SELECT value FROM settings WHERE key='photo_storage'").fetchone()
   if row:
    cfg=json.loads(row[0]);cfg['roots']={k:str(dest/'photos'/k) for k in cfg['roots']};cfg['backup_path']=str(dest/'Backups');cfg['daily']=False
    con.execute("UPDATE settings SET value=? WHERE key='photo_storage'",(json.dumps(cfg),))
   # Restored credentials must not retain live sessions from a backup.
   con.execute('DELETE FROM sessions');con.commit()
  os.replace(tmp,dest)
 except Exception:shutil.rmtree(tmp,ignore_errors=True);raise
 return {'restored_to':str(dest),'database':str(dest/'warehouse.db'),**{k:v for k,v in report.items() if k!='manifest'}}
def scheduler(db,stop):
 retry_after=0
 while not stop.wait(60):
  try:
   with db.transaction() as s:
    cfg=config(s);last=s.get(Setting,'photo_backup_status');last=last.value if last else {}
   if time.monotonic()<retry_after:continue
   if cfg.get('daily') and (not last.get('ok') or last.get('at','')[:10]!=stamp()[:10]):
    # Failed backup retries at most hourly; avoid filling the disk with emergency snapshots.
    if not last.get('ok') and last.get('at') and (datetime.fromisoformat(stamp())-datetime.fromisoformat(last['at'])).total_seconds()<3600:continue
    retry_after=time.monotonic()+3600
    backup(db)
  except Exception:pass # Failure persisted in photo_backup_status; no silent success.
