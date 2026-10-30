"""Explicit operator-run repair; never invoked during startup or ordinary reads."""
import copy,uuid
from sqlalchemy import select
from .models import Assignment,Stay,Vehicle,Guard
from .parts import load,mutate
from .parts_orders import config,plan
from .domain import need,execute,lines
from .customer_privacy import permissions

def repair(s,u,assignment_id):
    need(permissions(s,u)['security_owner'],'최초 관리자만 실행할 수 있습니다.',403)
    rev,data=load(s);cfg=config(data)
    for ident in ['SC','CUP','MITT']:
        need(any(i['id']==ident and i['active'] for i in data['items']),'기본품 마스터를 확인하세요.')
    cfg['defaults']['B2B']=list(dict.fromkeys(cfg['defaults'].get('B2B',[])+['SC','CUP','MITT']))
    for rule in cfg['models'].values():
        if 'B2B' in rule.get('defaults',{}):rule['defaults']['B2B']=list(dict.fromkeys(rule['defaults']['B2B']+['SC','CUP','MITT']))
    mutate(s,u,{'action':'rules','revision':rev,'rules':cfg,'request_id':str(uuid.uuid4())})
    a=s.get(Assignment,assignment_id);need(a is not None and a.status=='ACTIVE','승인된 진행 주문이 아닙니다.',409)
    saved=plan(s,a);need(saved and saved['request']['channel']=='B2B','B2B 부품 계획을 확인하세요.')
    need(not any(l['part_id']=='MITT' for l in saved['lines']),'토시가 이미 포함되어 있습니다.',409)
    old_lines={l.id:(l.qty,l.done,getattr(l,'handed',None),copy.deepcopy(l.item)) for l in sum(lines(s,a),[])}
    st=s.get(Stay,a.stay_id);v=s.get(Vehicle,st.vehicle_id)
    request=copy.deepcopy(saved['request']);request['exclude']=[x for x in request.get('exclude',[]) if x!='MITT'];request['omit_lines']=[x for x in request.get('omit_lines',[]) if not x.startswith('MITT:')]
    request.setdefault('purposes',{})['MITT']='INSTALL';request.setdefault('sources',{})['MITT']='WAREHOUSE'
    request['reason']='사용자 승인: B2B 기본 토시 1개 추가, 기존 완료 작업 보존'
    execute(s,u,'parts_plan',{'vehicle_id':v.id,'version':v.version,'parts_order':request})
    actual=sum(lines(s,a),[])
    for l in actual:
        if l.id in old_lines:need((l.qty,l.done,getattr(l,'handed',None),l.item)==old_lines[l.id],'기존 작업 변경 감지: 적용을 취소합니다.',409)
    added=[l for l in actual if l.id not in old_lines]
    need(len(added)==1 and added[0].item.get('part_id')=='MITT' and added[0].qty==1 and added[0].done==0,'토시 추가 검증 실패',409)
    s.get(Guard,1).revision+=1
    return {'assignment_id':a.id,'added':'MITT','quantity':1,'existing_work_preserved':True,'inventory_posted':False}
