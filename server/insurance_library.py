"""Admin-only encrypted shared JPEG library. Immutable files, indexed search, paged reads."""
import base64,hashlib,hmac,io,json,os,re,time,unicodedata,uuid
from pathlib import Path
from types import SimpleNamespace
from cryptography.fernet import Fernet,InvalidToken
from fastapi import HTTPException,Request
from starlette.responses import Response
from sqlalchemy import select,func,String,Text,Integer,Index
from sqlalchemy.orm import Mapped,mapped_column
from .models import Base,Setting,User,now
from . import customer_privacy as privacy
from .photo_store import atomic,safe

SETTING='insurance_library_storage'
MARKER='.warehouse-insurance.json'
LIMIT=199000
class InsuranceDocument(Base):
    __tablename__='insurance_documents'
    id:Mapped[str]=mapped_column(String,primary_key=True)
    digest:Mapped[str]=mapped_column(String,unique=True)
    plate_token:Mapped[str]=mapped_column(String,index=True)
    root_id:Mapped[str]=mapped_column(String)
    file:Mapped[str]=mapped_column(String)
    encrypted_meta:Mapped[str]=mapped_column(Text)
    cipher_digest:Mapped[str]=mapped_column(String)
    size:Mapped[int]=mapped_column(Integer)
    actor_id:Mapped[str]=mapped_column(String)
    created_at:Mapped[str]=mapped_column(String)
class InsuranceDocumentSearch(Base):
    __tablename__='insurance_document_search'
    document_id:Mapped[str]=mapped_column(String,primary_key=True)
    term:Mapped[str]=mapped_column(String,primary_key=True)
Index('ix_insurance_document_term',InsuranceDocumentSearch.term,InsuranceDocumentSearch.document_id)

def require_admin(u):
    if not u.active or u.role!='admin':raise HTTPException(403,'관리자만 공용 증권함을 사용할 수 있습니다.')

def normalized(value):return re.sub(r'[\s_\-]','',unicodedata.normalize('NFKC',str(value or '')).casefold())
def hashed_terms(values):
    key=base64.urlsafe_b64decode(privacy.key())
    return {hmac.new(key,b'customer-search-v1\0insurance-search:'+value.encode('utf8'),hashlib.sha256).hexdigest() for value in values}
def terms(value):
    value=normalized(value)
    return hashed_terms({value[i:i+n] for n in (1,2,3) for i in range(len(value)-n+1)})
def query_terms(value):
    value=normalized(value);n=min(3,len(value))
    return hashed_terms({value[i:i+n] for i in range(len(value)-n+1)}) if n else set()
def config(s):
    row=s.get(Setting,SETTING)
    return dict(row.value) if row else {'active':'','roots':{}}
def default_path(db):
    from .storage_paths import data_root
    return str((data_root() or Path(db.engine.url.database).resolve().parent/'Data')/'InsuranceDocuments')
def marker_ok(folder,ident):
    try:return json.loads((Path(folder)/MARKER).read_text(encoding='utf8'))=={'library_root':ident}
    except (OSError,ValueError):return False

def configure(db,u,path):
    require_admin(u);path=str(path).strip()
    if not path or not Path(path).is_absolute() or path.startswith(('\\\\','//')):raise HTTPException(422,'서버 PC의 절대 경로를 입력하세요. 네트워크 공유 경로는 지원하지 않습니다.')
    folder=Path(path).resolve()
    project=Path(__file__).resolve().parents[1]
    if folder.is_relative_to(project) and not folder.is_relative_to(project/'Data'):
        raise HTTPException(422,'프로그램 폴더 안에서는 Data 하위의 전용 폴더를 선택하세요.')
    for protected in [Path(__file__).resolve().parents[1]/'web',Path(__file__).resolve().parents[1]/'.git']:
        if folder==protected or folder.is_relative_to(protected):raise HTTPException(422,'프로그램 공개 폴더는 저장 경로로 사용할 수 없습니다.')
    try:
        with db.transaction() as s:
            cfg=config(s);roots=dict(cfg['roots'])
            ident=next((k for k,v in roots.items() if Path(v).resolve()==folder),None)
            if ident:
                if not marker_ok(folder,ident):raise HTTPException(409,'기존 저장 폴더를 확인할 수 없습니다. 위치나 연결 상태를 확인하세요.')
            else:
                if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):raise HTTPException(409,'새 경로는 비어 있는 전용 폴더를 선택하세요. 기존 파일은 변경하지 않습니다.')
                folder.mkdir(parents=True,exist_ok=True);ident=uuid.uuid4().hex
                atomic(folder/MARKER,json.dumps({'library_root':ident}).encode())
            # Check write permission without altering any existing file.
            probe=folder/('.probe-'+uuid.uuid4().hex)
            with probe.open('xb') as out:out.write(b'1');out.flush();os.fsync(out.fileno())
            probe.unlink()
            roots[ident]=str(folder);new={'active':ident,'roots':roots}
            row=s.get(Setting,SETTING)
            if row:row.value=new
            else:s.add(Setting(key=SETTING,value=new))
            privacy.audit(s,u,'INSURANCE_STORAGE_CHANGED',ident)
            return {**new,'path':str(folder),'default_path':default_path(db)}
    except OSError:raise HTTPException(503,'저장 경로의 접근 권한과 디스크 상태를 확인하세요.') from None

