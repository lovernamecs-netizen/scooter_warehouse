"""Transactional split/merge plans. Slot and vehicle identities never change."""
import hashlib,json,uuid
from sqlalchemy import select
from .models import Zone,Slot,Placement,Stay,Vehicle,Guard,LayoutRevision
from . import warehouses as wh

def plan(s,p):
    from .domain import need,get,qty,clean
    need(p.get('revision')==get(s,Guard,1).revision,'지도가 변경되었습니다. 새로고침 후 미리보기를 다시 확인하세요.',409)
    mode=p.get('mode');need(mode in ['split','merge'],'분할/병합 작업을 선택하세요.')
    axis=p.get('axis');need(axis in ['rows','cols'],'행/열 방향을 선택하세요.')
    a=get(s,Zone,p.get('zone_id'));need(a.active,'사용 중인 구역을 선택하세요.')
    cfg=wh.config(s);wid=wh.wid(cfg,a.id);w=next(x for x in cfg['items'] if x['id']==wid);need(w['active'],'사용 중인 창고를 선택하세요.')
    before=[a];moves=[];hidden=[]
    def dto(z):return {k:getattr(z,k) for k in ['id','name','kind','rows','cols','x','y','model_ids','active','version']}
    az=dto(a);zones=[az];retired=[]
    sa=list(s.scalars(select(Slot).where(Slot.zone_id==a.id)))
    if mode=='split':
        cut=qty(p.get('cut'),1,getattr(a,axis)-1)
        name=clean(p.get('name',''),80);need(name,'새 구역 이름을 입력하세요.')
        need(not s.scalar(select(Zone).where(Zone.name==name)),'이미 있는 구역 이름입니다.',409)
        zid=str(uuid.uuid5(uuid.NAMESPACE_URL,json.dumps(p,sort_keys=True,ensure_ascii=False)))
        az[axis]=cut
        bz={**dto(a),'id':zid,'name':name,axis:getattr(a,axis)-cut,'x':qty(p.get('x'),0,10000),'y':qty(p.get('y'),0,10000),'version':1}
        zones.append(bz)
        for sl in sa:
            if sl.row<a.rows and sl.col<a.cols and getattr(sl,'row' if axis=='rows' else 'col')>=cut:
                moves.append({'id':sl.id,'zone_id':zid,'row':sl.row-(cut if axis=='rows' else 0),'col':sl.col-(cut if axis=='cols' else 0),'label':sl.label})
    else:
        b=get(s,Zone,p.get('other_id'));need(b.id!=a.id and b.active,'서로 다른 두 사용 구역을 선택하세요.')
        need(wh.wid(cfg,b.id)==wid,'같은 창고 안의 구역만 병합할 수 있습니다.')
        need(b.kind==a.kind and set(b.model_ids)==set(a.model_ids),'구역 용도와 허용 차종 설정이 같아야 병합할 수 있습니다.')
        other_axis='cols' if axis=='rows' else 'rows';need(getattr(a,other_axis)==getattr(b,other_axis),'행 방향 병합은 열 수가, 열 방향 병합은 행 수가 같아야 합니다.')
        total=getattr(a,axis)+getattr(b,axis);qty(total,1,30);az[axis]=total
        before.append(b);retired.append(b.id)
        sb=list(s.scalars(select(Slot).where(Slot.zone_id==b.id)))
        labels={sl.label for sl in sa};nextrow=max([999]+[sl.row for sl in sa])+1
        # Retain shrunk, empty historical slots outside the new active grid.
        for sl in sa:
            if (sl.row>=a.rows or sl.col>=a.cols) and sl.row<az['rows'] and sl.col<az['cols']:
                need(not s.scalar(select(Placement).where(Placement.slot_id==sl.id)),'숨겨진 칸에 차량이 있습니다. 관리자 확인이 필요합니다.',409)
                hidden.append({'id':sl.id,'row':nextrow,'col':0});nextrow+=1
        for sl in sb:
            if sl.row>=b.rows or sl.col>=b.cols:continue
            label=sl.label
            if label in labels:label=f'{b.name[:30]} · {sl.label[:30]} · {sl.id[:8]}'
            labels.add(label)
            moves.append({'id':sl.id,'zone_id':a.id,'row':sl.row+(a.rows if axis=='rows' else 0),'col':sl.col+(a.cols if axis=='cols' else 0),'label':label})
    for z in zones:
        need(wh.fits(w,z['x'],z['y'],z['cols']*116+32,z['rows']*112+92),f"{z['name']}: 변경 구역이 창고 외곽을 벗어납니다. 위치 또는 창고 크기를 조정하세요.",409)
    if mode=='split':
        z,bz=zones
        overlap=z['x']<bz['x']+bz['cols']*116+32 and bz['x']<z['x']+z['cols']*116+32 and z['y']<bz['y']+bz['rows']*112+92 and bz['y']<z['y']+z['rows']*112+92
        need(not overlap,'분할되는 두 구역이 겹칩니다. 새 구역 위치를 조정하세요.',409)
    # New footprint must not obscure any unrelated zone or object.
    affected={z.id for z in before}
    obstacles=[{'name':z.name,'x':z.x,'y':z.y,'width':z.cols*116+32,'height':z.rows*112+92} for z in s.scalars(select(Zone)) if z.active and z.id not in affected and wh.wid(cfg,z.id)==wid]
    from .models import Setting
    setting=s.get(Setting,'map_objects')
    obstacles += [{**o,'name':o['label']} for o in (setting.value.get('objects',[]) if setting else []) if o.get('warehouse_id','main')==wid]
    collisions=[]
    for z in zones:
        for o in obstacles:
            if z['x']<o['x']+o['width'] and o['x']<z['x']+z['cols']*116+32 and z['y']<o['y']+o['height'] and o['y']<z['y']+z['rows']*112+92:collisions.append(o['name'])
    need(not collisions,{'message':'변경 배치가 다른 구역/도형과 겹칩니다. 먼저 공간을 확보하세요.','areas':list(dict.fromkeys(collisions))},409)
    for z in before:
        for sl in s.scalars(select(Slot).where(Slot.zone_id==z.id)):
            if sl.row>=z.rows or sl.col>=z.cols:need(not s.scalar(select(Placement).where(Placement.slot_id==sl.id)),'범위 밖 칸에 차량이 있습니다. 재배치를 먼저 확인하세요.',409)
    vehicles=[]
    for z in before:
        for st in s.scalars(select(Stay).join(Placement,Placement.stay_id==Stay.id).join(Slot,Slot.id==Placement.slot_id).where(Slot.zone_id==z.id)):
            need(st.closed_at is None,'출고 차량이 위치를 점유하고 있습니다.',409);vehicles.append(st.vehicle_id)
    result={'mode':mode,'warehouse_id':wid,'zones':zones,'retired':retired,'moves':moves,'hidden':hidden,'vehicles':vehicles,'before':[dto(z) for z in before]}
    result['token']=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return result

