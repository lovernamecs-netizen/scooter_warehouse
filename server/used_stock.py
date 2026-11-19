import base64,hashlib
from sqlalchemy import select
from .models import Vehicle,Stay,Setting
VIEWS={'front':'앞','rear':'뒤','left':'좌측면','right':'우측면','cockpit':'콕핏·주행거리','perspective':'퍼스펙티브'}
FIELDS=['mileage','exterior','pad_front','pad_rear','tire_front','tire_rear','oil_changed','oil_date','equipment_checked','repairs_done','description','equipment_notes','washed','damage']
def stay(s,v):
 active=s.scalar(select(Stay).where(Stay.vehicle_id==v.id,Stay.closed_at==None))
 return active or s.scalar(select(Stay).where(Stay.vehicle_id==v.id).order_by(Stay.closed_at.desc(),Stay.id.desc()))
def read(s,st):
 row=s.get(Setting,'used_profile:'+st.id) if st else None
 return dict(row.value) if row else {}
def missing(p):
 out=[]
 if not p.get('repairs_done'):out.append('정비 완료')
 if p.get('washed') is False or not p.get('washed'):out.append('세차 완료')
 if not p.get('oil_changed'):out.append('엔진오일 교환')
 return out

def put(s,key,value):
 row=s.get(Setting,key)
 if row:row.value=value
 else:s.add(Setting(key=key,value=value))

def summary(s,st):
 p=read(s,st)
 thumb_id=None
 if st:
  rows=list(s.scalars(select(Setting).where(Setting.key.startswith('used_media:'+st.id+':'))))
  active=[r.value for r in rows if isinstance(r.value,dict) and not r.value.get('deleted_at') and r.value.get('id')]
  whole=[d['id'] for d in active if d.get('category')=='intake' and d.get('key')=='whole']
  front=[d['id'] for d in active if d.get('key')=='front']
  any_photo=[d['id'] for d in active]
  thumb_id=(whole or front or any_photo or [None])[-1]
  if not thumb_id:
   for view in VIEWS:
    if s.get(Setting,'used_photo:'+st.id+':'+view):
     thumb_id='legacy:'+view;break
 return {'ready':bool(p.get('ready')),'mileage':p.get('mileage'),'exterior':p.get('exterior',''),'thumb_id':thumb_id,'stay_id':st.id if st else None,'status':'상품화 완료' if p.get('ready') else '상품화 진행' if p else '점검 미등록'}

def page(s,u,ident,stay_id=None):
 from .domain import get,need,vehicle_dto
 need(u.role!='ubis','권한이 없습니다.',403);v=get(s,Vehicle,ident);need(v.kind=='USED','중고차만 가능합니다.')
 st=get(s,Stay,stay_id) if stay_id else stay(s,v);need(not st or st.vehicle_id==v.id,'차량 입고 회차 오류',404);p=read(s,st);photos={}
 if st:
  for view in VIEWS:
   row=s.get(Setting,'used_photo:'+st.id+':'+view)
   if row:photos[view]=row.value
 media=[]
 if st:
  for row in s.scalars(select(Setting).where(Setting.key.startswith('used_media:'+st.id+':'))):
   if not row.value.get('deleted_at'):media.append({k:v for k,v in row.value.items() if k not in ['original','preview']})
 info=summary(s,st)
 registration=register(s,st) if st else ''
 dto=vehicle_dto(s,v,u)
 if 'equipment_notes' not in p and dto.get('equipment'):p['equipment_notes']='\n'.join(e['item']['name'] for e in dto.get('equipment',[]))
 return {'stays':[{'id':x.id,'received_at':str(x.received_at),'closed_at':str(x.closed_at) if x.closed_at else None} for x in s.scalars(select(Stay).where(Stay.vehicle_id==v.id).order_by(Stay.received_at.desc()))],'stay_id':st.id if st else None,'registration':registration,'media':media,'parts':PARTS,'vehicle':dto,'profile':p,'photos':photos,'views':VIEWS,'missing':missing(p),'ready':info['ready'],'publication_ready':info['ready'],'editable':bool(st and not st.closed_at and not v.archived and u.role in ['admin','worker'])}

