"""Public error contract and bounded, value-free diagnostic tracebacks."""
import errno,logging,traceback,uuid,threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

MESSAGES={401:'로그인이 필요하거나 만료되었습니다. 다시 로그인하세요.',403:'이 작업을 수행할 권한이 없습니다. 관리자에게 요청해주세요.',413:'요청 용량이 너무 큽니다. 사진 크기를 확인해주세요.',415:'지원하지 않는 파일 형식입니다.',422:'입력 내용을 확인해주세요.',429:'요청이 많습니다. 잠시 후 다시 시도해주세요.'}
def install(app,db):
    from .storage_paths import log_root
    folder=log_root(db) if db.sqlite else Path('logs').resolve()
    lock=threading.Lock()
    def diagnostic(request,exc):
        # A dedicated handler avoids host logging configuration leaking exception arguments.
        try:
            with lock:
                folder.mkdir(parents=True,exist_ok=True)
                handler=RotatingFileHandler(folder/'errors.log',maxBytes=1024*1024,backupCount=3,encoding='utf-8')
                try:
                    frames='\n'.join(f'{Path(f.filename).name}:{f.lineno} {f.name}' for f in traceback.extract_tb(exc.__traceback__))
                    record=logging.LogRecord('warehouse.safe',logging.ERROR,'',0,'request_id=%s type=%s\n%s',(request.state.request_id,type(exc).__name__,frames),None)
                    handler.emit(record)
                finally:handler.close()
        except OSError:pass
    def response(request,status,message,code=None,detail=None,fields=None):
        ident=getattr(request.state,'request_id',uuid.uuid4().hex)
        return JSONResponse(status_code=status,content={'detail':message if detail is None else detail,'code':code or 'HTTP_'+str(status),'message':message,'request_id':ident,'field_errors':fields or {},'retryable':False},headers={'X-Request-ID':ident})
    @app.exception_handler(HTTPException)
    async def http_error(request,exc):
        d=exc.detail
        message=d if isinstance(d,str) else d.get('message') if isinstance(d,dict) else None
        if exc.status_code>=500:message='요청을 처리하지 못했습니다. 오류 번호를 관리자에게 전달해주세요.';d=message
        return response(request,exc.status_code,message or MESSAGES.get(exc.status_code,'요청을 처리하지 못했습니다.'),detail=d)
    @app.exception_handler(RequestValidationError)
    async def validation(request,exc):
        known={'username','password','vin','scheduled','vehicle_id','stay_id','file','upload_id','category','key'}
        fields={str(e['loc'][-1]):'입력값을 확인해주세요.' for e in exc.errors() if e.get('loc') and str(e['loc'][-1]) in known}
        return response(request,422,MESSAGES[422],'VALIDATION_ERROR',fields=fields)
    def unexpected(request,exc):
        diagnostic(request,exc)
        disk=isinstance(exc,OSError) and exc.errno==errno.ENOSPC
        return response(request,503 if disk else 500,'사진 저장 공간이 부족합니다. 저장 공간을 확인한 뒤 다시 시도해주세요.' if disk else '요청을 처리하지 못했습니다. 오류 번호를 관리자에게 전달해주세요.','STORAGE_FULL' if disk else 'INTERNAL_ERROR')
    app.state.error_response=response;app.state.unexpected_error=unexpected