def apply(s,u,p):
    from .domain import admin,need,get,location,current_stay,audit,layout
    admin(u);spec={k:v for k,v in p.items() if k!='preview_token'};result=plan(s,spec)
    need(p.get('preview_token')==result['token'],'변경 내용을 미리보기한 뒤 확정하세요.',409)
    original={vid:location(s,current_stay(s,get(s,Vehicle,vid))) for vid in result['vehicles']}
    cfg=wh.config(s)
    for data in result['zones']:
        z=s.get(Zone,data['id'])
        if z:z.version+=1
        else:z=Zone(id=data['id'],version=1);s.add(z)
        for key in ['name','kind','rows','cols','x','y','model_ids','active']:setattr(z,key,data[key])
        cfg['zones'][z.id]=result['warehouse_id']
    s.flush()
    for data in result['hidden']:
        sl=get(s,Slot,data['id']);sl.row=data['row'];sl.col=data['col'];sl.enabled=False
    s.flush()
    for data in result['moves']:
        sl=get(s,Slot,data['id'])
        for key in ['zone_id','row','col','label']:setattr(sl,key,data[key])
    for zid in result['retired']:z=get(s,Zone,zid);z.active=False;z.version+=1
    wh.save(s,cfg);s.flush()
    for vid,before in original.items():
        v=get(s,Vehicle,vid);v.version+=1;audit(s,u,'LAYOUT_RESTRUCTURED',{'mode':result['mode'],'from':before,'to':location(s,current_stay(s,v))},v)
    audit(s,u,'ZONE_RESTRUCTURED',{'mode':result['mode'],'before':result['before'],'after':result['zones']})
    s.add(LayoutRevision(actor=u.username,snapshot=layout(s)));s.flush()
    return {'zone_id':result['zones'][0]['id'],'preserved_vehicles':len(original),'moved_slots':len(result['moves'])}