def execute(s,u,action,p):
 from .domain import get,need,version,current_stay,clean,qty,valid_date,today,audit,iso,now
 need(u.role in ['admin','worker'],'상품화 수정 권한이 없습니다.',403)
 v=get(s,Vehicle,p.get('vehicle_id'));version(v,p);need(v.kind=='USED','중고차만 가능합니다.');st=current_stay(s,v)
 version_bumped=False
 if action=='used_profile':
  d=p.get('profile',{});need(isinstance(d,dict),'점검 정보 형식 오류')
  data={k:d.get(k) for k in FIELDS}
  for k in ['mileage','pad_front','pad_rear','tire_front','tire_rear']:
   if data[k] is not None and data[k]!='':qty(data[k],0,3000000 if k=='mileage' else 100)
   else:data[k]=None
  for k in ['exterior','description','equipment_notes']:data[k]=clean(data[k] or '',4000)
  data['oil_changed']=bool(d.get('oil_changed',False))
  data['equipment_checked']=bool(d.get('equipment_checked',True))
  data['repairs_done']=bool(d.get('repairs_done',False))
  data['washed']=bool(d.get('washed',False))
  damage=d.get('damage') or {}
  data['damage']={}
  if isinstance(damage,dict):
   for key,value in list(damage.items())[:40]:
    if key in PARTS and isinstance(value,dict):
     status=value.get('status','unchecked')
     if status in ['unchecked','normal','damaged','repaired']:
      data['damage'][key]={'status':status,'note':clean(value.get('note',''),1000)}
  data['oil_date']=valid_date(data['oil_date']) if data.get('oil_date') else (today() if data['oil_changed'] else '')
  need(not data['oil_date'] or data['oil_date']<=today(),'오일 교환일은 미래일 수 없습니다.')
  if p.get('complete') is True:
   miss=missing(data)
   need(not miss,'상품화 완료 전 필수 체크 항목을 확인하세요: '+', '.join(miss))
  data['ready']=p.get('complete') is True
  data.update(updated_at=iso(now()),actor=u.username)
  put(s,'used_profile:'+st.id,data)
  if not data['ready']:
   from .domain import invalidate
   invalidate(s,st)
  audit(s,u,'USED_READY' if data['ready'] else 'USED_INSPECTED',{'profile':data},v)
 elif action=='used_media':
  import uuid
  category=p.get('category');need(category in CATEGORIES,'사진 분류 오류')
  key=p.get('key','');need(key in CATEGORIES[category],'사진 부위 오류')
  prefix='used_media:'+st.id+':'
  if p.get('remove'):
   ident=p.get('id','');row=s.get(Setting,prefix+ident);need(row is not None,'사진이 없습니다.',404);row.value={**row.value,'deleted_at':iso(now()),'deleted_by':u.username}
  else:
   from .photo_store import upload
   raw,mime=decode_image(p.get('original',''))
   upload(s,u,v.id,st.id,p.get('upload_id') or str(uuid.uuid4()),category,key,raw)
   version_bumped=True
  audit(s,u,'USED_PHOTO_CHANGED',{'category':category,'key':key,'removed':bool(p.get('remove'))},v)
 elif action=='used_photo':
  view=p.get('view');need(view in VIEWS,'촬영 방향을 선택하세요.')
  key='used_photo:'+st.id+':'+view
  if p.get('remove'):
   row=s.get(Setting,key)
   if row:s.delete(row)
  else:
   encoded=p.get('jpeg','');need(isinstance(encoded,str) and len(encoded)<=1500000,'사진 크기를 줄여주세요.')
   try:raw=base64.b64decode(encoded,validate=True)
   except Exception:need(False,'사진 형식 오류')
   need(len(raw)<=1000000 and raw.startswith(b'\xff\xd8\xff') and raw.endswith(b'\xff\xd9'),'JPEG 사진만 등록할 수 있습니다.')
   put(s,key,{'jpeg':encoded,'at':iso(now()),'sha256':hashlib.sha256(raw).hexdigest()})
  audit(s,u,'USED_PHOTO_CHANGED',{'view':view,'removed':bool(p.get('remove'))},v)
 if not version_bumped:v.version+=1
 s.flush();return {'vehicle_id':v.id,'version':v.version}

