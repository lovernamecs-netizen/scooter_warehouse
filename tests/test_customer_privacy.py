import json,uuid
import pytest
from sqlalchemy import select,text
from test_workflow import env
from server.models import User,Customer,CustomerAccess,OrderCustomer,OutboundCustomer,CustomerAudit,VehicleCustomerEvent,Order
from server.security import hash_password,issue

def new_customer(c,h,name='자주 주문하는 합성업체'):
    p={'name':name,'kind':'COMPANY','request_id':str(uuid.uuid4())}
    response=c.post('/api/customers',headers=h,json=p);assert response.status_code==200,response.text
    assert c.post('/api/customers',headers=h,json=p).json()==response.json()
    return response.json()['id']

def another(db,role='admin'):
    with db.transaction() as s:
        u=User(username=str(uuid.uuid4()),password=hash_password('test-password-123'),role=role);s.add(u);s.flush();return u.id,{'Authorization':'Bearer '+issue(s,u)}

def test_grant_revoke_encryption_autocomplete_and_escalation(env):
    db,c,h,cmd,state,*_=env
    ident=new_customer(c,h);other,headers=another(db)
    for route in ('/api/customers','/api/customers/search'):
        assert c.post(route,headers=headers,json={}).status_code==403
    assert c.post('/api/customers/access',headers=headers,json={'user_id':other,'allowed':True}).status_code==403
    assert c.post('/api/customers/access',headers=h,json={'user_id':other,'allowed':True}).status_code==200
    assert c.post('/api/customers/search',headers=headers,json={'query':'자주 주문'}).json()['items'][0]['id']==ident
    assert c.post('/api/customers/access',headers=h,json={'user_id':other,'allowed':False}).status_code==200
    assert c.get('/api/customers/'+ident+'/history',headers=headers).status_code==403
    owner=state()['user']['id']
    body={'command_id':str(uuid.uuid4()),'action':'user','payload':{'id':owner,'username':'admin','role':'admin','password':'malicious-reset-123'}}
    assert c.post('/api/command',headers=headers,json=body).status_code==403
    with db.read() as s:
        row=s.get(Customer,ident);assert '합성업체' not in row.encrypted_name
        assert s.scalar(select(CustomerAudit).where(CustomerAudit.event=='CUSTOMER_ACCESS_REVOKED'))
    assert '자주 주문하는 합성업체' not in json.dumps(state(),ensure_ascii=False)

def test_required_identity_and_immutable_dispatch_link(env):
    db,c,h,cmd,state,receive,v,vc,z,*_=env
    ident=new_customer(c,h);vehicle=receive();vc('move',vehicle,{'slot_id':z['slots'][0]['id']})
    p={'vehicle_id':vehicle,'version':v(vehicle)['version'],'scheduled':state()['today']}
    assert c.post('/api/command',headers=h,json={'command_id':str(uuid.uuid4()),'action':'assign','payload':p}).status_code==422
    vc('assign',vehicle,{'scheduled':state()['today'],'customer_id':ident})
    order=v(vehicle)['assignment']['order_id']
    assert c.get('/api/customers/order/'+order,headers=h).json()['name']=='자주 주문하는 합성업체'
    bulk=c.post('/api/customers/orders',headers=h,json={'order_ids':[order,'legacy-unknown']})
    assert bulk.status_code==200 and bulk.json()[order]['name']=='자주 주문하는 합성업체'
    assert bulk.json()['legacy-unknown'] is None
    assert bulk.headers['cache-control']=='no-store'
    assert c.post('/api/customers/orders',headers=h,json={'order_ids':['a']*201}).status_code==422
    worker,wh=another(db,'worker')
    assert c.post('/api/customers/orders',headers=wh,json={'order_ids':[order]}).status_code==403
    assert c.get('/api/customers/order/'+order,headers=wh).status_code==403
    vc('dispatch',vehicle,{'exception_reason':'합성 예외 출고','stock_exception_reason':'합성 검증','handed':{}})
    items=c.get('/api/customers/'+ident+'/history',headers=h).json()['items'];assert len(items)==1 and items[0]['vehicle_id']==vehicle
    common=c.get('/api/outbound',headers=wh).json();assert '자주 주문하는 합성업체' not in json.dumps(common,ensure_ascii=False)
    with db.read() as s:
        assert len(list(s.scalars(select(OutboundCustomer))))==1
        assert len(list(s.scalars(select(VehicleCustomerEvent))))==1
    with pytest.raises(Exception):
        with db.transaction() as s:s.execute(text('DELETE FROM order_customers'))

