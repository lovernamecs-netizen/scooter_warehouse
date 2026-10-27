"""Append-only local revisions and review approvals. No remote writes."""
import copy
from sqlalchemy import select
from .models import PurchaseRecord,PurchaseReviewEvent,Command,Guard,Master
from .domain import need,valid_date,today,iso
from .purchase_sheet import latest,digest,preview,apply,ALL_FIELDS,number

def view(s):
 records=latest(s)
 events=list(s.scalars(select(PurchaseReviewEvent).order_by(PurchaseReviewEvent.at,PurchaseReviewEvent.id)))
 approvals=[e for e in events if e.kind=='CONFIRM']
 approved={}
 for e in approvals:approved.update(e.data['versions'])
 return {'events':[{'id':e.id,'kind':e.kind,'data':e.data,'actor':e.actor,'at':iso(e.at),'stale':any(records.get(k) is None or records[k].revision!=v for k,v in e.data.get('versions',{}).items()) or any(k not in e.data.get('versions',{}) and r.data['values'].get('received_date') and r.data['values']['received_date']<=e.data.get('through','') for k,r in records.items())} for e in events],
 'changes':[{'id':r.record_id,'revision':r.revision,'source':r.data['source'],'deleted':bool(r.data.get('deleted')),'actor':r.actor,'at':iso(r.at),'reviewed':approved.get(r.record_id)==r.revision} for r in records.values()]}