def metadata(row,cipher=None):
    if cipher is None:return json.loads(privacy.decrypt(row.encrypted_meta))
    try:return json.loads(cipher.decrypt(row.encrypted_meta.encode('ascii')))
    except (InvalidToken,ValueError):raise HTTPException(503,'증권 메타데이터 암호화 키를 확인하세요.') from None
def dto(s,row):
    meta=metadata(row)
    count=s.scalar(select(func.count()).select_from(InsuranceDocument).where(InsuranceDocument.plate_token==row.plate_token)) if row.plate_token else 1
    actor=s.get(User,row.actor_id)
    return {'id':row.id,**meta,'size_bytes':row.size,'created_at':row.created_at,'actor':actor.username if actor else '이전 계정','same_plate_count':count}

def validate(data):
    raw=str(data.get('jpeg_base64',''))
    if len(raw)>LIMIT*2:raise HTTPException(413,'공용 증권 JPEG는 199,000바이트 이하여야 합니다.')
    try:
        raw=base64.b64decode(raw,validate=True)
        if not 0<len(raw)<=LIMIT:raise ValueError()
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as im:
            if im.format!='JPEG' or im.width>1500 or im.height>1440:raise ValueError()
            im.verify()
    except Exception:raise HTTPException(422,'199,000바이트 이하, 최대 1500×1440 크기의 올바른 JPEG가 필요합니다.') from None
    source=str(data.get('source','')).strip();plate=re.sub(r'[\s-]','',unicodedata.normalize('NFKC',str(data.get('plate',''))))
    if not source or len(source)>240 or len(plate)>64:raise HTTPException(422,'파일명과 차량번호 길이를 확인하세요.')
    try:page=max(1,min(500,int(data.get('page',1))))
    except (ValueError,TypeError):raise HTTPException(422,'페이지 번호를 확인하세요.') from None
    return raw,{'source':source,'plate':plate,'page':page,'review_required':bool(data.get('review_required',True))}

def save(db,u,data):
    require_admin(u);raw,meta=validate(data);digest=hashlib.sha256(raw).hexdigest()
    with db.transaction() as s:
        existing=s.scalar(select(InsuranceDocument).where(InsuranceDocument.digest==digest))
        if existing:
            result=dto(s,existing);privacy.audit(s,u,'INSURANCE_DOCUMENT_DUPLICATE',existing.id)
            return {'duplicate':True,'metadata_differs':result['plate']!=meta['plate'] or result['source']!=meta['source'],'document':result}
        cfg=config(s);ident=cfg.get('active');root=cfg['roots'].get(ident)
        if not root:raise HTTPException(409,'공용 증권 저장 경로를 먼저 설정하세요.')
        if not marker_ok(root,ident):raise HTTPException(503,'공용 증권 폴더를 사용할 수 없습니다. 경로를 확인하세요.')
        key=privacy.key();docid=f'{time.time_ns():020d}'+uuid.uuid4().hex
        ciphertext=Fernet(key).encrypt(raw);filename=docid+'.enc'
        # Unique immutable target. DB failures can leave an unreferenced encrypted file, never a broken committed record.
        try:atomic(safe(root,filename),ciphertext)
        except OSError:raise HTTPException(503,'증권 저장에 실패했습니다. 저장 공간과 폴더 권한을 확인하세요.') from None
        row=InsuranceDocument(id=docid,digest=digest,plate_token=privacy.token('insurance-plate:'+normalized(meta['plate'])) if meta['plate'] else '',root_id=ident,file=filename,encrypted_meta=privacy.encrypt(json.dumps(meta,ensure_ascii=False)),cipher_digest=hashlib.sha256(ciphertext).hexdigest(),size=len(raw),actor_id=u.id,created_at=now().isoformat())
        s.add(row);s.flush()
        for term in terms(meta['source'])|terms(meta['plate']):s.add(InsuranceDocumentSearch(document_id=docid,term=term))
        privacy.audit(s,u,'INSURANCE_DOCUMENT_SAVED',docid)
        return {'duplicate':False,'metadata_differs':False,'document':dto(s,row)}

