"""Interactive key provisioning/recovery. No key material is printed or stored in Git."""
import argparse,base64,getpass,json,os,sqlite3,subprocess
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from .customer_privacy import key_path

def password_key(password,salt):
    if len(password)<12:raise ValueError('복구 비밀번호는 12자 이상이어야 합니다.')
    return base64.urlsafe_b64encode(Scrypt(salt=salt,length=32,n=2**15,r=8,p=1).derive(password.encode()))

def write_private(path,raw):
    path=Path(path).resolve();path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        if os.name=='nt':
            import csv,io
            result=subprocess.check_output(['whoami','/user','/fo','csv','/nh'],text=True)
            sid=next(csv.reader(io.StringIO(result)))[1]
            subprocess.run(['icacls',str(path),'/inheritance:r','/grant:r','*'+sid+':F','*S-1-5-18:F'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        with os.fdopen(fd,'wb') as out:fd=None;out.write(raw);out.flush();os.fsync(out.fileno())
    finally:
        if fd is not None:os.close(fd)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['init','backup','restore']);parser.add_argument('--file',required=True);parser.add_argument('--database');args=parser.parse_args();path=key_path()
    if args.action=='init':
        if path.exists():raise ValueError('기존 키가 있습니다. 새 키로 교체하지 않습니다.')
        if not args.database:raise ValueError('실제 DB 경로를 --database로 지정하세요.')
        with sqlite3.connect(Path(args.database).resolve().as_uri()+'?mode=ro',uri=True) as con:
            exists=con.execute("select 1 from sqlite_master where type='table' and name='customers'").fetchone()
            if exists and con.execute('select count(*) from customers').fetchone()[0]:raise ValueError('이미 고객 데이터가 있습니다. 새 키 생성 대신 기존 키를 복구하세요.')
        raw=Fernet.generate_key()
    elif args.action=='backup':raw=path.read_bytes().strip();Fernet(raw)
    else:
        data=json.loads(Path(args.file).read_text());password=getpass.getpass('복구 비밀번호: ')
        raw=Fernet(password_key(password,base64.b64decode(data['salt']))).decrypt(data['ciphertext'].encode());Fernet(raw)
        if not args.database:raise ValueError('복원할 DB를 --database로 지정하세요.')
        with sqlite3.connect(Path(args.database).resolve().as_uri()+'?mode=ro',uri=True) as con:
            exists=con.execute("select 1 from sqlite_master where type='table' and name='customers'").fetchone()
            probe=con.execute('select encrypted_name from customers limit 1').fetchone() if exists else None
            if probe:Fernet(raw).decrypt(probe[0].encode())
        write_private(path,raw);print('키 복구 완료. 기존 파일을 덮어쓰지 않았습니다.');return
    password=getpass.getpass('키 백업 비밀번호(12자 이상): ')
    if password!=getpass.getpass('비밀번호 확인: '):raise ValueError('비밀번호가 다릅니다.')
    salt=os.urandom(16);encrypted=Fernet(password_key(password,salt)).encrypt(raw).decode()
    write_private(Path(args.file),json.dumps({'version':1,'salt':base64.b64encode(salt).decode(),'ciphertext':encrypted}).encode())
    if args.action=='init':write_private(path,raw)
    print('암호화된 키 백업을 생성했습니다. DB 백업과 별도로 보관하세요.')

if __name__=='__main__':
    try:main()
    except Exception as exc:raise SystemExit('키 작업 실패: '+type(exc).__name__+' (기존 키는 교체하지 않습니다.)')