def mutate(s,u,p):
 need(u.role in ['admin','worker'],'변경 권한이 없습니다.',403)
 request=p.get('request_id','');need(isinstance(request,str) and 16<=len(request)<=100,'요청 ID 오류')
 hashed=digest(p);old=s.get(Command,request)
 if old:need(old.user_id==u.id and old.digest==hashed,'요청 ID 충돌',409);return old.result
 kind=p.get('action');conflict=None
 if kind=='resolve_import':
  conflict=s.get(PurchaseReviewEvent,p.get('event_id'))
  need(conflict and conflict.kind=='IMPORT_CONFLICT','원본 차이를 찾을 수 없습니다.',404)
  need(not s.scalar(select(PurchaseReviewEvent.id).where(PurchaseReviewEvent.kind=='IMPORT_RESOLVED',PurchaseReviewEvent.data['event_id'].as_string()==conflict.id)),'이미 처리된 차이입니다.',409)
  need(p.get('choice') in ('keep','source'),'처리 방법을 선택하세요.')
  p={**p,'id':conflict.data['record_id'],'revision':conflict.data['revision'],'source':conflict.data['incoming']}
  kind='edit' if p['choice']=='source' else 'keep'
 reason=str(p.get('reason','')).strip();need(reason,'변경 또는 확정 사유를 입력하세요.')
 records=latest(s)
 if kind=='confirm':
  need(u.role=='admin','검토 확정은 관리자만 가능합니다.',403)
  through=p.get('through','');valid_date(through);need(through<=today(),'미래 날짜는 확정할 수 없습니다.')
  versions={k:r.revision for k,r in records.items() if r.data['values'].get('received_date') and r.data['values']['received_date']<=through}
  need(versions and (p.get('versions')==versions or p.get('review_token')==digest([through,versions])),'검토 대상이 변경되었습니다. 목록을 새로 확인하세요.',409)
  event=PurchaseReviewEvent(kind='CONFIRM',data={'through':through,'versions':versions,'reason':reason,'actor_id':u.id},actor=u.username);s.add(event);s.flush();result={'ok':True,'event_id':event.id}
 else:
  rec=records.get(p.get('id'));need(rec,'자료를 찾을 수 없습니다.',404)
  if conflict and kind=='keep' and rec.revision!=p.get('revision'):
   result={'ok':True,'revision':rec.revision}
   s.add(PurchaseReviewEvent(kind='IMPORT_RESOLVED',data={'event_id':conflict.id,'record_id':rec.record_id,'choice':'dismiss_stale','actor_id':u.id,'reason':reason},actor=u.username))
   s.add(Command(id=request,user_id=u.id,digest=hashed,result=result));s.get(Guard,1).revision+=1;return result
  need(rec.revision==p.get('revision'),'다른 사용자가 변경했습니다. 새로고침하세요.',409)
  data=copy.deepcopy(rec.data);vehicle_id=rec.vehicle_id;stay_id=rec.stay_id
  if kind=='keep':pass
  elif kind=='delete':need(not data.get('deleted'),'이미 삭제된 자료입니다.');data['deleted']=True
  elif kind=='restore':
   origin=s.scalar(select(PurchaseRecord).where(PurchaseRecord.record_id==rec.record_id,PurchaseRecord.revision==p.get('restore_revision')))
   need(origin and not origin.data.get('deleted'),'복구할 정상 버전을 선택하세요.')
   data=copy.deepcopy(origin.data);vehicle_id=origin.vehicle_id;stay_id=origin.stay_id
  elif kind=='edit':
   need(not data.get('deleted'),'삭제 자료는 먼저 복구하세요.')
   source=p.get('source');need(isinstance(source,dict) and set(source)==set(ALL_FIELDS) and all(isinstance(v,str) and len(v)<=10000 for v in source.values()),'17개 항목 입력 형식 오류')
   # A source-only edit does not mutate operational vehicle identifiers or stays.
   values=dict(source);pending=False
   for key in ('invoice_date','received_date'):
    try:
     if values[key]:valid_date(values[key])
    except Exception:values[key]='';pending=pending or key=='received_date'
   for key in ('vat_included','vat_excluded'):
    try:values[key]=number(values[key])
    except Exception:values[key]=None
   if values['vin']!=rec.data['values']['vin'] or values['received_date']!=rec.data['values']['received_date']:vehicle_id=None;stay_id=None
   from .domain import vin
   try:vin(values['vin'])
   except Exception:pending=True
   for key in ('model','color'):
    name='368G-V2' if key=='model' and values[key]=='존테스368T-G-V2' else values[key]
    master=s.scalar(select(Master).where(Master.kind==key,Master.name==name,Master.active==True))
    data[key+'_id']=master.id if master else None
   if any(source.get(k)!=rec.data['source'].get(k) for k in ('vat_included','vat_excluded')):
    effective=p.get('value_effective_day') or today();valid_date(effective);data['value_effective_day']=effective
   data.update(source=source,values=values,pending=pending or not values['received_date'] or values['received_date']>today(),status='수정 자료')
  else:need(False,'지원하지 않는 작업입니다.')
  data['local_override']=not (conflict and p['choice']=='source')
  if conflict:
   data['import_baseline']=copy.deepcopy(conflict.data['incoming']);data['import_decision']=digest(conflict.data['incoming'])
  if stay_id:need(not any(r.record_id!=rec.record_id and r.stay_id==stay_id and not r.data.get('deleted') for r in records.values()),'다른 자료가 동일 입고 회차에 연결되어 있습니다. 연결을 확인하세요.',409)
  new=PurchaseRecord(record_id=rec.record_id,revision=rec.revision+1,source_key=rec.source_key,data=data,vehicle_id=vehicle_id,stay_id=stay_id,actor=u.username);s.add(new)
  s.add(PurchaseReviewEvent(kind=kind.upper(),data={'record_id':rec.record_id,'before':rec.revision,'after':new.revision,'restore_revision':p.get('restore_revision'),'reason':reason,'actor_id':u.id},actor=u.username))
  result={'ok':True,'revision':new.revision}
 if conflict:s.add(PurchaseReviewEvent(kind='IMPORT_RESOLVED',data={'event_id':conflict.id,'record_id':rec.record_id,'choice':p['choice'],'actor_id':u.id,'reason':reason},actor=u.username))
 s.add(Command(id=request,user_id=u.id,digest=hashed,result=result));s.get(Guard,1).revision+=1
 return result

