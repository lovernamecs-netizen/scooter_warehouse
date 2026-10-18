"""Verified file-only patch installer. Default is read-only preflight.

No startup migration, database restore, photo copy, service launch, Git or network upload.
Run only after deployment approval and stopping the server.
"""
import argparse
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path

def digest(path):
    if not path.exists():return None
    if not path.is_file():raise ValueError('Expected a regular file: '+path.name)
    return hashlib.sha256(path.read_bytes()).hexdigest()

def database_fingerprint(path):
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as con:
        return hashlib.sha256('\n'.join(con.iterdump()).encode('utf-8')).hexdigest()

def safe(root,name):
    if not isinstance(name,str) or '\\' in name or ':' in name:raise ValueError('Unsafe manifest path')
    p=Path(name)
    if p.is_absolute() or '..' in p.parts or not p.parts:raise ValueError('Unsafe manifest path')
    target=root.joinpath(p)
    if not target.resolve().is_relative_to(root.resolve()):raise ValueError('Path leaves target')
    for parent in [target,*target.parents]:
        if parent==root:break
        if parent.is_symlink() or (hasattr(parent,'is_junction') and parent.is_junction()):raise ValueError('Linked target is not supported')
    return target

def preflight(package,target):
    m=json.loads((package/'manifest.json').read_text(encoding='utf-8'))
    if m.get('format')!=1 or m.get('base_version')!='1.0.30':raise ValueError('Unsupported patch version')
    for name,record in m['files'].items():
        if Path(name).parts[0] not in ['server','web'] or Path(name).suffix not in ['.py','.js','.json','.html','.css','.svg']:raise ValueError('Disallowed payload type')
        if digest(safe(package/'payload',name))!=record['after']:raise ValueError('Payload hash mismatch: '+name)
    current={name:digest(safe(target,name)) for name in m['baseline']}
    expected_after={**m['baseline'],**{n:r['after'] for n,r in m['files'].items()}}
    for name in m['files']:
        if name not in current:current[name]=digest(safe(target,name))
    before={**m['baseline'],**{n:None for n in m['files'] if n not in m['baseline']}}
    if current==expected_after:return m,'already-applied'
    bad=[n for n in before if current.get(n)!=before[n]]
    if bad:raise ValueError('Unknown/modified source; no files changed: '+', '.join(bad))
    # Reject extra source modules (including an unregistered earlier patch).
    for folder in ['server','web']:
        for p in (target/folder).rglob('*'):
            if p.is_file() and p.suffix in ['.py','.js','.html','.css'] and '__pycache__' not in p.parts:
                if p.relative_to(target).as_posix() not in before:raise ValueError('Unrecognised source file: '+p.name)
    return m,'ready'

def check_stopped(port):
    with socket.socket() as sock:
        sock.settimeout(.5)
        if sock.connect_ex(('127.0.0.1',port))==0:raise ValueError('Server port is open. Stop the server first.')

def atomic_copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.warehouse-patch-',dir=target.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(source.read_bytes());f.flush();os.fsync(f.fileno())
        os.replace(name,target)
    finally:
        if Path(name).exists():Path(name).unlink()

def apply(package,target,database,backup_root,port=8765,fail_after=None):
    m,status=preflight(package,target)
    if status=='already-applied':return None
    check_stopped(port)
    database=database.resolve()
    if not database.is_file():raise ValueError('An existing SQLite database must be explicitly selected')
    if backup_root.resolve().is_relative_to(package.resolve()):raise ValueError('Keep backups outside the update package')
    backup_root.mkdir(parents=True,exist_ok=True)
    backup=backup_root/('patch-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));backup.mkdir()
    state={'patch':m['patch'],'target':str(target.resolve()),'files':{},'complete':False}
    # A read-only URI cannot create or replace the operational DB. SQLite backup includes WAL.
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(backup/'database.sqlite')) as dst:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Backup integrity check failed')
    state['database_backup_sha256']=digest(backup/'database.sqlite')
    state['database_path']=str(database)
    state['database_fingerprint']=database_fingerprint(backup/'database.sqlite')
    for name,record in m['files'].items():
        old=safe(target,name);before=digest(old)
        state['files'][name]={'before':before,'after':record['after']}
        if before is not None:
            dest=safe(backup/'files',name);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old,dest)
    journal=backup/'restore.json';journal.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    # Recheck after backup; concurrent edits cannot be silently overwritten.
    preflight(package,target)
    touched=[]
    try:
        for name,record in m['files'].items():
            if digest(safe(target,name))!=state['files'][name]['before']:raise ValueError('Source changed during update')
            atomic_copy(safe(package/'payload',name),safe(target,name));touched.append(name)
            if fail_after is not None and len(touched)==fail_after:raise OSError('Injected test failure')
        if preflight(package,target)[1]!='already-applied':raise ValueError('Post-update verification failed')
        state['complete']=True;journal.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception:
        for name in reversed(touched):
            record=state['files'][name];dest=safe(target,name)
            if digest(dest)!=record['after']:raise RuntimeError('Concurrent edit during rollback; use backup for manual review')
            if record['before'] is None:dest.unlink()
            else:atomic_copy(safe(backup/'files',name),dest)
        raise
    return backup

def rollback(backup,target,port=8765):
    check_stopped(port);state=json.loads((backup/'restore.json').read_text(encoding='utf-8'))
    if Path(state['target']).resolve()!=target.resolve():raise ValueError('Backup belongs to another target')
    if database_fingerprint(Path(state['database_path']))!=state['database_fingerprint']:raise ValueError('Database changed after update. Automatic rollback is blocked; review a forward fix without erasing business records.')
    for name,record in state['files'].items():
        if digest(safe(target,name))!=record['after']:raise ValueError('Changed since patch; rollback refused: '+name)
        if record['before'] is not None and digest(safe(backup/'files',name))!=record['before']:raise ValueError('Backup hash mismatch')
    for name,record in state['files'].items():
        if record['before'] is None:safe(target,name).unlink()
        else:atomic_copy(safe(backup/'files',name),safe(target,name))
    # Deliberately do not restore database.sqlite: that could erase subsequent business records.

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--target',type=Path,required=True);p.add_argument('--package',type=Path,default=Path(__file__).resolve().parent);p.add_argument('--apply',action='store_true');p.add_argument('--server-stopped',action='store_true');p.add_argument('--database',type=Path);p.add_argument('--backup-root',type=Path);p.add_argument('--port',type=int,default=8765);p.add_argument('--rollback',type=Path);a=p.parse_args()
    if a.apply or a.rollback:
        if not a.server_stopped:p.error('Stop all server processes and pass --server-stopped')
    if a.rollback:rollback(a.rollback,a.target,a.port);print('File rollback completed. Database and photos were not restored or changed.');return
    m,status=preflight(a.package,a.target);print(json.dumps({'patch':m['patch'],'status':status,'files':len(m['files'])}))
    if a.apply:
        if not a.database or not a.backup_root:p.error('--database and --backup-root are required')
        result=apply(a.package,a.target,a.database,a.backup_root,a.port);print('Verified file update completed. Backup: '+str(result))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,sqlite3.Error) as e:raise SystemExit(str(e))
