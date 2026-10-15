from test_workflow import env

def test_order_preserves_vehicles_and_conflict(env):
 db,c,h,cmd,state,receive,v,vc,z,opt,item,model,color=env
 ident=receive();before=v(ident);original=next(m for m in state()['masters'] if m['id']==model)
 other=cmd('master',{'kind':'model','name':'Second model','detail':{'brand_id':original['detail']['brand_id']},'active':False})['id']
 models=[m for m in state()['masters'] if m['kind']=='model'];payload={'ids':[other,model],'versions':{m['id']:m['version'] for m in models}}
 cmd('model_order',payload);assert v(ident)==before
 after={m['id']:m for m in state()['masters'] if m['kind']=='model'}
 assert after[other]['detail']['sort_order']==0 and after[model]['detail']['sort_order']==1
 assert after[model]['detail']['brand_id']==original['detail']['brand_id'] and not after[other]['active']
 db.init();assert next(m for m in state()['masters'] if m['id']==other)['detail']['sort_order']==0
 cmd('model_order',payload,409);cmd('model_order',{'ids':[model,model],'versions':{}},409)
 token=c.post('/api/login',json={'username':'worker','password':'test-password-123'}).json()['token']
 import uuid
 result=c.post('/api/command',headers={'Authorization':'Bearer '+token},json={'command_id':str(uuid.uuid4()),'action':'model_order','payload':payload});assert result.status_code==403
