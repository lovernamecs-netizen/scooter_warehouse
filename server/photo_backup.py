"""Consistent SQLite + immutable photo backup; verified restore to a NEW directory."""
import hashlib,json,sqlite3,tempfile,zipfile,os,shutil,threading,time
from pathlib import Path
from contextlib import closing
from datetime import datetime
from sqlalchemy import select
from .models import Setting
from .photo_store import config,stamp,safe,atomic
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
  # Capture the DB and immutable file inventory under a short writer reservation.
  # Compression and verification never hold the operational database writer lock.
  with db.read() as s:
   if s.bind.dialect.name!='sqlite':raise ValueError('사진 통합 백업은 SQLite 전용입니다.')
   initial=config(s);dest=Path(initial['backup_path']);dest.mkdir(parents=True,exist_ok=True)
  name='ScooterWarehouse-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.zip';target=dest/name
  with tempfile.TemporaryDirectory(dir=dest) as tmp:
   snapshot=Path(tmp)/'warehouse.db';files=[]
   with db.transaction() as s:
    cfg=config(s)
    if cfg!=initial:raise ValueError('백업 설정이 변경되었습니다. 다시 실행하세요.')
    manifest={'version':1,'created_at':stamp(),'files':{},'roots':cfg['roots'],'producer':'ScooterWarehouse-data-safety-1'}
    with closing(sqlite3.connect(s.bind.url.database)) as source,closing(sqlite3.connect(snapshot)) as output:source.backup(output)
    folders=set()
    for row in s.scalars(select(Setting).where(Setting.key.startswith('used_media:'))):
     d=row.value
     if 'root_id' not in d:continue
     root=cfg['roots'][d['root_id']]
     files.append(('photos/'+d['root_id']+'/'+d['path'],safe(root,d['path']),d['sha256']))
     files.append(('photos/'+d['root_id']+'/'+d['thumbnail'],safe(root,d['thumbnail']),None))
     folders.add((d['root_id'],d['vehicle_id'],d['stay_id']))
    for root_id,vehicle_id,stay_id in folders:
     directory=safe(cfg['roots'][root_id],vehicle_id+'/'+stay_id+'/Metadata')
     for metadata in directory.glob('*.json'):files.append(('photos/'+root_id+'/'+vehicle_id+'/'+stay_id+'/Metadata/'+metadata.name,metadata,None))
    for root_id,root_path in cfg['roots'].items():
     for journal in (Path(root_path)/'.journal').glob('*.json'):
      if s.get(Setting,'photo_upload:'+journal.stem):continue
      raw=journal.read_bytes();entry=json.loads(raw);prefix='recovery/'+root_id+'/'+journal.stem+'/'
      files.append((prefix+'journal.json',raw,None))
      for field in ['path','thumbnail']:
       source=safe(root_path,entry[field])
       if source.is_file():files.append((prefix+field+'/'+source.name,source,None))
    from .insurance_library import InsuranceDocument,config as library_config,MARKER,marker_ok
    library=library_config(s)
    manifest['insurance_roots']=library['roots']
    for ident,folder in library['roots'].items():
     if not marker_ok(folder,ident):raise ValueError('공용 증권 저장 경로 확인 필요')
     files.append(('insurance/'+ident+'/'+MARKER,Path(folder)/MARKER,None))
    for doc in s.scalars(select(InsuranceDocument)):
     files.append(('insurance/'+doc.root_id+'/'+doc.file,safe(library['roots'][doc.root_id],doc.file),doc.cipher_digest))
   with closing(sqlite3.connect(snapshot)) as output:
    if output.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('백업 DB 무결성 오류')
   with zipfile.ZipFile(Path(tmp)/name,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
    for archive,source,expected in [('warehouse.db',snapshot,None),*files]:
     h=hashlib.sha256();size=0
     if isinstance(source,bytes):z.writestr(archive,source);h.update(source);size=len(source)
     else:
      with source.open('rb') as src,z.open(archive,'w',force_zip64=True) as dst:
       while chunk:=src.read(1024*1024):dst.write(chunk);h.update(chunk);size+=len(chunk)
     if expected and h.hexdigest()!=expected:raise ValueError('원본 파일 무결성 오류')
     manifest['files'][archive]={'size':size,'sha256':h.hexdigest()}
    z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
   verify(Path(tmp)/name);os.replace(Path(tmp)/name,target)
  status={'ok':True,'at':stamp(),'file':str(target),'files':len(manifest['files']),'last_success_at':manifest['created_at']}
  with db.transaction() as s:put(s,'photo_backup_status',status)
  # Cleanup failure must not mislabel a verified backup or generate emergency copies.
  try:prune_verified(dest,cfg['retention'])
  except Exception:
   status['cleanup_warning']='백업은 완료됐지만 오래된 백업 정리에 실패했습니다. 경로 권한과 저장 공간을 확인하세요.'
   with db.transaction() as s:put(s,'photo_backup_status',status)
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
   library=con.execute("SELECT value FROM settings WHERE key='insurance_library_storage'").fetchone()
   if library:
    cfg=json.loads(library[0]);cfg['roots']={k:str(dest/'insurance'/k) for k in cfg['roots']}
    con.execute("UPDATE settings SET value=? WHERE key='insurance_library_storage'",(json.dumps(cfg),))
   # Restored queue may predate successful sends on the original server: NEVER replay it.
   if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='insurance_dispatches'").fetchone():
    con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('libresms_restore_hold',?)",(json.dumps({'held':True}),))
    con.execute("UPDATE insurance_dispatches SET state='unknown',payload='',note='복구본의 이전 요청: 실제 발송 여부 확인 필요' WHERE provider='libresms' AND state IN ('queued','processing')")
    con.execute("UPDATE insurance_sends SET state='unknown' WHERE id IN (SELECT id FROM insurance_dispatches WHERE provider='libresms' AND state='unknown')")
   # Restored credentials must not retain live sessions from a backup.
   con.execute('DELETE FROM sessions');con.commit()
  os.replace(tmp,dest)
 except Exception:shutil.rmtree(tmp,ignore_errors=True);raise
 return {'restored_to':str(dest),'database':str(dest/'warehouse.db'),**{k:v for k,v in report.items() if k!='manifest'}}
def scheduler(db,stop):
 last_attempt=0.0
 last_attempt=0.0
 retry_after=0
 while not stop.wait(60):
  try:
   with db.read() as s:
    cfg=config(s);last=s.get(Setting,'photo_backup_status');last=last.value if last else {}
   if time.monotonic()<retry_after:continue
   if cfg.get('daily') and (not last.get('ok') or last.get('at','')[:10]!=stamp()[:10]):
    # Failed backup retries at most hourly; avoid filling the disk with emergency snapshots.
    if not last.get('ok') and last.get('at') and (datetime.fromisoformat(stamp())-datetime.fromisoformat(last['at'])).total_seconds()<3600:continue
    retry_after=time.monotonic()+3600
    backup(db)
  except Exception:pass # Failure persisted in photo_backup_status; no silent success.
