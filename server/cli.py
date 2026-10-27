import argparse,getpass,json,os,base64,hashlib
from datetime import datetime
from sqlalchemy import select,insert
from .db import Database
from .models import *
from . import parts  # Register parts tables for complete backup and restore.
from .security import hash_password

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['init','demo','backup','restore','status']);parser.add_argument('--file');parser.add_argument('--username',default='admin');args=parser.parse_args()
    db=Database();db.init(seed_catalog=args.action not in ['restore','demo'])
    if args.action=='status':
        with db.transaction() as s:
            if not s.scalar(select(User).where(User.role=='admin',User.active==True)):raise SystemExit(1)
        print('ready')
    elif args.action=='init':
        password=os.getenv('WAREHOUSE_ADMIN_PASSWORD') or getpass.getpass('관리자 비밀번호(10자 이상): ')
        with db.transaction() as s:
            if s.scalar(select(User).where(User.username==args.username)):raise SystemExit('이미 존재하는 관리자입니다.')
            s.add(User(username=args.username,password=hash_password(password),role='admin'))
        print('관리자 생성 완료')
    elif args.action=='demo':
        from .domain import execute
        with db.transaction() as s:
            if s.scalar(select(Master).where(Master.kind.in_(['brand','model','color']))) or s.scalar(select(Vehicle)):raise SystemExit('차량·차종이 없는 DB에서만 예시 마스터를 추가합니다.')
            u=s.scalar(select(User).where(User.role=='admin'))
            if not u:raise SystemExit('먼저 init 실행')
            brands={name:execute(s,u,'master',{'kind':'brand','name':name})['id'] for name in ['HONDA','YAMAHA','ZONTES','SYM']}
            for b,name in [('HONDA','PCX125'),('YAMAHA','NMAX'),('YAMAHA','XMAX'),('ZONTES','368G'),('SYM','HUSKY125')]:execute(s,u,'master',{'kind':'model','name':name,'detail':{'brand_id':brands[b]}})
            for name,h in [('화이트','#f8fafc'),('블랙','#222b38'),('그레이','#8b95a4')]:execute(s,u,'master',{'kind':'color','name':name,'detail':{'hex':h}})
            for name,cap in [('충전거치대',''),('컵홀더',''),('사제 윈드쉴드',''),('알루미늄 탑박스 65L','65L'),('알루미늄 탑박스 85L','85L'),('EPP 박스',''),('블랙박스','')]:execute(s,u,'master',{'kind':'option','name':name,'detail':{'capacity':cap,'category':'장착품','requires_install':True}})
            for name in ['순정 윈드쉴드','순정 미러','브라켓']:execute(s,u,'master',{'kind':'item','name':name,'detail':{'category':'전달품'}})
            for name,kind,x,y,r,c in [('입고·유비스 대기','UBIS_WAIT',20,20,2,6),('정규 재고','STORAGE',20,400,2,8),('출고 대기','OUTBOUND_WAIT',1100,20,2,4),('중고차','USED',1100,400,2,4)]:execute(s,u,'zone',{'name':name,'kind':kind,'x':x,'y':y,'rows':r,'cols':c})
        print('예시 마스터·구역 추가 완료. 실제 차량 데이터는 없습니다.')
    else:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        need_file=args.file
        if not need_file:raise SystemExit('--file 경로 필요')
        password=os.getenv('WAREHOUSE_BACKUP_PASSWORD') or getpass.getpass('백업 암호(복구 시 동일 암호 필요): ')
        if len(password)<12:raise SystemExit('백업 암호는 12자 이상')
        if args.action=='backup':
            if os.path.exists(need_file):raise SystemExit('이미 존재하는 백업 파일입니다. 다른 파일명을 지정하세요.')
            with db.transaction() as s:
                tables={t.name:[dict(r._mapping) for r in s.execute(select(t))] for t in Base.metadata.sorted_tables if t.name not in ['sessions','commands']}
                from .photo_store import read_file
                files={}
                for row in tables['settings']:
                    d=row['value']
                    if row['key'].startswith('used_media:') and 'root_id' in d:
                        for preview in [False,True]:
                            raw,_,_=read_file(s,d,preview);rel=d['root_id']+'/'+(d['thumbnail'] if preview else d['path']);files[rel]={'data':base64.b64encode(raw).decode(),'sha256':hashlib.sha256(raw).hexdigest()}

            payload=json.dumps({'schema':1,'tables':tables,'photo_files':files},default=lambda v:v.isoformat() if isinstance(v,datetime) else v,ensure_ascii=False).encode()
            salt=os.urandom(16);nonce=os.urandom(12);key=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1,dklen=32)
            with open(need_file,'wb') as f:f.write(b'SWH1'+salt+nonce+AESGCM(key).encrypt(nonce,payload,b'SWH1'))
            print('암호화 백업 완료')
        else:
            data=open(need_file,'rb').read()
            if data[:4]!=b'SWH1':raise SystemExit('백업 형식 오류')
            salt=data[4:20];nonce=data[20:32];key=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1,dklen=32)
            payload=json.loads(AESGCM(key).decrypt(nonce,data[32:],b'SWH1'))
            if payload['schema']!=1:raise SystemExit('지원하지 않는 스키마')
            with db.transaction() as s:
                for t in Base.metadata.sorted_tables:
                    if t.name not in ['guard','settings'] and s.execute(select(t).limit(1)).first():raise SystemExit('복구는 새 빈 DB에서만 가능합니다. 서버를 중지하고 새 DATABASE_URL을 지정하세요.')
                if payload.get('photo_files'):
                    from pathlib import Path
                    import uuid
                    from .photo_store import safe,atomic
                    root=Path(db.engine.url.database).resolve().parent/('RestoredPhotos-'+uuid.uuid4().hex)
                    for rel,entry in payload['photo_files'].items():
                        raw=base64.b64decode(entry['data'],validate=True)
                        if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('사진 백업 무결성 오류')
                        atomic(safe(root,rel),raw)
                    for row in payload['tables']['settings']:
                        if row['key']=='photo_storage':
                            cfg=row['value'];cfg['roots']={k:str(root/k) for k in cfg['roots']};cfg['daily']=False;cfg['backup_path']=str(root.parent/'Backups')
                for t in Base.metadata.sorted_tables:
                    if t.name=='guard':
                        guard=s.get(Guard,1);guard.revision=payload['tables']['guard'][0]['revision']+1;continue
                    records=payload['tables'].get(t.name,[])
                    if t.name=='settings':
                        extra=list(s.scalars(select(Setting).where(Setting.key!='schema_version')))
                        if extra:raise SystemExit('복구 대상 DB에 설정이 존재합니다.')
                        marker=s.get(Setting,'schema_version')
                        if marker:s.delete(marker);s.flush()
                    for r in records:
                        for c in t.columns:
                            if isinstance(c.type,DateTime) and r.get(c.name):r[c.name]=datetime.fromisoformat(r[c.name])
                    if records:s.execute(insert(t),records)
            print('새 DB 복구 완료. 모든 사용자는 다시 로그인해야 합니다.')
if __name__=='__main__':main()