def test_missing_or_wrong_key_fails_closed(env,monkeypatch,tmp_path):
    db,c,h,*_=env;ident=new_customer(c,h)
    monkeypatch.setenv('WAREHOUSE_CUSTOMER_KEY_FILE',str(tmp_path/'missing.key'))
    assert c.post('/api/customers/search',headers=h,json={'query':'자주'}).status_code==503
    assert c.get('/api/customers/'+ident+'/history',headers=h).status_code==503
    from cryptography.fernet import Fernet
    wrong=tmp_path/'wrong.key';wrong.write_bytes(Fernet.generate_key());monkeypatch.setenv('WAREHOUSE_CUSTOMER_KEY_FILE',str(wrong))
    assert c.post('/api/customers/search',headers=h,json={'query':'存在しない'}).status_code==503

def test_key_backup_restore_does_not_export_plain_key(env,monkeypatch,tmp_path):
    import os,sys
    from pathlib import Path
    from server.customer_keys import main
    db,c,h,*_=env;ident=new_customer(c,h)
    original=Path(os.environ['WAREHOUSE_CUSTOMER_KEY_FILE']).read_bytes()
    bundle=tmp_path/'recovery.keybackup'
    monkeypatch.setattr('getpass.getpass',lambda *_:'Synthetic recovery password 123!')
    monkeypatch.setattr(sys,'argv',['customer_keys','backup','--file',str(bundle)])
    main();assert original not in bundle.read_bytes()
    restored=tmp_path/'restored.key';monkeypatch.setenv('WAREHOUSE_CUSTOMER_KEY_FILE',str(restored))
    monkeypatch.setattr(sys,'argv',['customer_keys','restore','--file',str(bundle),'--database',db.engine.url.database])
    main();assert restored.read_bytes()==original
    assert c.get('/api/customers/'+ident+'/history',headers=h).status_code==200
    with pytest.raises(FileExistsError):main()

def test_duplicate_names_are_not_merged_and_pagination(env):
    db,c,h,*_=env
    first=new_customer(c,h,'동명이인');second=new_customer(c,h,'동명이인');assert first!=second
    assert len(c.post('/api/customers/search',headers=h,json={'query':'동명'}).json()['items'])==2
    for i in range(22):new_customer(c,h,'페이지합성 '+str(i))
    result=c.post('/api/customers/search',headers=h,json={'query':'페이지합성'}).json();assert len(result['items'])==20 and result['next']
    more=c.post('/api/customers/search',headers=h,json={'query':'페이지합성','after':result['next']}).json();assert len(more['items'])==2

def test_editor_rejects_duplicate_without_altering_existing_identity(env):
    db,c,h,*_=env
    ident=new_customer(c,h,'Duplicate Company')
    response=c.post('/api/customers',headers=h,json={'name':' duplicate company ','kind':'COMPANY','request_id':str(uuid.uuid4()),'prevent_duplicate':True})
    assert response.status_code==409
    rows=c.post('/api/customers/search',headers=h,json={'query':'duplicate company'}).json()['items']
    assert [row['id'] for row in rows]==[ident]

def test_delegated_admin_can_assign(env):
    db,c,h,cmd,state,receive,v,vc,z,*_=env
    ident=new_customer(c,h);vehicle=receive();vc('move',vehicle,{'slot_id':z['slots'][0]['id']})
    other,headers=another(db)
    payload={'vehicle_id':vehicle,'version':v(vehicle)['version'],'scheduled':state()['today'],'customer_id':ident}
    def assign():return c.post('/api/command',headers=headers,json={'command_id':str(uuid.uuid4()),'action':'assign','payload':payload})
    assert assign().status_code==403
    assert c.post('/api/customers/access',headers=h,json={'user_id':other,'allowed':True}).status_code==200
    response=assign();assert response.status_code==200,response.text
