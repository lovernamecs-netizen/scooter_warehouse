"""Explicit corrections/transfers for unshipped installation records; no stock postings."""
import copy
from sqlalchemy import select
from .models import Equipment,OptionLine,Assignment,Outbound

def context(s,e,st,a):
 line=s.get(OptionLine,e.line_id) if e.line_id else None
 prior=s.get(Assignment,line.assignment_id) if line else None
 eligible=bool(st and e.qty>0 and line and prior and prior.stay_id==st.id and prior.status in ['ACTIVE','CANCELLED'] and not s.scalar(select(Outbound.id).where(Outbound.stay_id==st.id)))
 current=bool(eligible and a and prior.id==a.id)
 cancelled=bool(eligible and prior.status=='CANCELLED')
 return line,prior,{'can_correct':current or cancelled,'can_carry':bool(cancelled and a and e.qty==1 and e.item.get('part_id') and e.item.get('parts_source')=='WAREHOUSE'),'order_record':'current' if current else 'cancelled' if cancelled else 'historical'}

def edit(s,u,v,st,a,p):
 from .domain import need,get,clean,audit,lines
 from .parts_orders import apply,plan
 need(v.kind=='NEW','신차 장착 기록에서 수정하세요.')
 e=get(s,Equipment,p.get('equipment_id'));need(e.vehicle_id==v.id,'다른 차량의 장착품입니다.')
 line,prior,flags=context(s,e,st,a);mode=p.get('mode');reason=clean(p.get('reason',''),1000)
 need(reason,'수정 사유를 입력하세요.');need(p.get('confirmed') is True,'실제 장착 상태를 확인하세요.')
 need(flags['can_correct'],'과거 입고·출고 장착 기록은 여기서 수정할 수 없습니다.',409)
 before={'equipment_id':e.id,'line_id':e.line_id,'assignment_id':prior.id,'qty':e.qty,'done':line.done,'source':e.item.get('parts_source')}
 if mode=='correct':
  # Cancelled order work remains as historical evidence; only its current equipment is corrected.
  if a and prior.id==a.id:line.done=0
  e.qty=0
  if a:a.ready=False;a.work='IN_PROGRESS'
  audit(s,u,'EQUIPMENT_RECORD_CORRECTED',{'reason':reason,'before':before,'current_assignment':a.id if a else None},v)
 elif mode=='carry':
  need(flags['can_carry'],'현재 주문으로 연결할 수 없는 장착품입니다.',409)
  saved=plan(s,a);need(saved,'현재 주문의 부품 계획을 먼저 연결하세요.')
  request=copy.deepcopy(saved['request']);part=e.item['part_id'];key=part+':INSTALL'
  need(not any(l.qty and l.item.get('part_id')==part for l in lines(s,a)[0]),'현재 주문에 같은 장착 작업이 있습니다. 먼저 작업 계획을 확인하세요.',409)
  request['exclude']=[x for x in request.get('exclude',[]) if x!=part]
  request['omit_lines']=[x for x in request.get('omit_lines',[]) if x!=key]
  request['install']=list(dict.fromkeys(request.get('install',[])+[part]))
  request.setdefault('sources',{})[part]='WAREHOUSE';request.setdefault('purposes',{})[part]='INSTALL';request['reason']=reason
  e.qty=0;s.flush();new=apply(s,u,v,a,request)
  row=next((r for r in new['lines'] if r['key']==key),None);need(row and row['source']=='WAREHOUSE' and row['qty']==1,'연결할 장착 수량을 확인하세요.')
  target=get(s,OptionLine,row['line_id']);target.done=1
  existing=s.scalar(select(Equipment).where(Equipment.line_id==target.id))
  if existing:need(existing.qty==0,'현재 주문 장착품이 이미 있습니다.');existing.qty=1
  else:s.add(Equipment(vehicle_id=v.id,line_id=target.id,item=target.item,qty=1,origin='NEW'))
  a.ready=False;a.work='IN_PROGRESS'
  audit(s,u,'EQUIPMENT_ORDER_CARRIED',{'reason':reason,'before':before,'to_assignment':a.id,'to_line':target.id,'stock_posted':False},v)
 else:need(False,'장착 기록 수정 방식을 선택하세요.')
