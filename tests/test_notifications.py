import uuid
from sqlalchemy import select
from test_workflow import env
from server.models import History

def test_notifications_cursor_preferences_and_permissions(env):
 db,c,h,cmd,state,receive,v,vc,*_=env
 assert c.get('/api/notifications').status_code==401
 first=c.get('/api/notifications',headers=h).json();assert first['items']==[];cursor=first['cursor']
 ident=receive();vc('assign',ident,{'number':str(uuid.uuid4()),'scheduled':state()['today']})
 result=c.get('/api/notifications',headers=h,params={'after':cursor}).json();assert [i['event'] for i in result['items']]==['ASSIGNED'];assert result['items'][0]['vin_tail']==v(ident)['vin'][-4:];assert 'data' not in result['items'][0]
 assert c.get('/api/notifications',headers=h,params={'after':result['cursor']}).json()['items']==[]
 # A fresh login/view starts at latest; it does not replay the history ledger.
 assert c.get('/api/notifications',headers=h).json()['items']==[]
 before=v(ident)
 assert c.put('/api/notifications/preferences',headers=h,json={'events':[]}).status_code==200
 db.init();assert c.get('/api/notifications',headers=h).json()['events']==[];assert v(ident)==before
 token=c.post('/api/login',json={'username':'worker','password':'test-password-123'}).json()['token'];wh={'Authorization':'Bearer '+token}
 assert c.get('/api/notifications',headers=wh).json()['events']==['ASSIGNED','READY','DISPATCHED']
 assert c.put('/api/notifications/preferences',headers=wh,json={'events':['WORK_STARTED']}).status_code==200
 assert c.get('/api/notifications',headers=h).json()['events']==[]
 assert c.put('/api/notifications/preferences',headers=h,json={'events':['BAD']}).status_code==422
 assert c.put('/api/notifications/preferences',headers=h,json={'events':'READY'}).status_code==422
 assert c.get('/api/notifications',headers=h,params={'after':'missing'}).json()['reset']


def test_only_committed_events_and_pagination(env):
 db,c,h,cmd,state,receive,v,vc,*_=env;ident=receive()
 cursor=c.get('/api/notifications',headers=h).json()['cursor']
 try:
  with db.transaction() as s:
   s.add(History(vehicle_id=ident,event='DISPATCHED',actor='rollback',data={}));s.flush();raise RuntimeError('rollback')
 except RuntimeError:pass
 assert c.get('/api/notifications',headers=h,params={'after':cursor}).json()['items']==[]
 with db.transaction() as s:
  for i in range(105):s.add(History(vehicle_id=ident,event='READY',actor='tester',data={}))
 first=c.get('/api/notifications',headers=h,params={'after':cursor}).json();assert len(first['items'])==100 and first['more']
 second=c.get('/api/notifications',headers=h,params={'after':first['cursor']}).json();assert len(second['items'])==5
 assert not ({i['id'] for i in first['items']} & {i['id'] for i in second['items']})
