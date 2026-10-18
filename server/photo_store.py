"""Immutable originals; transactional metadata with recoverable filesystem journals."""
import io, os, json, hashlib, uuid, shutil, tempfile, warnings
from pathlib import Path
from datetime import datetime, timezone
from PIL import Image, ImageOps
from sqlalchemy import select
from .models import Setting, Vehicle, Stay, Guard
from .domain import need, get, audit, iso, now
from .used_stock import put, CATEGORIES
try:
 import pillow_heif
 pillow_heif.register_heif_opener()
except ImportError:
 pass
LIMIT=25_000_000

def stamp():return datetime.now(timezone.utc).isoformat()
def digest(raw):return hashlib.sha256(raw).hexdigest()
def config(s):
 row=s.get(Setting,'photo_storage')
 if row:return dict(row.value)
 db=Path(s.bind.url.database or 'warehouse.db').resolve()
 root=db.parent/'Data'/'Vehicles'
 return {'active':'default','roots':{'default':str(root)},'backup_path':str(db.parent/'Backups'),'retention':7,'daily':False}
def safe(root,relative):
 p=Path(root).resolve()/relative
 p=p.resolve();need(p.is_relative_to(Path(root).resolve()),'잘못된 파일 경로',422)
 return p
def atomic(path,raw):
 path.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(prefix='.write-',dir=path.parent)
 try:
  with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def checked(raw):
 need(0<len(raw)<=LIMIT,'원본 사진은 25MB 이하이어야 합니다.',413)
 try:
  with warnings.catch_warnings():
   warnings.simplefilter('error',Image.DecompressionBombWarning)
   with Image.open(io.BytesIO(raw)) as im:
    fmt=im.format;w,h=im.size
    need(fmt in ['JPEG','PNG','WEBP','HEIF','HEIC'],'JPEG, PNG, WebP, HEIC 사진만 지원합니다.',415)
    need(w>0 and h>0 and w*h<=100_000_000,'사진 해상도 범위 초과',422)
    im.load();orientation=im.getexif().get(274,1)
    thumb=ImageOps.exif_transpose(im);thumb.thumbnail((1100,1100));thumb=thumb.convert('RGB')
    b=io.BytesIO();thumb.save(b,'JPEG',quality=82)
    return {'width':w,'height':h,'orientation':orientation,'format':fmt,'mime':{'JPEG':'image/jpeg','PNG':'image/png','WEBP':'image/webp','HEIF':'image/heic','HEIC':'image/heic'}[fmt],'ext':{'JPEG':'jpg','PNG':'png','WEBP':'webp','HEIF':'heic','HEIC':'heic'}[fmt]},b.getvalue()
 except Exception as e:
  from fastapi import HTTPException
  if isinstance(e,HTTPException):raise
  need(False,'사진을 해독할 수 없습니다. HEIC 지원 설치 또는 JPEG 촬영 설정을 확인하세요.',415)