def import_all(s,u,p):
 import uuid
 need(u.role in ['admin','worker'],'변경 권한이 없습니다.',403)
 request=p.get('request_id','');need(isinstance(request,str) and 16<=len(request)<=100,'요청 ID 오류')
 hashed=digest(p);old=s.get(Command,request)
 if old:need(old.user_id==u.id and old.digest==hashed,'요청 ID 충돌',409);return old.result
 rows=p.get('rows');need(isinstance(rows,list) and len(rows)<=20000,'파일 행 수 제한을 확인하세요.')
 result={'ok':True,'saved':0,'unchanged':0,'protected':0,'conflicts':0}
 namespace=p.get('source_namespace') or digest([p.get('google_source',{}).get('file_id') or p.get('filename') or 'legacy-upload',p['sheet']])
 need(isinstance(namespace,str) and len(namespace)<=200,'원본 연결 오류')
 records=latest(s)
 candidates=[r for r in records.values() if r.data.get('import_source',{}).get('namespace')==namespace or (not r.data.get('import_source',{}).get('namespace') and namespace=='legacy:'+r.data.get('import_source',{}).get('sheet',''))]
 # Resolve exact content first, then a unique business identity. Never bind by row position.
 def identity(source):return tuple(str(source.get(k,'')).strip() for k in ('invoice_date','supplier','representative','received_date','region','model','vin','color'))
 matches={};used=set()
 resolved=set(s.scalars(select(PurchaseReviewEvent.data['event_id'].as_string()).where(PurchaseReviewEvent.kind=='IMPORT_RESOLVED')))
 open_conflicts={(e.data['record_id'],e.data['revision'],digest(e.data['incoming'])) for e in s.scalars(select(PurchaseReviewEvent).where(PurchaseReviewEvent.kind=='IMPORT_CONFLICT')) if e.id not in resolved}
 exact_index={};identity_index={}
 for record in candidates:
  exact_index.setdefault(digest(record.data.get('import_baseline',record.data['source'])),[]).append(record)
  identity_index.setdefault(identity(record.data.get('import_baseline',record.data['source'])),[]).append(record)
 for index,row in enumerate(rows):
  exact=exact_index.get(digest(row['data']),[])
  related=exact or identity_index.get(identity(row['data']),[])
  related=[r for r in related if r.record_id not in used]
  if exact and len(related)>1:related=sorted(related,key=lambda r:(r.data.get('import_source',{}).get('row',0),r.record_id))[:1]
  if len(related)==1:
   record=related[0];matches[index]=record.record_id;used.add(record.record_id)
   if record.data.get('local_override') or record.data.get('deleted'):
    result['protected']+=1
    if record.data['source']!=row['data'] and record.data.get('import_decision')!=digest(row['data']):
     result['conflicts']+=1
     if (record.record_id,record.revision,digest(row['data'])) not in open_conflicts:s.add(PurchaseReviewEvent(kind='IMPORT_CONFLICT',data={'record_id':record.record_id,'revision':record.revision,'incoming':row['data'],'namespace':namespace,'request_id':request,'actor_id':u.id},actor=u.username))
  elif related:
   need(False,'원본 행 연결이 모호합니다. 동일 자료를 구분한 후 다시 가져오세요.',409)

 # A changed unidentified row must not silently become a duplicate of an old row.
 for index,row in enumerate(rows):
  if index not in matches:
   displaced=[r for r in candidates if r.record_id not in used and r.data.get('import_source',{}).get('row')==row['row']]
   need(not displaced,'기존 원본 행의 식별 정보가 변경되었습니다. 원본 차종·VIN·입고일 연결을 확인한 후 다시 가져오세요.',409)
 s.info['_purchase_records']=records;s.info['_purchase_bindings']=[]
 for offset in range(0,len(rows),250):
  chunk=rows[offset:offset+250]
  body={'rows':[r['data'] for r in chunk],'choices':{str(i):{**({'record_id':matches[offset+i]} if offset+i in matches else {}),'import_source':{'namespace':namespace,'label':(p.get('filename') or 'Google 원본')+' · '+p['sheet'],'source_cells':r.get('source_cells',{}),'kind':'XLSX','sha256':p['sha256'],'sheet':p['sheet'],'row':r['row'],'source_identity':r['source_identity'],'duplicate_identity':r['duplicate_identity']}} for i,r in enumerate(chunk)},'reason':'전체 원본 파일 가져오기','request_id':str(uuid.uuid5(uuid.NAMESPACE_URL,request+':'+str(offset)))}
  check=preview(s,u,body);body['token']=check['token'];done=apply(s,u,body,_checked=check)
  for key in ('saved','unchanged'):result[key]+=done[key]
 bindings=s.info.get('_purchase_bindings',[])
 linked={b['row']:b['id'] for b in bindings}
 s.add(PurchaseReviewEvent(kind='SOURCE_READ',actor=u.username,data={'namespace':namespace,'label':(p.get('filename') or 'Google 원본')+' · '+p['sheet'],'sha256':p['sha256'],'actor_id':u.id,'rows':[{'row':r['row'],'record_id':linked.get(r['row']),'source':r['data']} for r in rows]}))
 s.info.pop('_purchase_records',None)
 s.add(PurchaseReviewEvent(kind='IMPORT',data={'sha256':p['sha256'],'sheet':p['sheet'],'namespace':namespace,'actor_id':u.id,'count':len(rows),'bindings':s.info.pop('_purchase_bindings',[]),**result},actor=u.username))
 s.add(Command(id=request,user_id=u.id,digest=hashed,result=result))
 return result