PARTS={'front':'전면 카울','headlight':'헤드라이트','shield':'윈드스크린','mirror':'미러','handle':'핸들','floor':'발판','seat':'시트','rear':'후면 카울','left':'좌측 카울','right':'우측 카울','exhaust':'머플러','front_fender':'앞 펜더','rear_fender':'뒤 펜더'}
CATEGORIES={'intake':['whole','plate','vin','front','rear','left','right','cockpit','other'],'damage':list(PARTS),'wear':['pad_front','pad_rear','tire_front','tire_rear'],'product':['front','rear','left','right','cockpit','dashboard']}
def register(s,st):
 from .domain import day
 key='used_registration:'+st.id;row=s.get(Setting,key)
 if row:return row.value['number']
 stamp=day(st.received_at).replace('-','');seqkey='used_sequence:'+stamp;seq=s.get(Setting,seqkey);number=(seq.value['n'] if seq else 0)+1
 put(s,seqkey,{'n':number});value='USED-'+stamp+'-'+str(number).zfill(3);put(s,key,{'number':value});s.flush();return value

def decode_image(encoded,limit=25000000):
 from .domain import need
 need(isinstance(encoded,str) and len(encoded)<=limit*4//3+8,'사진은 25MB 이하로 선택하세요.')
 try:raw=base64.b64decode(encoded,validate=True)
 except Exception:need(False,'사진 형식 오류')
 is_heic=len(raw)>=12 and raw[4:8]==b'ftyp' and raw[8:12] in [b'heic',b'heix',b'hevc',b'hevx',b'mif1',b'msf1']
 mime='image/jpeg' if raw.startswith(b'\xff\xd8\xff') and raw.endswith(b'\xff\xd9') else 'image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else 'image/webp' if raw[:4]==b'RIFF' and raw[8:12]==b'WEBP' else 'image/heic' if is_heic else ''
 need(mime and len(raw)<=limit,'JPG, PNG, WebP 또는 HEIC 사진만 선택하세요.');return raw,mime

def media_download(s,u,ident,photo_id=None,category=None,preview=False,stay_id=None):
 import io,zipfile
 from .domain import get,need
 need(u.role!='ubis','권한이 없습니다.',403);v=get(s,Vehicle,ident);need(v.kind=='USED','중고차만 가능합니다.');st=get(s,Stay,stay_id) if stay_id else stay(s,v);need(st is not None and st.vehicle_id==v.id,'입고 이력이 없습니다.',404)
 prefix='used_media:'+st.id+':'
 if photo_id:
  row=s.get(Setting,prefix+photo_id);need(row is not None and not row.value.get('deleted_at'),'사진이 없습니다.',404);d=row.value
  if 'root_id' in d:
   from .photo_store import read_file
   return read_file(s,d,preview)
  content=s.get(Setting,'used_media_data:'+st.id+':'+photo_id);content=content.value if content else d;raw,mime=decode_image(content['preview'] if preview else content['original']);return raw,mime,d['category']+'-'+d['key']+'-'+photo_id[:8]+('.jpg' if mime=='image/jpeg' else '.png' if mime=='image/png' else '.webp')
 need(category in CATEGORIES or category=='all','사진 분류 오류')
 import tempfile
 buf=tempfile.TemporaryFile();count=0
 with zipfile.ZipFile(buf,'w',zipfile.ZIP_STORED) as z:
  if category=='all':
   import json
   meta=page(s,u,ident,st.id);meta.pop('photos',None);z.writestr('Metadata/vehicle.json',json.dumps(meta,ensure_ascii=False,default=str))
  for row in s.scalars(select(Setting).where(Setting.key.startswith(prefix))):
   d=row.value
   if d.get('deleted_at') or (category!='all' and d['category']!=category):continue
   if 'root_id' in d:
    from .photo_store import read_file
    raw,mime,name=read_file(s,d,preview);z.writestr(d['category']+'/'+name,raw);count+=1;continue
   content=s.get(Setting,'used_media_data:'+st.id+':'+d['id']);raw,mime=decode_image((content.value if content else d)['original']);ext={'image/jpeg':'jpg','image/png':'png','image/webp':'webp','image/heic':'heic'}[mime];z.writestr(d['category']+'/'+d['key']+'-'+d['id'][:8]+'.'+ext,raw);count+=1
  if category in ['all','product']:
   for view in VIEWS:
    row=s.get(Setting,'used_photo:'+st.id+':'+view)
    if row:z.writestr('previous-product/'+view+'.jpg',base64.b64decode(row.value['jpeg']));count+=1
 if not count:buf.close();need(False,'다운로드할 사진이 없습니다.',404)
 buf.seek(0);return buf,'application/zip',register(s,st)+'-'+category+'.zip'
