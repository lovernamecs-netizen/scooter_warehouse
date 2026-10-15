"""Per-account preferences; notifications read immutable committed lifecycle history."""
from sqlalchemy import select,or_,and_
from .models import Setting,History,Vehicle,Master
from .domain import need,iso
EVENTS={'RECEIVED':'차량 입고','ASSIGNED':'주문·작업 배정','WORK_STARTED':'작업 시작','WORK_COMPLETED':'작업 완료','READY':'출고대기','DISPATCHED':'출고 완료','ORDER_CANCELLED':'주문 취소','MOVED':'위치 이동','UBIS_INSTALLED':'유비스 장착 완료'}
DEFAULT=['ASSIGNED','READY','DISPATCHED']
def preferences(s,u):
    row=s.get(Setting,'notifications:'+u.id)
    return row.value.get('events',DEFAULT) if row else DEFAULT

def save(s,u,p):
    selected=p.get('events');need(isinstance(selected,list) and all(isinstance(x,str) and x in EVENTS for x in selected),'알림 항목을 확인하세요.')
    selected=list(dict.fromkeys(selected));key='notifications:'+u.id;row=s.get(Setting,key)
    if row:row.value={'events':selected}
    else:s.add(Setting(key=key,value={'events':selected}))
    return {'events':selected}

def feed(s,u,after=None):
    need(u.role!='ubis','유비스 전용 계정은 업무 알림을 사용할 수 없습니다.',403)
    result={'events':preferences(s,u),'choices':EVENTS,'items':[],'cursor':after,'more':False}
    if after is None:
        latest=s.scalar(select(History).order_by(History.at.desc(),History.id.desc()).limit(1))
        result['cursor']=latest.id if latest else 'start';return result
    query=select(History)
    if after!='start':
        anchor=s.get(History,after)
        if not anchor:
            result=feed(s,u);result['reset']=True;return result
        query=query.where(or_(History.at>anchor.at,and_(History.at==anchor.at,History.id>anchor.id)))
    rows=list(s.scalars(query.order_by(History.at,History.id).limit(100)))
    result['more']=len(rows)==100
    if rows:result['cursor']=rows[-1].id
    for h in rows:
        if h.event not in result['events'] or not h.vehicle_id:continue
        v=s.get(Vehicle,h.vehicle_id);model=s.get(Master,v.model_id) if v else None
        result['items'].append({'id':h.id,'event':h.event,'title':EVENTS[h.event],'at':iso(h.at),'actor':h.actor,'vehicle_id':h.vehicle_id,'model':model.name if model else '차량','vin_tail':v.vin[-4:] if v and not v.vin.startswith('@PENDING:') else '미등록'})
    return result
