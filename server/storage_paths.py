"""Explicit data location; starting a server must never initialize a missing database."""
import os
from pathlib import Path
from sqlalchemy.engine import URL
from contextlib import closing

def data_root():
    value=os.getenv('WAREHOUSE_DATA_DIR')
    if not value:return None
    root=Path(value).expanduser()
    if not root.is_absolute():raise ValueError('WAREHOUSE_DATA_DIR must be absolute')
    return root.resolve()

def database_url():
    root=data_root()
    explicit=os.getenv('DATABASE_URL')
    if root and explicit:raise ValueError('Choose WAREHOUSE_DATA_DIR or DATABASE_URL, not both')
    return URL.create('sqlite',database=str(root/'Database'/'warehouse.db')) if root else explicit or 'sqlite:///warehouse.db'

def require_existing(engine):
    if engine.dialect.name!='sqlite':return
    path=Path(engine.url.database or '')
    if not path.is_file() or path.stat().st_size==0:
        raise RuntimeError('기존 운영 DB를 찾을 수 없습니다. 데이터 경로/저장장치를 확인하세요. 자동 초기화하지 않습니다.')
    # Read-only SQLite connection cannot create an empty replacement database.
    import sqlite3
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as con:
        names={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'guard','settings','users','vehicles'}.issubset(names):
            raise RuntimeError('운영 DB 형식이 아닙니다. 올바른 경로를 선택하세요.')

def log_root(db):
    root=data_root()
    return root/'Logs' if root else Path(db.engine.url.database or 'warehouse.db').resolve().parent/'logs'
