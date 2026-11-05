"""10k synthetic metadata HTTP benchmark. No real JPEG/customer data/provider calls."""
import os,time,json,uuid,statistics,httpx
from pathlib import Path
from sqlalchemy import select
from cryptography.fernet import Fernet
from browser_support import start,stop,PASSWORD,RESULTS
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.db import Database
from server.models import User
from server.insurance_library import InsuranceDocument,InsuranceDocumentSearch,terms
r=start(demo=False);prior=os.environ.get('WAREHOUSE_CUSTOMER_KEY_FILE');db=None
try:
 root=Path(r[1].name);os.environ['WAREHOUSE_CUSTOMER_KEY_FILE']=str(root/'customer.key');cipher=Fernet((root/'customer.key').read_bytes());db=Database('sqlite:///'+str(root/'test.db'))
 with db.transaction() as s:
  user=s.scalar(select(User).where(User.username=='admin'));actor=user.id
  for start in range(0,10000,250):
   docs=[];index=[]
   for n in range(start,start+250):
    ident=f'{n:020d}'+uuid.uuid4().hex;source=f'POLICY{n:05d}.jpg';meta={'source':source,'plate':'','page':1,'review_required':True}
    docs.append(dict(id=ident,digest=ident,plate_token='',root_id='synthetic',file=ident+'.enc',encrypted_meta=cipher.encrypt(json.dumps(meta).encode()).decode(),cipher_digest='',size=199000,actor_id=actor,created_at='2026-11-05T00:00:00+00:00'))
    index.extend({'document_id':ident,'term':term} for term in terms(source))
   s.bulk_insert_mappings(InsuranceDocument,docs);s.bulk_insert_mappings(InsuranceDocumentSearch,index)
 with httpx.Client(base_url=r[3],trust_env=False,timeout=20) as client:
  token=client.post('/api/login',json={'username':'admin','password':PASSWORD}).json()['token'];headers={'Authorization':'Bearer '+token};metrics={}
  for name,query,expected in [('first_page','',50),('exact_search','policy09999',1)]:
   timings=[]
   for _ in range(5):
    before=time.perf_counter();response=client.get('/api/insurance/library',params={'q':query},headers=headers);timings.append(time.perf_counter()-before)
    assert response.status_code==200 and len(response.json()['documents'])==expected,response.text
    assert 'jpeg_base64' not in response.text
   metrics[name]={'median_seconds':round(statistics.median(timings),4),'response_bytes':len(response.content),'returned':expected}
  metrics['synthetic_records']=10000;metrics['scope']='metadata HTTP only; no image payloads or real files'
  (RESULTS/'insurance-library-performance.json').write_text(json.dumps(metrics,indent=2),encoding='utf8');print(json.dumps(metrics))
finally:
 if db:db.engine.dispose()
 if prior is None:os.environ.pop('WAREHOUSE_CUSTOMER_KEY_FILE',None)
 else:os.environ['WAREHOUSE_CUSTOMER_KEY_FILE']=prior
 stop(r)
