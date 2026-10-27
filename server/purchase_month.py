"""Monthly source reconciliation and immutable month approvals."""
from collections import Counter,defaultdict
from sqlalchemy import select,func
from .models import PurchaseReviewEvent,PurchaseRecord,Command,Guard
from .purchase_sheet import latest,digest,ALL_FIELDS
from .domain import need,valid_date,today,iso

def month_valid(month):
 valid_date(month+'-01');return month

def key(source):
 vin=str(source.get('vin','')).strip().upper()
 return (vin,str(source.get('received_date','')).strip()) if len(vin)==17 else None

def scan(s,u,month,page=0,namespace='',full_snapshot=False):
 need(u.role in ('admin','worker'),'접근 권한이 없습니다.',403);month_valid(month);need(0<=page<=100000,'페이지 오류')
 records=latest(s)
 ranked=select(PurchaseReviewEvent.id.label('id'),func.row_number().over(partition_by=PurchaseReviewEvent.data['namespace'].as_string(),order_by=(PurchaseReviewEvent.at.desc(),PurchaseReviewEvent.id.desc())).label('rn')).where(PurchaseReviewEvent.kind=='SOURCE_READ').subquery()
 events=list(s.scalars(select(PurchaseReviewEvent).join(ranked,PurchaseReviewEvent.id==ranked.c.id).where(ranked.c.rn==1)))
 sources={}
 for event in events:
  if not namespace or event.data['namespace']==namespace:sources[event.data['namespace']]=event
 source_rows=[]
 for event in sources.values():
  for row in event.data['rows']:source_rows.append({**row,'namespace':event.data['namespace']})
 # Legacy imports are a reference only, not a claim of a fresh external read.
 legacy=not bool(sources)
 if legacy:
  for rec in records.values():
   if rec.data.get('import_source') and (not namespace or rec.data['import_source'].get('namespace')==namespace):source_rows.append({'record_id':rec.record_id,'source':rec.data.get('import_baseline',rec.data['source']),'row':rec.data['import_source'].get('row'),'namespace':rec.data['import_source'].get('namespace','legacy')})
 by_id=defaultdict(list);by_key=defaultdict(list)
 for row in source_rows:
  if row.get('record_id'):by_id[row['record_id']].append(row)
  if key(row['source']):by_key[key(row['source'])].append(row)
 groups=defaultdict(list)
 for rec in records.values():
  if not rec.data.get('deleted') and key(rec.data['source']):groups[key(rec.data['source'])].append(rec.record_id)
 results=[];used=set();versions={}
 for rec in records.values():
  info=rec.data.get('import_source',{})
  if namespace and info.get('namespace')!=namespace:continue
  found=by_id.get(rec.record_id) or by_key.get(key(rec.data['source']),[])
  if not rec.data['source'].get('received_date','').startswith(month) and not any(r['source'].get('received_date','').startswith(month) for r in found):continue
  versions[rec.record_id]=rec.revision
  for row in found:used.add(id(row))
  incoming=found[0]['source'] if found else None
  diff=[k for k in ALL_FIELDS if incoming is not None and str(incoming.get(k,''))!=str(rec.data['source'].get(k,''))]
  duplicate=len(groups.get(key(rec.data['source']),[]))>1
  ambiguous=len({digest(r['source']) for r in found})>1
  status='시트에만 있음' if rec.data.get('deleted') and incoming else '삭제 기록' if rec.data.get('deleted') else '프로그램에만 있음' if incoming is None else '원본 연결 확인' if ambiguous else '항목 차이' if diff else '동일 차량 중복' if duplicate else '차량 식별 전' if not key(rec.data['source']) else '일치'
  results.append({'id':rec.record_id,'revision':rec.revision,'status':status,'current':rec.data['source'],'source':incoming,'fields':diff,'duplicate':duplicate,'source_rows':[{'namespace':r['namespace'],'row':r.get('row')} for r in found]})
 for row in source_rows:
  if id(row) not in used and row['source'].get('received_date','').startswith(month):results.append({'id':None,'status':'시트에만 있음','current':None,'source':row['source'],'fields':[],'duplicate':False,'source_rows':[{'namespace':row['namespace'],'row':row.get('row')}]})
 counts=dict(Counter(r['status'] for r in results));signature=digest([month,namespace,results,versions])
 previous=s.scalar(select(PurchaseReviewEvent).where(PurchaseReviewEvent.kind=='MONTH_CONFIRMED',PurchaseReviewEvent.data['month'].as_string()==month,PurchaseReviewEvent.data['namespace'].as_string()==namespace).order_by(PurchaseReviewEvent.at.desc(),PurchaseReviewEvent.id.desc()).limit(1))
 return {**({'snapshot_rows':results,'versions':versions} if full_snapshot else {}),'month':month,'namespace':namespace,'token':signature,'count':len(results),'counts':counts,'page':page,'rows':results[page*50:(page+1)*50],'legacy_reference':legacy,'source_reads':[{'at':iso(e.at),'actor':e.actor,'label':e.data.get('label',e.data['namespace'])} for e in sources.values()],'undated':sum(not r['source'].get('received_date') for r in source_rows),'approval':{'actor':previous.actor,'at':iso(previous.at),'stale':previous.data['token']!=signature,'id':previous.id} if previous else None}

