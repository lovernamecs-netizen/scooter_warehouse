"""Additive catalogue defaults and separate rack work lines."""
from sqlalchemy import select
from .models import Master,Setting,OptionLine,Equipment
from .domain import need,item_snapshot

def box(item):
    if 'requires_rack' in item:return bool(item['requires_rack'])
    name=str(item.get('name','')).upper()
    return ('탑박스' in name or 'EPP' in name) and not any(x in name for x in ['짐대','브라켓'])
def rack(item):return item.get('component')=='rack' or '짐대' in item.get('name','') or ('탑박스' in item.get('name','') and '브라켓' in item.get('name',''))
def catalog(s):
    if s.get(Setting,'catalog_119'):return
    for kind,name,detail in [('item','겨울토시',{'category':'추가 전달품'}),('item','여름토시',{'category':'추가 전달품'}),('option','짐대',{'category':'장착품','component':'rack','requires_install':True})]:
        if not s.scalar(select(Master).where(Master.kind==kind,Master.name==name)):s.add(Master(kind=kind,name=name,detail=detail,active=True))
    s.add(Setting(key='catalog_119',value={'added':True}))
def needs_rack(s,v,a):
    opts=list(s.scalars(select(OptionLine).where(OptionLine.assignment_id==a.id,OptionLine.qty>0)))
    equipment=list(s.scalars(select(Equipment).where(Equipment.vehicle_id==v.id,Equipment.qty>0)))
    return any(box(l.item) for l in opts),opts,equipment

def ensure(s,v,a):
    if s.get(Setting,'parts_order:'+a.id):return
    s.flush();required,opts,equipment=needs_rack(s,v,a)
    if not required:return
    if any(rack(e.item) for e in equipment) or any(rack(l.item) for l in opts):return
    m=s.scalar(select(Master).where(Master.kind=='option',Master.name=='짐대',Master.active==True))
    need(m is not None,'짐대 장착품 설정을 활성화하거나 짐대 품목을 함께 선택하세요.')
    s.add(OptionLine(assignment_id=a.id,master_id=m.id,item=item_snapshot(m),qty=1,required=True))

def check_complete(s,v,a):
    if s.get(Setting,'parts_order:'+a.id):return
    required,opts,equipment=needs_rack(s,v,a)
    if required:need(any(rack(e.item) for e in equipment) or any(rack(l.item) and l.done>=l.qty for l in opts),'탑박스/EPP에는 짐대가 필요합니다. 짐대 작업을 추가하고 완료하거나 기존 장착품을 확인하세요.')
