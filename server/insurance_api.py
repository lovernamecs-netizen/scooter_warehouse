"""Isolated document tools with existing customer grants and durable send reservations."""
import hashlib,json,threading,uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import File,UploadFile,Request,HTTPException
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse
from starlette.background import BackgroundTask
from sqlalchemy import select,String,Text,DateTime
from sqlalchemy.orm import Mapped,mapped_column
from .models import Base,now,User
from . import customer_privacy as privacy
from .insurance_documents import InsuranceDocumentError,convert_pdf,iter_pdf,parse_contacts,MAX_PDF_BYTES,MAX_CONTACT_BYTES
from . import insurance_settings as settings,insurance_coolsms as sms

class InsuranceSend(Base):
    __tablename__='insurance_sends'
    id: Mapped[str]=mapped_column(String,primary_key=True)
    fingerprint: Mapped[str]=mapped_column(String,unique=True)
    digest: Mapped[str]=mapped_column(String,index=True)
    actor_id: Mapped[str]=mapped_column(String)
    state: Mapped[str]=mapped_column(String)
    encrypted_detail: Mapped[str]=mapped_column(Text)
    at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,index=True)

_conversion=threading.BoundedSemaphore(1)
_settings_lock=threading.Lock()
UNKNOWN={'state':'unknown','title':'발송 접수 여부를 확인해야 합니다.','action':'CoolSMS 콘솔에서 확인하기 전 다시 발송하지 마세요.','delivery_confirmed':False,'technical':{'code':'','detail':'전송 진행 중 또는 응답 미확인'}}

def send(db,uid,data):
    phone,plate,image,message=sms._validate(data)
    request_id=str(data.get('request_id',''))
    try:uuid.UUID(request_id)
    except ValueError:raise InsuranceDocumentError('발송 요청 번호를 확인하세요.') from None
    _,_,sender=settings.credentials()
    digest=privacy.token(json.dumps([phone,plate,message,sender,hashlib.sha256(image).hexdigest()],ensure_ascii=False))
    day=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    fingerprint=day+':'+digest
    detail={'plate':plate,'phone':phone,'sender':sender,'message':message,'result':UNKNOWN}
    with db.transaction() as s:
        existing=s.get(InsuranceSend,request_id)
        if existing and existing.digest!=digest:raise HTTPException(409,'다른 내용에 사용한 발송 요청 번호입니다.')
        existing=existing or s.scalar(select(InsuranceSend).where(InsuranceSend.digest==digest,InsuranceSend.state=='unknown').order_by(InsuranceSend.at.desc()).limit(1))
        existing=existing or s.scalar(select(InsuranceSend).where(InsuranceSend.fingerprint==fingerprint))
        if existing and existing.state=='failed' and existing.id!=request_id:
            existing.fingerprint='failed:'+existing.id
            s.flush();existing=None
        if existing:return {**json.loads(privacy.decrypt(existing.encrypted_detail))['result'],'repeated_request':True}
        s.add(InsuranceSend(id=request_id,fingerprint=fingerprint,digest=digest,actor_id=uid,state='unknown',encrypted_detail=privacy.encrypt(json.dumps(detail,ensure_ascii=False))))
        privacy.audit(s,type('Actor',(),{'id':uid})(),'INSURANCE_SEND_RESERVED',request_id)
    # No DB writer lock during provider I/O. A crash leaves an unknown reservation.
    result=sms.send_one(data)
    detail['result']=result
    with db.transaction() as s:
        row=s.get(InsuranceSend,request_id);row.state=result['state'];row.encrypted_detail=privacy.encrypt(json.dumps(detail,ensure_ascii=False))
        privacy.audit(s,type('Actor',(),{'id':uid})(),'INSURANCE_SEND_'+result['state'].upper(),request_id)
    return result

def install(app,db,user):
    def access(request):
        with db.read() as s:
            u=user(s,request);privacy.allowed(s,u);return u.id
    def call(fn,*args):
        try:return fn(*args)
        except InsuranceDocumentError as exc:raise HTTPException(422,str(exc)) from None

    @app.post('/api/insurance/convert')
    async def convert(request:Request,file:UploadFile=File(...)):
        access(request)
        try:
            if not (file.filename or '').lower().endswith('.pdf'):raise HTTPException(422,'PDF 파일을 선택하세요.')
            if not _conversion.acquire(blocking=False):raise HTTPException(429,'다른 문서를 변환 중입니다. 완료 후 다시 시도하세요.')
            streaming=False
            try:
                data=await file.read(MAX_PDF_BYTES+1)
                if request.query_params.get('stream')!='1':return await run_in_threadpool(call,convert_pdf,data)
                events=iter_pdf(data)
                first=await run_in_threadpool(call,next,events)
                released=False
                def cleanup():
                    nonlocal released
                    if not released:
                        released=True
                        events.close()
                        _conversion.release()
                def lines():
                    try:
                        yield json.dumps(first)+'\n'
                        for event in events:yield json.dumps(event,ensure_ascii=False)+'\n'
                    except InsuranceDocumentError as exc:yield json.dumps({'type':'error','message':str(exc)},ensure_ascii=False)+'\n'
                    except Exception:yield json.dumps({'type':'error','message':'PDF 변환이 중단됐습니다. 원본 파일을 확인하고 다시 시도하세요.'},ensure_ascii=False)+'\n'
                    finally:cleanup()
                response=StreamingResponse(lines(),media_type='application/x-ndjson',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'},background=BackgroundTask(cleanup))
                streaming=True
                return response
            finally:
                if not streaming:_conversion.release()
        finally:await file.close()

    @app.post('/api/insurance/contacts')
    async def contacts(request:Request,file:UploadFile=File(...)):
        access(request)
        try:
            data=await file.read(MAX_CONTACT_BYTES+1)
            return await run_in_threadpool(call,parse_contacts,file.filename or '',data)
        finally:await file.close()

    @app.get('/api/insurance/mms/settings')
    def config(request:Request):access(request);return settings.public_settings()

    @app.put('/api/insurance/mms/settings')
    def account(p:dict,request:Request):
        uid=access(request)
        with _settings_lock:result=call(settings.save_account,p)
        with db.transaction() as s:privacy.audit(s,type('Actor',(),{'id':uid})(),'INSURANCE_ACCOUNT_CHANGED')
        return result

    @app.put('/api/insurance/mms/template')
    def template(p:dict,request:Request):
        uid=access(request)
        with _settings_lock:result=call(settings.save_template,p.get('msg_template',''))
        with db.transaction() as s:privacy.audit(s,type('Actor',(),{'id':uid})(),'INSURANCE_TEMPLATE_CHANGED')
        return result

    @app.post('/api/insurance/mms/send')
    def dispatch(p:dict,request:Request):return call(send,db,access(request),p)

    @app.get('/api/insurance/mms/history')
    def history(request:Request):
        uid=access(request)
        with db.transaction() as s:
            privacy.audit(s,type('Actor',(),{'id':uid})(),'INSURANCE_HISTORY_READ')
            rows=s.execute(select(InsuranceSend,User.username).outerjoin(User,InsuranceSend.actor_id==User.id).order_by(InsuranceSend.at.desc(),InsuranceSend.id).limit(50))
            return [{'id':r.id,'at':r.at,'actor_id':r.actor_id,'actor':name or '이전 계정','state':r.state,**json.loads(privacy.decrypt(r.encrypted_detail))} for r,name in rows]

    @app.post('/api/insurance/mms/explain')
    def explain(p:dict,request:Request):
        from .insurance_mms import explain_failure
        access(request);return explain_failure(p.get('code',''),p.get('detail',''))