def listing(db,u,q='',cursor=''):
    require_admin(u)
    if len(q)>80 or (cursor and not re.fullmatch(r'[a-f0-9]{52}',cursor)):raise HTTPException(422,'검색 조건을 확인하세요.')
    with db.read() as s:
        statement=select(InsuranceDocument)
        ts=query_terms(q)
        if ts:
            matches=select(InsuranceDocumentSearch.document_id).where(InsuranceDocumentSearch.term.in_(ts)).group_by(InsuranceDocumentSearch.document_id).having(func.count()==len(ts))
            statement=statement.where(InsuranceDocument.id.in_(matches))
        if cursor:statement=statement.where(InsuranceDocument.id<cursor)
        result=[];last=cursor;more=False;cipher=Fernet(privacy.key())
        # Indexed candidates, bounded chunks; exact comparison removes n-gram false positives.
        while len(result)<=50:
            batch=list(s.scalars((statement.where(InsuranceDocument.id<last) if last else statement).order_by(InsuranceDocument.id.desc()).limit(100)))
            if not batch:break
            for row in batch:
                last=row.id;meta=metadata(row,cipher)
                if q and not any(normalized(q) in normalized(meta[k]) for k in ('plate','source')):continue
                if len(result)==50:more=True;break
                result.append((row,meta))
            if more or len(batch)<100:break
        tokens={row.plate_token for row,_ in result if row.plate_token}
        counts=dict(s.execute(select(InsuranceDocument.plate_token,func.count()).where(InsuranceDocument.plate_token.in_(tokens)).group_by(InsuranceDocument.plate_token)).all()) if tokens else {}
        names=dict(s.execute(select(User.id,User.username).where(User.id.in_({row.actor_id for row,_ in result}))).all()) if result else {}
        documents=[{'id':row.id,**meta,'size_bytes':row.size,'created_at':row.created_at,'actor':names.get(row.actor_id,'이전 계정'),'same_plate_count':counts.get(row.plate_token,1)} for row,meta in result]
        return {'documents':documents,'next_cursor':result[-1][0].id if more else '', 'page_size':50}

def content(db,u,ident):
    require_admin(u)
    with db.transaction() as s:
        row=s.get(InsuranceDocument,ident)
        if not row:raise HTTPException(404,'증권을 찾을 수 없습니다.')
        cfg=config(s);root=cfg['roots'].get(row.root_id)
        if not root or not marker_ok(root,row.root_id):raise HTTPException(503,'증권 저장 경로를 확인하세요.')
        try:
            cipher=safe(root,row.file).read_bytes()
            if hashlib.sha256(cipher).hexdigest()!=row.cipher_digest:raise ValueError()
            raw=Fernet(privacy.key()).decrypt(cipher)
            if hashlib.sha256(raw).hexdigest()!=row.digest:raise ValueError()
        except (OSError,ValueError,InvalidToken):raise HTTPException(503,'증권 파일 무결성 또는 저장 경로를 확인하세요.') from None
        privacy.audit(s,u,'INSURANCE_DOCUMENT_READ',ident)
        return raw,dto(s,row)

def install(app,db,user):
    def actor(request):
        with db.read() as s:
            u=user(s,request);require_admin(u);return SimpleNamespace(id=u.id,role=u.role,active=u.active,username=u.username)
    @app.get('/api/insurance/library/settings')
    def settings(request:Request):
        actor(request)
        with db.read() as s:
            cfg=config(s);return {**cfg,'path':cfg['roots'].get(cfg['active'],''),'default_path':default_path(db)}
    @app.put('/api/insurance/library/settings')
    def change(p:dict,request:Request):return configure(db,actor(request),p.get('path',''))
    @app.post('/api/insurance/library')
    def store(p:dict,request:Request):return save(db,actor(request),p)
    @app.get('/api/insurance/library')
    def search(request:Request,q:str='',cursor:str=''):return listing(db,actor(request),q,cursor)
    @app.get('/api/insurance/library/{ident}/image')
    def image(ident:str,request:Request):
        raw,meta=content(db,actor(request),ident)
        return Response(raw,media_type='image/jpeg',headers={'Cache-Control':'no-store','Content-Disposition':'attachment; filename="insurance-'+ident+'.jpg"'})
