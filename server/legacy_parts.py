"""Explicitly link legacy work rows to inventory without losing completion history."""
import copy
from sqlalchemy import select
from .models import Setting,OptionLine,DeliveryLine,Equipment
from .domain import admin,need,lines,line_dto,audit
from .parts import load,itemmap
from .parts_orders import plan,snapshot,config


def link(s,u,v,a,p):
    admin(u);need(a is not None,'활성 주문이 없습니다.',409);need(not plan(s,a),'이미 재고 품목에 연결된 주문입니다.',409)
    reason=str(p.get('reason','')).strip();need(reason,'연결 사유를 입력하세요.')
    channel=p.get('channel','LEGACY');need(channel in ['B2B','B2C','LEGACY'],'주문 구분 오류')
    _,data=load(s);items=itemmap(data);opts,delivery=lines(s,a);original=[x for x in opts+delivery if x.qty>0]
    mapping=p.get('lines');need(isinstance(mapping,list) and len(mapping)==len(original) and original,'모든 기존 작업을 연결하세요.')
    byid={x.get('line_id'):x for x in mapping};need(len(byid)==len(mapping) and set(byid)=={x.id for x in original},'기존 작업 연결을 확인하세요.')
    prepared=[];keys=set()
    for line in original:
        m=byid[line.id];item=items.get(m.get('part_id'));need(item and item['active'],'사용 중인 재고 품목을 선택하세요.')
        need(not item.get('model_ids') or v.model_id in item['model_ids'],'차종과 맞지 않는 재고 품목입니다.')
        purpose=m.get('purpose');source=m.get('source','WAREHOUSE');need(purpose in ['INSTALL','DELIVERY'] and source in ['WAREHOUSE','EXISTING','FACTORY'],'장착/전달 및 출처를 확인하세요.')
        key=item['id']+':'+purpose;need(key not in keys,'같은 품목/용도의 중복 작업은 먼저 확인하세요.');keys.add(key)
        if isinstance(line,DeliveryLine) and purpose=='INSTALL':need(line.handed==0,'이미 전달한 품목을 장착으로 바꿀 수 없습니다.')
        prepared.append((line,item,purpose,source,key))
    before=[line_dto(x) for x in original];result=[];reclassified=False
    for old,item,purpose,source,key in prepared:
        line=old;metadata={**snapshot(item),'part_id':item['id'],'parts_key':key,'parts_source':source,'parts_purpose':purpose,'requires_rack':False}
        same=isinstance(old,OptionLine)==(purpose=='INSTALL')
        if not same:
            reclassified=True
            cls=OptionLine if purpose=='INSTALL' else DeliveryLine
            line=cls(assignment_id=a.id,master_id=old.master_id,item=metadata,qty=old.qty,done=old.done,required=old.required)
            s.add(line);s.flush()
            for equipment in s.scalars(select(Equipment).where(Equipment.line_id==old.id)):equipment.qty=0
            old.qty=0;old.done=0;old.required=False
            if isinstance(old,DeliveryLine):old.handed=0
            if isinstance(line,OptionLine) and line.done:s.add(Equipment(vehicle_id=v.id,line_id=line.id,item=metadata,qty=line.done,origin='NEW' if source=='WAREHOUSE' else source))
        else:
            line.item=metadata
            for equipment in s.scalars(select(Equipment).where(Equipment.line_id==line.id)):equipment.item=metadata;equipment.origin='NEW' if source=='WAREHOUSE' else source
        result.append({'key':key,'part_id':item['id'],'purpose':purpose,'source':source,'qty':line.qty,'item':snapshot(item),'origins':['legacy-linked'],'line_id':line.id})
    saved={'version':config(data)['version'],'channel':channel,'model_id':v.model_id,'vehicle_kind':v.kind,'lines':result,'request':{'channel':channel},'reason':reason,'legacy_linked':True}
    s.add(Setting(key='parts_order:'+a.id,value=saved))
    if reclassified:a.ready=False
    audit(s,u,'LEGACY_PARTS_LINKED',{'reason':reason,'before':before,'after':copy.deepcopy(saved),'reclassified':reclassified},v)
    return saved
