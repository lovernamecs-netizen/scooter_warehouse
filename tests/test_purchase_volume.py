import json,time,tracemalloc
from test_workflow import env
from server.models import PurchaseRecord,uid
from server.purchase_sheet import ALL_FIELDS

def test_fifty_thousand_revisions_bounded_read(env):
 source={k:'' for k in ALL_FIELDS};source.update(model='합성차종',received_date='2026-01-02',vat_included='1000')
 with env[0].transaction() as session:
  for batch in range(10):
   mappings=[]
   for i in range(batch*1000,(batch+1)*1000):
    values={**source,'vin':f'TEST{i:013d}'}
    for version in range(1,6):mappings.append({'id':uid(),'record_id':f'record-{i:05d}','revision':version,'source_key':str(i),'data':{'source':values,'values':values,'pending':False},'actor':'synthetic'})
   session.bulk_insert_mappings(PurchaseRecord,mappings)
 tracemalloc.start();started=time.perf_counter()
 response=env[1].get('/api/purchases/page?month=2026-01',headers=env[2]);elapsed=time.perf_counter()-started;_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
 assert response.status_code==200,response.text
 result=response.json();assert result['count']==10000 and len(result['rows'])==50 and result['history']==[]
 assert len(response.content)<250000
 print(json.dumps({'records':10000,'revisions':50000,'query_seconds':round(elapsed,3),'response_bytes':len(response.content),'python_traced_peak_mb':round(peak/1024/1024,2)}))
