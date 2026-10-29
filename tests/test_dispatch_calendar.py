from test_workflow import env
from test_customer_privacy import another

def test_month_scope_and_permissions(env):
 db,c,h,cmd,state,receive,v,vc,z,*_=env
 ident=receive();vc('move',ident,{'slot_id':z['slots'][0]['id']})
 vc('assign',ident,{'scheduled':state()['today']})
 vc('dispatch',ident,{'exception_reason':'합성 테스트','stock_exception_reason':'합성 검증','handed':{}})
 today=state()['today'];full=c.get('/api/outbound',headers=h).json()
 assert c.get('/api/outbound?month='+today[:7],headers=h).json()==full
 assert c.get('/api/outbound?month=1990-01',headers=h).json()==[]
 for month in ['2026-13','bad','2026-1','9999-12']:
  assert c.get('/api/outbound?month='+month,headers=h).status_code==422
 _,uh=another(db,'ubis')
 assert c.get('/api/outbound?month='+today[:7],headers=uh).status_code==403
 assert c.get('/api/outbound?month='+today[:7]).status_code==401
 assert c.get('/api/outbound',headers=h).json()==full