def summary(s,u,through,page=0):
 from sqlalchemy import func
 from .purchase_sheet import current_query
 need(u.role in ('admin','worker'),'접근 권한이 없습니다.',403)
 valid_date(through);need(0<=page<=100000,'페이지 오류')
 date=PurchaseRecord.data['values']['received_date'].as_string()
 q=current_query().where(date!='',date<=through)
 versions=dict(s.execute(q.with_only_columns(PurchaseRecord.record_id,PurchaseRecord.revision)).all())
 rows=list(s.scalars(q.order_by(PurchaseRecord.record_id).offset(page*50).limit(50)))
 events=list(s.scalars(select(PurchaseReviewEvent).where(PurchaseReviewEvent.kind=='CONFIRM').order_by(PurchaseReviewEvent.at.desc()).limit(20)))
 return {'through':through,'count':len(versions),'page':page,'token':digest([through,versions]),'changes':[{'id':r.record_id,'revision':r.revision,'source':r.data['source'],'deleted':bool(r.data.get('deleted')),'actor':r.actor} for r in rows],'events':[{'actor':e.actor,'at':iso(e.at),'data':{'through':e.data['through']},'stale':e.data.get('versions')!=dict(s.execute(current_query().where(date!='',date<=e.data['through']).with_only_columns(PurchaseRecord.record_id,PurchaseRecord.revision)).all())} for e in events]}

def conflicts(s,u,page=0):
 from sqlalchemy import func
 need(u.role in ('admin','worker'),'접근 권한이 없습니다.',403);need(0<=page<=100000,'페이지 오류')
 resolved=select(PurchaseReviewEvent.data['event_id'].as_string()).where(PurchaseReviewEvent.kind=='IMPORT_RESOLVED')
 q=select(PurchaseReviewEvent).where(PurchaseReviewEvent.kind=='IMPORT_CONFLICT',PurchaseReviewEvent.id.not_in(resolved))
 count=s.scalar(select(func.count()).select_from(q.subquery()))
 rows=[]
 for event in s.scalars(q.order_by(PurchaseReviewEvent.at.desc(),PurchaseReviewEvent.id).offset(page*50).limit(50)):
  rec=s.scalar(select(PurchaseRecord).where(PurchaseRecord.record_id==event.data['record_id']).order_by(PurchaseRecord.revision.desc()).limit(1))
  rows.append({'id':event.id,'record_id':rec.record_id,'current':rec.data['source'],'incoming':event.data['incoming'],'deleted':bool(rec.data.get('deleted')),'stale':rec.revision!=event.data['revision'],'actor':event.actor,'at':iso(event.at)})
 return {'count':count,'page':page,'rows':rows}