def confirm(s,u,p):
 need(u.role=='admin','월 확정은 관리자만 가능합니다.',403)
 rid=p.get('request_id','');need(isinstance(rid,str) and 16<=len(rid)<=100,'요청 ID 오류');hashed=digest(p);old=s.get(Command,rid)
 if old:need(old.user_id==u.id and old.digest==hashed,'요청 ID 충돌',409);return old.result
 result=scan(s,u,p.get('month',''),namespace=p.get('namespace',''),full_snapshot=True)
 need(result['month']<=today()[:7],'미래 월은 확정할 수 없습니다.')
 need(result['token']==p.get('token'),'자료가 변경됐습니다. 월 대조를 다시 실행하세요.',409)
 need(str(p.get('reason','')).strip(),'확정 사유를 입력하세요.')
 need(p.get('acknowledged') is True,'차이·미식별 자료와 원본 읽은 시점을 확인하세요.')
 event=PurchaseReviewEvent(kind='MONTH_CONFIRMED',actor=u.username,data={k:result[k] for k in ('month','namespace','token','count','counts','source_reads','undated','legacy_reference','snapshot_rows','versions')});event.data={**event.data,'actor_id':u.id,'reason':p['reason']};s.add(event);s.flush()
 response={'ok':True,'event_id':event.id};s.add(Command(id=rid,user_id=u.id,digest=hashed,result=response));s.get(Guard,1).revision+=1;return response

def store_source(s,u,p):
 need(u.role in ('admin','worker'),'접근 권한이 없습니다.',403)
 rid=p.get('request_id','');need(isinstance(rid,str) and 16<=len(rid)<=100,'요청 ID 오류');hashed=digest(p);old=s.get(Command,rid)
 if old:need(old.user_id==u.id and old.digest==hashed,'요청 ID 충돌',409);return old.result
 rows=p.get('rows');need(isinstance(rows,list) and len(rows)<=20000,'원본 행 수 오류')
 namespace=p.get('source_namespace') or digest([(p.get('google_source') or {}).get('file_id') or p.get('filename'),p.get('sheet')])
 records=latest(s);index=defaultdict(list)
 for rec in records.values():
  info=rec.data.get('import_source',{});ns=info.get('namespace') or 'legacy:'+info.get('sheet','')
  if ns==namespace:index[key(rec.data.get('import_baseline',rec.data['source']))].append(rec)
 saved=[]
 for row in rows:
  source=row.get('data');need(isinstance(source,dict) and set(source)<=set(ALL_FIELDS) and all(isinstance(v,str) and len(v)<=10000 for v in source.values()),'원본 항목 오류')
  candidates=index.get(key(source),[]) if key(source) else []
  saved.append({'row':row.get('row'),'source':source,'record_id':candidates[0].record_id if len(candidates)==1 else None})
 event=PurchaseReviewEvent(kind='SOURCE_READ',actor=u.username,data={'namespace':namespace,'label':(p.get('filename') or 'Google 원본')+' · '+str(p.get('sheet','')),'rows':saved,'sha256':p.get('sha256'),'actor_id':u.id,'scan_only':True});s.add(event);s.flush()
 result={'ok':True,'event_id':event.id,'count':len(saved)};s.add(Command(id=rid,user_id=u.id,digest=hashed,result=result));return result

def approvals(s,u,month):
 need(u.role in ('admin','worker'),'접근 권한이 없습니다.',403);month_valid(month)
 return {'rows':[{'id':e.id,'actor':e.actor,'at':iso(e.at),'reason':e.data['reason'],'counts':e.data['counts']} for e in s.scalars(select(PurchaseReviewEvent).where(PurchaseReviewEvent.kind=='MONTH_CONFIRMED',PurchaseReviewEvent.data['month'].as_string()==month).order_by(PurchaseReviewEvent.at.desc()).limit(50))]}

def approved_snapshot(s,u,ident,page=0):
 need(u.role in ('admin','worker'),'접근 권한이 없습니다.',403);need(0<=page<=100000,'페이지 오류')
 e=s.get(PurchaseReviewEvent,ident);need(e and e.kind=='MONTH_CONFIRMED','확정 기록이 없습니다.',404)
 rows=e.data.get('snapshot_rows',[])
 return {'month':e.data['month'],'actor':e.actor,'at':iso(e.at),'count':len(rows),'page':page,'rows':rows[page*50:(page+1)*50]}
