import json
import sqlite3
from contextlib import closing
from pathlib import Path
import importlib.util
import pytest

spec=importlib.util.spec_from_file_location('patch_installer',Path(__file__).resolve().parents[1]/'tools/install_patch.py');installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)

def fixture(tmp_path):
    target=tmp_path/'target';package=tmp_path/'package';backup=tmp_path/'backups'
    (target/'server').mkdir(parents=True);(package/'payload/server').mkdir(parents=True)
    (target/'server/app.py').write_text('original',encoding='utf-8');(target/'photos').mkdir();(target/'photos/original.jpg').write_bytes(b'synthetic original')
    (package/'payload/server/app.py').write_text('updated',encoding='utf-8');(package/'payload/server/new.py').write_text('new module',encoding='utf-8')
    files={n:{'after':installer.digest(package/'payload'/n)} for n in ['server/app.py','server/new.py']}
    (package/'manifest.json').write_text(json.dumps({'format':1,'base_version':'1.0.30','patch':'test','baseline':{'server/app.py':installer.digest(target/'server/app.py')},'files':files}))
    db=target/'warehouse.db'
    with closing(sqlite3.connect(db)) as con:con.execute('CREATE TABLE data(value TEXT)');con.execute("INSERT INTO data VALUES ('synthetic')");con.commit()
    return target,package,backup,db

def test_apply_idempotence_and_file_rollback(tmp_path):
    target,package,root,db=fixture(tmp_path);before=installer.digest(db)
    assert installer.preflight(package,target)[1]=='ready'
    backup=installer.apply(package,target,db,root,port=0)
    assert installer.preflight(package,target)[1]=='already-applied'
    assert installer.apply(package,target,db,root,port=0) is None
    assert installer.digest(db)==before and (target/'photos/original.jpg').read_bytes()==b'synthetic original'
    installer.rollback(backup,target,port=0);assert installer.preflight(package,target)[1]=='ready'

def test_unknown_source_payload_tamper_and_extra_modules_block(tmp_path):
    target,package,root,db=fixture(tmp_path)
    (target/'server/app.py').write_text('local changes')
    with pytest.raises(ValueError,match='modified'):installer.apply(package,target,db,root,port=0)
    assert not root.exists()
    (target/'server/app.py').write_text('original');(target/'server/unknown.py').write_text('unknown')
    with pytest.raises(ValueError,match='Unrecognised'):installer.preflight(package,target)
    (package/'payload/server/app.py').write_text('tampered')
    with pytest.raises(ValueError,match='hash mismatch'):installer.preflight(package,target)

def test_copy_failure_restores_only_touched_files(tmp_path):
    target,package,root,db=fixture(tmp_path)
    with pytest.raises(OSError,match='Injected'):installer.apply(package,target,db,root,port=0,fail_after=1)
    assert installer.preflight(package,target)[1]=='ready';assert len(list(root.glob('*/database.sqlite')))==1

def test_rollback_refuses_subsequent_business_data(tmp_path):
    target,package,root,db=fixture(tmp_path);backup=installer.apply(package,target,db,root,port=0)
    with closing(sqlite3.connect(db)) as con:con.execute("INSERT INTO data VALUES ('later business record')");con.commit()
    with pytest.raises(ValueError,match='Database changed'):installer.rollback(backup,target,port=0)
    assert (target/'server/app.py').read_text()=='updated'

def test_path_traversal_rejected(tmp_path):
    for name in ['../outside','C:/absolute','server/../../outside','server\\other']:
        with pytest.raises(ValueError):installer.safe(tmp_path,name)