def upload(s,u,vehicle_id,stay_id,upload_id,category,key,raw,captured_at='',expected_hash='',migration=False):
 need(u.role in ['admin','worker'],'사진 등록 권한이 없습니다.',403)
 try:ident=str(uuid.UUID(upload_id))
 except (ValueError,TypeError,AttributeError):need(False,'업로드 ID 형식 오류')
 sha=digest(raw);need(not expected_hash or sha==expected_hash,'사진 SHA-256 불일치',422)
 existing=s.get(Setting,'photo_upload:'+ident)
 if existing:
  d=existing.value;need(d['sha256']==sha and d['vehicle_id']==vehicle_id and d['stay_id']==stay_id and d['category']==category and d['key']==key,'동일 업로드 ID의 다른 사진 요청',409)
  read_file(s,d);return d
 v=get(s,Vehicle,vehicle_id);st=get(s,Stay,stay_id)
 need(st.vehicle_id==v.id and v.kind=='USED','차량·입고 회차 불일치',409)
 need(migration or (not st.closed_at and not v.archived),'종료된 입고 회차입니다. 원본은 휴대폰에 보관됩니다.',409)
 need(category in CATEGORIES and (key in CATEGORIES[category] or migration and key=='perspective'),'사진 부위 오류')
 meta,preview=checked(raw);cfg=config(s);root=Path(cfg['roots'][cfg['active']]);root.mkdir(parents=True,exist_ok=True)
 need(shutil.disk_usage(root).free>len(raw)*2+50_000_000,'PC 사진 저장 공간이 부족합니다.',507)
 prefix='used_media:'+st.id+':'
 rows=list(s.scalars(select(Setting).where(Setting.key.startswith(prefix))))
 need(migration or sum(not r.value.get('deleted_at') for r in rows)<100,'회차당 사진은 최대 100장입니다.')
 folder={'damage':'Damage','intake':'Inspection','wear':'Inspection','product':'Product'}[category]
 rel=f'{v.id}/{st.id}/{folder}/{key}_{ident}.{meta.pop("ext")}'
 d={'id':ident,'upload_id':ident,'vehicle_id':v.id,'stay_id':st.id,'category':category,'key':key,'root_id':cfg['active'],'path':rel,'thumbnail':f'{v.id}/{st.id}/Thumbnails/{key}_{ident}.jpg','size':len(raw),'sha256':sha,'at':stamp(),'captured_at':captured_at[:100] or stamp(),'actor':u.username,'status':'saved',**meta}
 journal=root/'.journal'/(ident+'.json');atomic(journal,json.dumps(d,ensure_ascii=False).encode())
 from .domain import vehicle_dto
 from .used_stock import read
 metadata={'vehicle':vehicle_dto(s,v,u),'stay_id':st.id,'photo':d,'profile':read(s,st)}
 atomic(safe(root,f'{v.id}/{st.id}/Metadata/{ident}.json'),json.dumps(metadata,ensure_ascii=False,default=str).encode())
 target=safe(root,rel)
 if target.exists():need(digest(target.read_bytes())==sha,'동일 파일 이름의 내용 충돌',409)
 else:atomic(target,raw)
 atomic(safe(root,d['thumbnail']),preview)
 if category=='product' and not migration:
  for old in rows:
   if old.value['category']==category and old.value['key']==key and not old.value.get('deleted_at'):old.value={**old.value,'deleted_at':stamp(),'replaced_by':ident}
 put(s,prefix+ident,d);put(s,'photo_upload:'+ident,d);put(s,'photo_storage',cfg)
 audit(s,u,'USED_PHOTO_STORED',{'photo_id':ident,'stay_id':st.id,'sha256':sha,'size':len(raw)},v)
 v.version+=1;s.get(Guard,1).revision+=1;s.flush()
 # Journal retained intentionally: recovery can distinguish committed and uncommitted files.
 return d

def read_file(s,d,preview=False):
 root=config(s)['roots'].get(d['root_id']);need(root,'사진 저장 경로 설정이 없습니다.',503)
 p=safe(root,d['thumbnail'] if preview else d['path']);need(p.is_file(),'원본 파일이 없습니다. 백업/저장 경로를 확인하세요.',503)
 raw=p.read_bytes()
 if not preview:need(digest(raw)==d['sha256'],'원본 파일 무결성 오류',503)
 return raw,'image/jpeg' if preview else d['mime'],p.name

def status(s):
 cfg=config(s);roots=[];failures=[]
 for ident,path in cfg['roots'].items():
  p=Path(path);parent=p
  while not parent.exists() and parent!=parent.parent:parent=parent.parent
  roots.append({'id':ident,'path':path,'exists':p.exists(),'free':shutil.disk_usage(parent).free})
  if p.exists():
   for j in (p/'.journal').glob('*.json'):
    if not s.get(Setting,'photo_upload:'+j.stem):failures.append({'id':j.stem,'state':'파일 기록 후 DB 미확정','journal':str(j)})
 for r in s.scalars(select(Setting).where(Setting.key.startswith('used_media:'))):
  if 'root_id' in r.value:
   try:read_file(s,r.value)
   except Exception:failures.append({'id':r.value['id'],'state':'원본 누락 또는 무결성 오류'})
 last=s.get(Setting,'photo_backup_status')
 return {**cfg,'storage':roots,'failures':failures,'backup':last.value if last else {}}
def configure(s,p):
 cfg=config(s)
 for field in ['root','backup_path']:
  if field not in p:continue
  path=Path(p[field]).expanduser();need(path.is_absolute(),'저장 경로는 PC의 절대 경로로 입력하세요.')
  path.mkdir(parents=True,exist_ok=True)
  fd,test=tempfile.mkstemp(dir=path);os.close(fd);os.unlink(test)
  if field=='root':
   ident=digest(str(path.resolve()).encode())[:16];cfg['roots']={**cfg['roots'],ident:str(path.resolve())};cfg['active']=ident
  else:cfg[field]=str(path.resolve())
 if 'retention' in p:need(type(p['retention']) is int and 1<=p['retention']<=90,'보존 개수는 1~90입니다.');cfg['retention']=p['retention']
 if 'daily' in p:need(type(p['daily']) is bool,'자동 백업 설정 오류');cfg['daily']=p['daily']
 put(s,'photo_storage',cfg);return cfg
