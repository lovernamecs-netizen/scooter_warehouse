"""Durable dispatch guards and one-at-a-time LibreSMS queue. Images cleared on completion."""
import base64,hashlib,json,time,uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select,String,Text,Float
from sqlalchemy.orm import Mapped,mapped_column
from .models import Base,User,Setting
from . import customer_privacy as privacy,insurance_libresms as libre
from .insurance_documents import InsuranceDocumentError

class InsuranceDispatch(Base):
    __tablename__='insurance_dispatches'
    id:Mapped[str]=mapped_column(String,primary_key=True)
    digest:Mapped[str]=mapped_column(String,index=True)
    fingerprint:Mapped[str]=mapped_column(String,unique=True)
    provider:Mapped[str]=mapped_column(String,index=True)
    device_id:Mapped[str]=mapped_column(String,default='phone1',index=True)
    state:Mapped[str]=mapped_column(String,index=True)
    payload:Mapped[str]=mapped_column(Text,default='')
    created:Mapped[float]=mapped_column(Float,index=True)
    retry_at:Mapped[float]=mapped_column(Float,default=0)
    note:Mapped[str]=mapped_column(String,default='')

QUEUED={'state':'queued','provider':'libresms','title':'전용폰 발송 대기열에 저장했습니다.','action':'연결 상태와 공용 발송 대기열을 확인하세요.','delivery_confirmed':False,'technical':{'code':'','detail':''}}
def semantic(phone,plate,message,image):return privacy.token(json.dumps([phone,plate,message,hashlib.sha256(image).hexdigest()],ensure_ascii=False))
def previous(s,ident,digest,provider):
    from .insurance_api import InsuranceSend
    exact=s.get(InsuranceDispatch,ident)
    if exact and (exact.digest!=digest or exact.provider!=provider):raise HTTPException(409,'다른 내용이나 발송 방식에 사용한 요청 번호입니다.')
    day=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat();fingerprint=day+':'+digest
    row=exact or s.scalar(select(InsuranceDispatch).where(InsuranceDispatch.digest==digest,InsuranceDispatch.state.in_(['queued','processing','unknown'])).order_by(InsuranceDispatch.created.desc()).limit(1)) or s.scalar(select(InsuranceDispatch).where(InsuranceDispatch.fingerprint==fingerprint))
    if row and row.state in ('failed','cancelled') and row.id!=ident:
        row.fingerprint='released:'+row.id;s.flush();row=None
    if row:
        old=s.get(InsuranceSend,row.id)
        return {**json.loads(privacy.decrypt(old.encrypted_detail))['result'],'state':row.state,'repeated_request':True,'request_id':row.id,'provider':row.provider},fingerprint
    return None,fingerprint

def enqueue(db,uid,data):
    from .insurance_api import InsuranceSend,settings,sms
    phone,plate,image,message=sms._validate(data);ident=str(data.get('request_id',''))
    try:uuid.UUID(ident)
    except ValueError:raise InsuranceDocumentError('발송 요청 번호를 확인하세요.') from None
    cfg=libre.config(db,data.get('device_id','phone1'));digest=semantic(phone,plate,message,image)
    with db.transaction() as s:
        old=s.get(InsuranceSend,ident)
        if old and not s.get(InsuranceDispatch,ident):raise HTTPException(409,'기존 CoolSMS 요청 번호입니다.')
        existing,fingerprint=previous(s,ident,digest,'libresms')
        if existing:return existing
        if not cfg['enabled']:raise InsuranceDocumentError('LibreSMS 시험 연결을 먼저 설정하고 사용으로 전환하세요.')
        # Check legacy CoolSMS reservations without modifying their snapshots.
        day=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
        for record in s.scalars(select(InsuranceSend).where((InsuranceSend.state=='unknown')|(InsuranceSend.fingerprint.startswith(day+':')))):
            if s.get(InsuranceDispatch,record.id):continue
            detail=json.loads(privacy.decrypt(record.encrypted_detail))
            legacy=privacy.token(json.dumps([phone,plate,message,detail.get('sender',''),hashlib.sha256(image).hexdigest()],ensure_ascii=False))
            if record.digest==legacy and record.state!='failed':return {**detail['result'],'repeated_request':True,'provider':'coolsms','request_id':record.id}
        detail={'plate':plate,'phone':phone,'sender':cfg['sender'],'message':message,'provider':'libresms','device':cfg['name'],'device_id':cfg['device_id'],'result':QUEUED}
        payload={'cfg':cfg,'phone':phone,'message':message,'image':base64.b64encode(image).decode('ascii')}
        s.add(InsuranceSend(id=ident,fingerprint='libresms:'+fingerprint,digest=digest,actor_id=uid,state='queued',encrypted_detail=privacy.encrypt(json.dumps(detail,ensure_ascii=False))))
        s.add(InsuranceDispatch(id=ident,digest=digest,fingerprint=fingerprint,provider='libresms',device_id=cfg['device_id'],state='queued',payload=privacy.encrypt(json.dumps(payload)),created=time.time(),retry_at=0,note=''))
        privacy.audit(s,type('Actor',(),{'id':uid})(),'LIBRESMS_QUEUED',ident)
    return {**QUEUED,'request_id':ident}

def finish(s,job,result):
    from .insurance_api import InsuranceSend
    row=s.get(InsuranceSend,job.id);detail=json.loads(privacy.decrypt(row.encrypted_detail));detail['result']=result
    row.state=result['state'];row.encrypted_detail=privacy.encrypt(json.dumps(detail,ensure_ascii=False));job.state=result['state'];job.payload='';job.note=result['title']
    privacy.audit(s,type('Actor',(),{'id':row.actor_id})(),'LIBRESMS_'+result['state'].upper(),job.id)

