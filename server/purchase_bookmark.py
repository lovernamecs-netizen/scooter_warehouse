"""Immutable source-row review boundaries; does not alter the external workbook."""
from sqlalchemy import select
from .models import PurchaseReviewEvent,PurchaseRecord,Command,Guard
from .purchase_sheet import digest
from .domain import need,iso

def review(s,u,namespace,through):
 need(u.role in ('admin','worker'),'접근 권한이 없습니다.',403)
 need(isinstance(through,int) and 2<=through<=20000,'확정 마지막 행은 2~20,000입니다.')
 event=s.scalar(select(PurchaseReviewEvent).where(PurchaseReviewEvent.kind=='IMPORT',PurchaseReviewEvent.data['namespace'].as_string()==namespace).order_by(PurchaseReviewEvent.at.desc(),PurchaseReviewEvent.id.desc()).limit(1))
 need(event and event.data.get('bindings'),'연결된 원본을 먼저 가져오세요.')
 bindings=[b for b in event.data['bindings'] if b['row']<=through]
 need(bindings,'확정할 행이 없습니다.')
 from .purchase_sheet import current_query
 versions=dict(s.execute(current_query().with_only_columns(PurchaseRecord.record_id,PurchaseRecord.revision)).all())
 stale=bool(event.data.get('conflicts')) or any(versions.get(b['id'])!=b['revision'] for b in bindings)
 previous=s.scalar(select(PurchaseReviewEvent).where(PurchaseReviewEvent.kind=='SOURCE_CONFIRMED',PurchaseReviewEvent.data['namespace'].as_string()==namespace).order_by(PurchaseReviewEvent.at.desc()).limit(1))
 return {'namespace':namespace,'through':through,'import_id':event.id,'count':len(bindings),'stale':stale,'token':digest([event.id,through,bindings,[(b['id'],versions.get(b['id'])) for b in bindings]]),'bindings':bindings,'previous':{'through':previous.data['through'],'actor':previous.actor,'at':iso(previous.at)} if previous else None}

def confirm(s,u,p):
 need(u.role=='admin','원본 검토 확정은 관리자만 가능합니다.',403)
 request=p.get('request_id','');need(isinstance(request,str) and 16<=len(request)<=100,'요청 ID 오류');hashed=digest(p)
 old=s.get(Command,request)
 if old:need(old.user_id==u.id and old.digest==hashed,'요청 ID 충돌',409);return old.result
 reason=str(p.get('reason','')).strip();need(reason,'확정 사유를 입력하세요.')
 result=review(s,u,p.get('namespace'),p.get('through'))
 need(not result['stale'] and result['token']==p.get('token'),'원본 또는 프로그램 자료가 변경되었습니다. 다시 가져온 후 검토하세요.',409)
 event=PurchaseReviewEvent(kind='SOURCE_CONFIRMED',actor=u.username,data={'namespace':result['namespace'],'through':result['through'],'import_id':result['import_id'],'bindings':result['bindings'],'actor_id':u.id,'reason':reason});s.add(event);s.flush()
 out={'ok':True,'event_id':event.id,'count':result['count']};s.add(Command(id=request,user_id=u.id,digest=hashed,result=out));s.get(Guard,1).revision+=1;return out
