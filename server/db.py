import os
from contextlib import contextmanager
from sqlalchemy import create_engine,event,select,text,inspect
from sqlalchemy.orm import Session
from .models import Base, Guard, Setting

class Database:
    def __init__(self,url=None):
        url=url or os.getenv('DATABASE_URL','sqlite:///warehouse.db')
        self.engine=create_engine(url,connect_args={'check_same_thread':False,'timeout':30} if url.startswith('sqlite') else {},pool_pre_ping=True)
        self.sqlite=self.engine.dialect.name=='sqlite'
        if self.sqlite:
            @event.listens_for(self.engine,'connect')
            def pragma(dbapi,record):
                dbapi.execute('PRAGMA foreign_keys=ON')
                dbapi.execute('PRAGMA busy_timeout=30000')
                dbapi.execute('PRAGMA journal_mode=WAL')
    def init(self,seed_catalog=True):
        Base.metadata.create_all(self.engine)
        with self.transaction() as s:
            if not s.get(Guard,1): s.add(Guard(id=1,revision=0))
            schema=s.get(Setting,'schema_version')
            if schema and schema.value.get('version') not in [1,2]:raise RuntimeError('지원하지 않는 DB schema version: 업그레이드/복구 절차를 확인하세요.')
            if 'manufactured_month' not in {c['name'] for c in inspect(s.connection()).get_columns('vehicles')}:
                s.execute(text('ALTER TABLE vehicles ADD COLUMN manufactured_month VARCHAR(7)'))
            if not schema:s.add(Setting(key='schema_version',value={'version':2}))
            else:schema.value={'version':2}
            from .bundles import catalog
            if seed_catalog:catalog(s)
            for table in ['outbound','history','closings','adjustments','layout_revisions']:
                if self.sqlite:
                    for op in ['UPDATE','DELETE']:
                        s.execute(text(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{op} BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable record'); END"))
                else:
                    s.execute(text("CREATE OR REPLACE FUNCTION deny_ledger_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'immutable record'; END $$"))
                    s.execute(text(f"DROP TRIGGER IF EXISTS immutable_{table} ON {table}"))
                    s.execute(text(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION deny_ledger_mutation()"))
    @contextmanager
    def transaction(self):
        with Session(self.engine,expire_on_commit=False) as s:
            try:
                if self.sqlite: s.execute(text('BEGIN IMMEDIATE'))
                else: s.execute(select(Guard).where(Guard.id==1).with_for_update())
                yield s
                s.commit()
            except Exception:
                s.rollback(); raise