def recover(db):
    # Single production server process: interrupted HTTP calls are NEVER replayed.
    with db.transaction() as s:
        for job in s.scalars(select(InsuranceDispatch).where(InsuranceDispatch.provider=='libresms',InsuranceDispatch.state=='processing')):
            finish(s,job,{'state':'unknown','provider':'libresms','title':'서버 재시작 전 발송 결과 확인 필요','action':'전용폰과 수신자 확인 후 처리하세요. 자동 재발송하지 않습니다.','delivery_confirmed':False})

def process_once(db,device_id='phone1'):
    from .insurance_api import InsuranceSend
    cfg=libre.config(db,device_id)
    if not cfg['enabled']:return
    with db.read() as s:
        job=s.scalar(select(InsuranceDispatch).where(InsuranceDispatch.provider=='libresms',InsuranceDispatch.device_id==device_id,InsuranceDispatch.state=='queued').order_by(InsuranceDispatch.created,InsuranceDispatch.id).limit(1))
        if not job or job.retry_at>time.time():return
        ident=job.id;payload=json.loads(privacy.decrypt(job.payload))
    if any(payload['cfg'][k]!=cfg[k] for k in ('url','sender')):note='설정 변경 전 요청입니다. 기존 설정을 복원하거나 대기 요청을 취소하세요.'
    else:note='' if libre.health(cfg)['online'] else '휴대폰 오프라인 · 대기 유지'
    with db.transaction() as s:
        job=s.get(InsuranceDispatch,ident)
        if job.state!='queued':return
        current=s.get(Setting,libre.device_key(device_id))
        current=json.loads(privacy.decrypt(current.value['encrypted'])) if current else libre.DEFAULT
        if not current['enabled'] or any(current[k]!=cfg[k] for k in ('url','sender')):return
        delay=s.get(Setting,'libresms_next_send_at' if device_id=='phone1' else 'libresms_next_send_at_phone2')
        if delay and float(delay.value.get('at',0))>time.time():return
        if note:job.note=note;job.retry_at=time.time()+15;return
        if s.scalar(select(InsuranceDispatch.id).where(InsuranceDispatch.provider=='libresms',InsuranceDispatch.state=='processing').limit(1)):return
        row=s.get(InsuranceSend,ident);u=s.get(User,row.actor_id)
        if not u or not privacy.permissions(s,u)['customer_access']:
            finish(s,job,{'state':'cancelled','provider':'libresms','title':'요청자의 발송 권한이 해제되어 취소됨','delivery_confirmed':False});return
        job.state='processing';row.state='processing'
        detail=json.loads(privacy.decrypt(row.encrypted_detail));detail['result']={**QUEUED,'state':'processing','title':'전용폰 MMS 처리 중'};row.encrypted_detail=privacy.encrypt(json.dumps(detail,ensure_ascii=False))
    result=libre.send(payload['cfg'],payload['phone'],payload['message'],base64.b64decode(payload['image']))
    with db.transaction() as s:
        finish(s,s.get(InsuranceDispatch,ident),result)
        delay=s.get(Setting,'libresms_next_send_at' if device_id=='phone1' else 'libresms_next_send_at_phone2');value={'at':time.time()+cfg['interval']}
        if delay:delay.value=value
        else:s.add(Setting(key='libresms_next_send_at' if device_id=='phone1' else 'libresms_next_send_at_phone2',value=value))
        next_job=s.scalar(select(InsuranceDispatch).where(InsuranceDispatch.provider=='libresms',InsuranceDispatch.device_id==device_id,InsuranceDispatch.state=='queued').order_by(InsuranceDispatch.created,InsuranceDispatch.id).limit(1))
        if next_job:next_job.retry_at=max(next_job.retry_at,time.time()+cfg['interval'])

def scheduler(db,stop):
    recover(db)
    while not stop.wait(2):
        try:
            process_once(db,'phone1')
            process_once(db,'phone2')
        except Exception:pass # Reservation remains processing (never replayed); next restart marks unknown.

def queue(db):
    from .insurance_api import InsuranceSend
    with db.read() as s:
        base=select(InsuranceDispatch,InsuranceSend).join(InsuranceSend,InsuranceSend.id==InsuranceDispatch.id).where(InsuranceDispatch.provider=='libresms')
        rows=list(s.execute(base.where(InsuranceDispatch.state.in_(['queued','processing','unknown'])).order_by(InsuranceDispatch.created,InsuranceDispatch.id).limit(100)))
        rows+=list(s.execute(base.where(InsuranceDispatch.state.in_(['accepted','failed','cancelled'])).order_by(InsuranceDispatch.created.desc()).limit(20)))
        return [{'id':job.id,'state':job.state,'note':job.note,'actor_id':record.actor_id,**json.loads(privacy.decrypt(record.encrypted_detail))} for job,record in rows]

def cancel(db,uid,ident):
    with db.transaction() as s:
        job=s.get(InsuranceDispatch,ident)
        if not job or job.provider!='libresms':raise HTTPException(404,'대기 요청을 찾을 수 없습니다.')
        if job.state!='queued':raise HTTPException(409,'발송 대기 상태에서만 취소할 수 있습니다.')
        finish(s,job,{'state':'cancelled','provider':'libresms','title':'관리자가 대기 요청을 취소했습니다.','delivery_confirmed':False})
        privacy.audit(s,type('Actor',(),{'id':uid})(),'LIBRESMS_CANCELLED_BY',ident)
    return {'state':'cancelled'}
