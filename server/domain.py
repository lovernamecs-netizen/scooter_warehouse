import re,json,hashlib,uuid
from datetime import datetime,date,time,timedelta,timezone
from zoneinfo import ZoneInfo
from collections import Counter
from sqlalchemy import select,func
from fastapi import HTTPException
from .models import *
from . import warehouses as wh
from .security import hash_password
KST=ZoneInfo('Asia/Seoul')
def fail(message,code=422): raise HTTPException(code,message)
def need(condition,message,code=422):
    if not condition: fail(message,code)
def get(s,cls,id):
    item=s.get(cls,id)
    if not item: fail('대상을 찾을 수 없습니다.',404)
    return item
def rows(s,cls): return list(s.scalars(select(cls)))
def iso(t): return t.replace(tzinfo=timezone.utc).isoformat() if t else None
def day(t): return t.replace(tzinfo=timezone.utc).astimezone(KST).date().isoformat()
def today(): return now().astimezone(KST).date().isoformat()
def valid_date(value):
    try: return date.fromisoformat(value).isoformat()
    except (ValueError,TypeError): fail('날짜 형식은 YYYY-MM-DD입니다.')
def qty(v,minimum=0,maximum=9999):
    need(isinstance(v,int) and not isinstance(v,bool) and minimum<=v<=maximum,'수량/좌표 범위를 확인하세요.')
    return v
def clean(v,limit=500):
    need(isinstance(v,str) and len(v)<=limit,'문자열 길이 또는 형식을 확인하세요.')
    return v.strip()
def manufactured_month(value):
    if value is None or value=='':return None
    value=clean(value,7)
    need(bool(re.fullmatch(r'(19|20|21)\d{2}-(0[1-9]|1[0-2])',value)),'제조년월은 YYYY-MM 형식입니다.')
    need(value<=today()[:7],'미래 제조년월은 등록할 수 없습니다.')
    return value
def vin(value):
    value=clean(value,40).upper()
    need(bool(re.fullmatch('[A-HJ-NPR-Z0-9]{17}',value)),'VIN은 I/O/Q를 제외한 영문·숫자 17자리입니다. 원문을 확인하세요.')
    return value
def admin(u): need(u.role=='admin','관리자 권한이 필요합니다.',403)
def master(s,id,kind,active=True):
    m=get(s,Master,id);need(m.kind==kind and (m.active or not active),'사용 가능한 마스터 품목을 선택하세요.')
    return m
def version(v,p): need(v.version==p.get('version'),{'message':'다른 기기에서 변경했습니다. 최신 내용을 확인하고 다시 시도하세요.','current_version':v.version},409)
def audit(s,u,event,data=None,v=None):
    s.add(History(vehicle_id=v.id if v else None,event=event,actor=u.username,data=data or {}))
def current_stay(s,v):
    st=s.scalar(select(Stay).where(Stay.vehicle_id==v.id,Stay.closed_at==None));need(st is not None,'현재 재고 차량이 아닙니다.',409);return st
def assignment(s,st): return s.scalar(select(Assignment).where(Assignment.stay_id==st.id,Assignment.status=='ACTIVE'))
def lines(s,a): return list(s.scalars(select(OptionLine).where(OptionLine.assignment_id==a.id))),list(s.scalars(select(DeliveryLine).where(DeliveryLine.assignment_id==a.id)))
def invalidate(s,st):
    a=assignment(s,st)
    if a: a.ready=False;a.work='IN_PROGRESS'
def item_snapshot(m): return {'master_id':m.id,'name':m.name,**m.detail}
def line_dto(l): return {'id':l.id,'master_id':l.master_id,'item':l.item,'qty':l.qty,'done':l.done,'required':l.required,**({'handed':l.handed} if isinstance(l,DeliveryLine) else {})}
def staging(s):
    setting=s.get(Setting,'dispatch_staging')
    return dict(setting.value.get('items',{})) if setting else {}
def stage_set(s,stay_id,value=None):
    data=staging(s)
    if value is None:data.pop(stay_id,None)
    else:data[stay_id]=value
    setting=s.get(Setting,'dispatch_staging')
    if setting:setting.value={'items':data}
    else:s.add(Setting(key='dispatch_staging',value={'items':data}))
def unique_option(s,v,mid,a=None,exclude=None):
    need(not any(e.qty>0 and e.item.get('master_id')==mid and (exclude is None or e.line_id!=exclude) for e in s.scalars(select(Equipment).where(Equipment.vehicle_id==v.id))),'이미 장착된 품목입니다. 기존 장착품을 확인하세요.',409)
    if a:need(not any(l.master_id==mid and l.qty>0 and l.id!=exclude for l in lines(s,a)[0]),'이미 선택한 장착품입니다.',409)
def location(s,st):
    p=s.get(Placement,st.id) if st else None
    if not p:
        entry=staging(s).get(st.id) if st else None
        if not entry:return None
        return {'kind':'DISPATCH_STAGING','slot_id':None,'zone_id':None,'zone':'출고대기','label':'공통 출고대기','warehouse_id':None,'warehouse':'전체 창고 공통'}
    slot=get(s,Slot,p.slot_id);z=get(s,Zone,slot.zone_id)
    cfg=wh.config(s);warehouse_id=wh.wid(cfg,z.id);w=next(w for w in cfg['items'] if w['id']==warehouse_id)
    return {'slot_id':slot.id,'zone_id':z.id,'zone':z.name,'label':slot.label,'warehouse_id':warehouse_id,'warehouse':w['name']}
def vehicle_dto(s,v,u=None):
    model=get(s,Master,v.model_id);color=get(s,Master,v.color_id)
    brand=s.get(Master,model.detail.get('brand_id',''))
    st=s.scalar(select(Stay).where(Stay.vehicle_id==v.id,Stay.closed_at==None))
    a=assignment(s,st) if st else None
    loc=location(s,st)
    state=('보관처리' if v.archived else '출고완료') if not st else ('출고대기' if a and a.ready else {'PENDING':'작업대기','IN_PROGRESS':'작업중','COMPLETED':'작업완료'}.get(a.work) if a else '재고' if loc and loc.get('zone_id') and get(s,Zone,loc['zone_id']).kind in ['STORAGE','USED'] else '배치대기' if v.ubis=='INSTALLED' else '유비스 대기')
    result={'id':v.id,'vin':'' if v.vin.startswith('@PENDING:') else v.vin,'vin_pending':v.vin.startswith('@PENDING:'),'reference':'임시-'+v.id[:8],'model_id':v.model_id,'model':model.name,'brand':brand.name if brand else '', 'brand_id':brand.id if brand else '', 'color_id':v.color_id,'color':color.name,'color_hex':color.detail.get('hex','#94a3b8'),'year':v.year,'manufactured_month':v.manufactured_month,'kind':v.kind,'plate':v.plate,'smart_key':v.smart_key if not u or u.role in ['admin','worker'] else '', 'notes':v.notes,'ubis':v.ubis,'version':v.version,'archived':v.archived,'stay_id':st.id if st else None,'received_at':iso(st.received_at) if st else None,'location':loc,'state':state,'assignment':None}
    if a:
        opts,items=lines(s,a);o=get(s,Order,a.order_id)
        result['assignment']={'id':a.id,'order_id':o.id,'number':o.number,'notes':o.notes,'scheduled':a.scheduled,'work':a.work,'ready':a.ready,'options':[line_dto(l) for l in opts],'items':[line_dto(l) for l in items]}
    if v.kind=='USED':
        from .used_stock import summary
        result['used_stock']=summary(s,st)
    result['equipment']=[{'id':e.id,'item':e.item,'qty':e.qty,'origin':e.origin,'line_id':e.line_id} for e in s.scalars(select(Equipment).where(Equipment.vehicle_id==v.id,Equipment.qty>0))]
    return result
def layout(s):
    cfg=wh.config(s)
    ps={p.slot_id:p.stay_id for p in rows(s,Placement)}
    return {'warehouses':cfg['items'],'zones':[{'warehouse_id':wh.wid(cfg,z.id),'id':z.id,'name':z.name,'kind':z.kind,'rows':z.rows,'cols':z.cols,'x':z.x,'y':z.y,'model_ids':z.model_ids,'active':z.active,'version':z.version,'slots':[{'id':sl.id,'row':sl.row,'col':sl.col,'label':sl.label,'enabled':sl.enabled,'stay_id':ps.get(sl.id)} for sl in s.scalars(select(Slot).where(Slot.zone_id==z.id))]} for z in rows(s,Zone)],'objects':(s.get(Setting,'map_objects').value.get('objects',[]) if s.get(Setting,'map_objects') else [])}
def state(s,u):
    vehicles=[vehicle_dto(s,v,u) for v in rows(s,Vehicle)]
    if u.role=='ubis': vehicles=[v for v in vehicles if v['stay_id']];[v.update(assignment=None,equipment=[],notes='') for v in vehicles]
    return {'revision':get(s,Guard,1).revision,'server_time':iso(now()),'today':today(),'user':{'id':u.id,'username':u.username,'role':u.role},'masters':[{'id':m.id,'kind':m.kind,'name':m.name,'detail':m.detail,'active':m.active,'version':m.version} for m in rows(s,Master)],'vehicles':vehicles,'layout':layout(s)}
def report(s,d):
    valid_date(d);end=datetime.combine(date.fromisoformat(d)+timedelta(days=1),time.min,KST).astimezone(timezone.utc)
    outs=[o for o in rows(s,Outbound) if o.day==d]
    models=Counter();options=Counter();new_options=Counter();items=Counter()
    def key(l):
        it=l['item'];return ' / '.join(str(it.get(k,'')) for k in ['name','model','capacity'] if it.get(k))
    for o in outs:
        models[o.snapshot['vehicle']['model']]+=1
        for l in o.snapshot['options']:
            options[key(l)]+=l['qty']
            if l['origin']=='NEW':new_options[key(l)]+=l['qty']
        for l in o.snapshot['items']:items[key(l)]+=l['qty']
    sts=rows(s,Stay);hist=rows(s,History)
    nextday=(date.fromisoformat(d)+timedelta(days=1)).isoformat()
    nxt=list(s.scalars(select(Assignment).where(Assignment.status=='ACTIVE',Assignment.scheduled==nextday)))
    adjustments=[{'id':a.id,'outbound_id':a.outbound_id,'kind':a.kind,'reason':a.reason,'at':iso(a.at),'detail':a.detail} for a in rows(s,Adjustment) if day(a.at)==d]
    result={'day':d,'received':sum(day(x.received_at)==d and x.reason!='VOID' for x in sts),'ubis':len({h.vehicle_id for h in hist if h.event=='UBIS_INSTALLED' and day(h.at)==d}),'placed':sum(x.first_placed_at is not None and day(x.first_placed_at)==d for x in sts),'dispatched':len(outs),'current_stock':sum(x.closed_at is None for x in sts),'end_stock':sum(x.received_at.replace(tzinfo=timezone.utc)<end and (x.closed_at is None or x.closed_at.replace(tzinfo=timezone.utc)>=end) for x in sts),'models':dict(models),'options':dict(options),'new_options':dict(new_options),'items':dict(items),'next_day':nextday,'next_total':len(nxt),'next_completed':sum(a.work=='COMPLETED' for a in nxt),'adjustments':adjustments,'outbounds':[{'id':o.id,'at':iso(o.at),'vin':o.snapshot['vehicle']['vin'],'model':o.snapshot['vehicle']['model']} for o in outs]}
    c=s.get(Closing,d)
    return {**result,'closing':{'at':iso(c.at),'actor':c.actor,'snapshot':c.snapshot} if c else None}

def receive(s,u,p):
    vvin=vin(p.get('vin','')) if clean(p.get('vin','')) else '@PENDING:'+str(uuid.uuid4());need(s.scalar(select(Vehicle).where(Vehicle.vin==vvin)) is None,'등록된 VIN입니다. 기존 차량을 검색하세요.',409)
    need(p.get('model_id'),'차종을 선택하세요.');need(p.get('color_id'),'색상을 선택하세요.')
    master(s,p['model_id'],'model');master(s,p['color_id'],'color')
    year=qty(p.get('year'),1900,2100);kind=p.get('kind','NEW');need(kind in ['NEW','USED'],'신차/중고를 선택하세요.')
    v=Vehicle(vin=vvin,model_id=p['model_id'],color_id=p['color_id'],year=year,manufactured_month=manufactured_month(p.get('manufactured_month')),kind=kind,plate=clean(p.get('plate','')),smart_key=clean(p.get('smart_key','')),notes=clean(p.get('notes',''),4000),ubis='UNKNOWN' if kind=='USED' else 'NOT_INSTALLED')
    s.add(v);s.flush();st=Stay(vehicle_id=v.id)
    if p.get('received_date'):
        dt=valid_date(p['received_date']);need(dt<=today(),'미래 입고일은 등록할 수 없습니다.')
        st.received_at=datetime.combine(date.fromisoformat(dt),now().astimezone(KST).time().replace(tzinfo=None),KST).astimezone(timezone.utc)
    s.add(st);audit(s,u,'RECEIVED',{'received_date':p.get('received_date',today()),'vin_pending':v.vin.startswith('@PENDING:')},v);s.flush()
    if p.get('ubis_installed'):
        execute(s,u,'ubis',{'vehicle_id':v.id,'version':v.version,'status':'INSTALLED'})
    if p.get('slot_id'):
        execute(s,u,'move',{'vehicle_id':v.id,'version':v.version,'slot_id':p['slot_id']})
    if kind=='USED':
        from .used_stock import register
        register(s,st)
        if p.get('used_profile') is not None:execute(s,u,'used_profile',{'vehicle_id':v.id,'version':v.version,'profile':p['used_profile']})
    return {'vehicle_id':v.id}

def fifo_candidates(s,v):
    candidates=[]
    for other,stay in s.execute(select(Vehicle,Stay).join(Stay,Stay.vehicle_id==Vehicle.id).where(Stay.closed_at==None,Vehicle.archived==False,Vehicle.model_id==v.model_id,Vehicle.color_id==v.color_id,Vehicle.kind==v.kind,Vehicle.manufactured_month!=None)):
        if other.id==v.id or assignment(s,stay):continue
        if v.manufactured_month and other.manufactured_month>=v.manufactured_month:continue
        candidates.append((other,stay))
    candidates.sort(key=lambda pair:(pair[0].manufactured_month,pair[1].received_at,pair[0].id))
    return candidates

def execute(s,u,action,p):
    need(u.role!='viewer','조회 전용 계정입니다.',403)
    if u.role=='ubis': need(action=='ubis','유비스 작업만 허용됩니다.',403)
    if action=='used_record':
        v=get(s,Vehicle,p.get('vehicle_id'));version(v,p);need(v.kind=='USED','중고차만 가능합니다.');current_stay(s,v)
        execute(s,u,'vehicle_edit',{**p.get('vehicle',{}),'vehicle_id':v.id,'version':v.version})
        return execute(s,u,'used_profile',{'vehicle_id':v.id,'version':v.version,'profile':p.get('profile',{}),'complete':p.get('complete',False)})
    if action in ['used_profile','used_photo','used_media']:
        from .used_stock import execute as used_execute
        return used_execute(s,u,action,p)
    if action=='receive': return receive(s,u,p)
    if action=='restructure':
        from .layout_ops import apply
        return apply(s,u,p)
    if action=='model_order':
        admin(u)
        models=list(s.scalars(select(Master).where(Master.kind=='model')))
        ids=p.get('ids');versions=p.get('versions',{})
        need(isinstance(ids,list) and all(isinstance(x,str) for x in ids),'차종 순서 형식이 잘못되었습니다.')
        need(len(ids)==len(set(ids)) and set(ids)=={m.id for m in models},'차종 목록이 변경되었습니다. 새로고침 후 다시 정렬하세요.',409)
        need(isinstance(versions,dict) and all(versions.get(m.id)==m.version for m in models),'다른 관리자가 차종을 수정했습니다. 새로고침 후 다시 정렬하세요.',409)
        ranks={ident:index for index,ident in enumerate(ids)}
        for m in models:
            m.detail={**m.detail,'sort_order':ranks[m.id]};m.version+=1
        audit(s,u,'MODEL_ORDER_CHANGED',{'ids':ids})
        return {'ids':ids}
    if action=='master':
        admin(u);kind=p['kind'];need(kind in ['brand','model','color','option','item'],'잘못된 마스터 종류입니다.')
        name=clean(p['name'],120);need(name,'이름을 입력하세요.');detail=p.get('detail',{});need(isinstance(detail,dict),'세부정보 오류')
        if kind=='model':master(s,detail.get('brand_id'),'brand')
        if kind=='color':need(bool(re.fullmatch('#[0-9a-fA-F]{6}',detail.get('hex','#94a3b8'))),'색상 코드를 확인하세요.')
        if p.get('id'):
            m=get(s,Master,p['id']);version(m,p);need(m.kind==kind,'종류는 변경할 수 없습니다.');m.version+=1
        else:m=Master(kind=kind);s.add(m)
        m.name=name;m.detail=detail;m.active=bool(p.get('active',True));s.flush();audit(s,u,'MASTER_CHANGED',{'id':m.id,'name':name});return {'id':m.id}
    if action=='warehouse':
        admin(u);need(p.get('revision')==get(s,Guard,1).revision,'다른 작업으로 지도가 변경됐습니다. 새로고침하세요.',409)
        cfg=wh.config(s);ident=p.get('id') or str(uuid.uuid4());old=next((w for w in cfg['items'] if w['id']==ident),None)
        need(not p.get('id') or old is not None,'창고를 찾을 수 없습니다.',404)
        name=clean(p.get('name',''),80);need(name,'창고 이름을 입력하세요.')
        need(not any(w['id']!=ident and w['name']==name for w in cfg['items']),'이미 사용 중인 창고 이름입니다.',409)
        width=qty(p.get('width'),200,20000);height=qty(p.get('height'),200,20000);points=p.get('points',wh.RECT);need(wh.valid(points),'외곽 꼭짓점을 확인하세요. 교차하지 않는 3~20개의 점이 필요합니다.')
        active=bool(p.get('active',True));candidate={'id':ident,'name':name,'width':width,'height':height,'points':points,'active':active}
        zones=[z for z in rows(s,Zone) if wh.wid(cfg,z.id)==ident]
        occupied=[]
        for z in zones:
            for sl in s.scalars(select(Slot).where(Slot.zone_id==z.id)):
                place=s.scalar(select(Placement).where(Placement.slot_id==sl.id))
                if place:occupied.append({'vehicle_id':get(s,Stay,place.stay_id).vehicle_id,'zone':z.name,'slot':sl.label})
        if not active:
            need(not occupied,{'message':'차량이 남아 있어 창고를 사용 중지할 수 없습니다. 다른 창고로 이동하세요.','vehicles':occupied},409)
            need(any(w['active'] and w['id']!=ident for w in cfg['items']),'최소 한 개의 창고는 사용해야 합니다.')
        else:
            outside=[z.name for z in zones if z.active and not wh.fits(candidate,z.x,z.y,z.cols*116+32,z.rows*112+92)]
            objects=s.get(Setting,'map_objects');objects=objects.value.get('objects',[]) if objects else []
            outside += [o['label'] for o in objects if o.get('warehouse_id','main')==ident and not wh.fits(candidate,o['x'],o['y'],o['width'],o['height'])]
            need(not outside,{'message':'외곽 밖으로 나가는 구역/도형을 먼저 옮기거나 줄이세요. 기존 배치는 보존됩니다.','areas':outside},409)
        cfg['items']=[candidate if w['id']==ident else w for w in cfg['items']]+([] if old else [candidate]);wh.save(s,cfg)
        s.flush();s.add(LayoutRevision(actor=u.username,snapshot=layout(s)));audit(s,u,'WAREHOUSE_CHANGED',{'id':ident,'name':name,'active':active});return {'id':ident}
    if action in ['zone','slot','map_objects']:
        admin(u)
        if action=='zone':
            r=qty(p['rows'],1,30);c=qty(p['cols'],1,30);name=clean(p['name'],80);need(name,'구역 이름을 입력하세요.')
            kind=p.get('kind','STORAGE');need(kind in ['RECEIVING','UBIS_WAIT','STORAGE','WORK','OUTBOUND_WAIT','USED'],'구역 종류를 확인하세요.')
            mids=p.get('model_ids',[])
            for mid in mids:master(s,mid,'model')
            if p.get('id'):
                z=get(s,Zone,p['id']);version(z,p)
                conflicts=[]
                for sl in s.scalars(select(Slot).where(Slot.zone_id==z.id)):
                    place=s.scalar(select(Placement).where(Placement.slot_id==sl.id))
                    if place:
                        v=get(s,Vehicle,get(s,Stay,place.stay_id).vehicle_id)
                        if sl.row>=r or sl.col>=c or not p.get('active',True) or (mids and v.model_id not in mids):
                            conflicts.append({'vin':v.vin,'slot':sl.label,'vehicle_id':v.id})
                need(not conflicts,{'message':'차량 재배치가 필요합니다. 먼저 다른 빈 위치로 이동한 뒤 적용하세요.','vehicles':conflicts},409)
                z.version+=1
            else:z=Zone();s.add(z)
            z.name=name;z.kind=kind;z.rows=r;z.cols=c;z.x=qty(p.get('x',20),0,10000);z.y=qty(p.get('y',20),0,10000);z.model_ids=mids;z.active=bool(p.get('active',True));s.flush()
            cfg=wh.config(s);warehouse_id=p.get('warehouse_id',wh.wid(cfg,z.id));target=next((w for w in cfg['items'] if w['id']==warehouse_id),None)
            need(target and target['active'],'사용 가능한 창고를 선택하세요.')
            if warehouse_id!=wh.wid(cfg,z.id):
                need(not s.scalar(select(Placement).join(Slot,Placement.slot_id==Slot.id).where(Slot.zone_id==z.id)),'차량이 있는 구역의 소속 창고는 바꿀 수 없습니다. 차량을 먼저 이동하세요.',409)
            need(not z.active or wh.fits(target,z.x,z.y,z.cols*116+32,z.rows*112+92),'구역이 창고 외곽을 벗어납니다. 좌표·크기 또는 창고 외곽을 조정하세요.',409)
            cfg['zones'][z.id]=warehouse_id;wh.save(s,cfg)
            existing={(sl.row,sl.col):sl for sl in s.scalars(select(Slot).where(Slot.zone_id==z.id))}
            for rr in range(r):
                for cc in range(c):
                    if (rr,cc) not in existing:s.add(Slot(zone_id=z.id,row=rr,col=cc,label=f'{rr+1:02}-{cc+1:02}'))
                    elif rr>=p.get('old_rows',z.rows) or cc>=p.get('old_cols',z.cols):pass
            for (rr,cc),sl in existing.items():
                if rr>=r or cc>=c:sl.enabled=False
        elif action=='slot':
            sl=get(s,Slot,p['id']);z=get(s,Zone,sl.zone_id);version(z,p)
            enabled=bool(p['enabled']);need(not enabled or (sl.row<z.rows and sl.col<z.cols and z.active),'Grid 밖의 Slot은 활성화할 수 없습니다.')
            need(enabled or not s.scalar(select(Placement).where(Placement.slot_id==sl.id)),'차량이 있는 위치는 비활성화할 수 없습니다.',409)
            sl.enabled=enabled;sl.label=clean(p['label'],80);need(sl.label,'위치 이름을 입력하세요.');z.version+=1
        else:
            need(p.get('revision')==get(s,Guard,1).revision,'다른 작업으로 지도가 변경됐습니다. 새로고침하세요.',409)
            objects=p.get('objects',[]);need(isinstance(objects,list) and len(objects)<=100,'최대 100개 도형을 지원합니다.')
            cfg=wh.config(s)
            for o in objects:
                need(o.get('kind') in ['DOOR','AISLE','MATERIAL','WALL'],'도형 종류 오류');clean(o['label'],80)
                for k in ['x','y','width','height']:qty(o[k],0,10000)
                target=next((w for w in cfg['items'] if w['id']==o.get('warehouse_id','main')),None);need(target is not None,'도형의 창고가 없습니다.')
                need(wh.fits(target,o['x'],o['y'],o['width'],o['height']),'도형이 창고 외곽을 벗어납니다.',409)
            setting=s.get(Setting,'map_objects') or Setting(key='map_objects');setting.value={'objects':objects};s.add(setting)
        s.flush();s.add(LayoutRevision(actor=u.username,snapshot=layout(s)));audit(s,u,'LAYOUT_CHANGED');return {'ok':True}
    if action=='close_day':
        admin(u);d=valid_date(p['day']);need(d<=today(),'미래 날짜를 마감할 수 없습니다.');need(not s.get(Closing,d),'이미 마감된 날짜입니다.',409)
        snap=report(s,d);snap.pop('closing');s.add(Closing(day=d,actor=u.username,snapshot=snap));audit(s,u,'DAY_CLOSED',{'day':d});return {'day':d}
    if action=='user':
        admin(u);username=clean(p['username'],80);need(username,'아이디를 입력하세요.');role=p['role'];need(role in ['admin','worker','viewer','ubis'],'권한 오류')
        user=get(s,User,p['id']) if p.get('id') else User(username=username,password=hash_password(p['password']))
        need(user.id!=u.id or (p.get('active',True) and role=='admin'),'현재 관리자 본인의 권한을 해제할 수 없습니다.')
        user.username=username;user.role=role;user.active=bool(p.get('active',True))
        if p.get('password'):user.password=hash_password(p['password'])
        s.add(user);s.flush();audit(s,u,'USER_CHANGED',{'username':username,'role':role});return {'id':user.id}
    if action=='import_apply':
        job=get(s,ImportJob,p['id']);need(job.actor==u.username or u.role=='admin','본인의 가져오기만 적용할 수 있습니다.',403);need(not job.applied,'이미 적용한 파일입니다.',409)
        need(len(job.rows)>0 and all(not r.get('error') for r in job.rows),'오류를 수정한 파일을 다시 가져오세요.')
        ids=[receive(s,u,r['data'])['vehicle_id'] for r in job.rows];job.applied=True;return {'ids':ids}
    if action=='adjust_outbound':
        admin(u);o=get(s,Outbound,p['outbound_id']);reason=clean(p.get('reason',''),2000);need(reason,'정정 사유가 필요합니다.')
        kind=p['kind'];need(kind in ['RETURN','VOID','CORRECTION'],'정정 유형 오류')
        v=get(s,Vehicle,o.vehicle_id);version(v,p)
        if kind in ['RETURN','VOID']:
            need(not s.scalar(select(Stay).where(Stay.vehicle_id==v.id,Stay.closed_at==None)),'이미 재입고된 차량입니다.',409)
            need(not s.scalar(select(Adjustment).where(Adjustment.outbound_id==o.id,Adjustment.kind.in_(['RETURN','VOID']))),'이미 처리한 출고입니다.',409)
            s.add(Stay(vehicle_id=v.id,reason=kind));v.archived=False
            if kind=='RETURN':v.kind='USED'
        detail={}
        if kind=='CORRECTION':
            detail=p.get('detail',{});need(detail.get('category') in ['options','items'],'장착품/전달품을 선택하세요.');clean(detail.get('name',''),120)
            delta=detail.get('delta');need(isinstance(delta,int) and delta!=0 and abs(delta)<=9999,'정정 수량은 0이 아닌 정수입니다.')
        s.add(Adjustment(outbound_id=o.id,kind=kind,reason=reason,actor=u.username,detail=detail));v.version+=1;audit(s,u,kind,{'outbound_id':o.id,'reason':reason,'detail':detail},v);return {'vehicle_id':v.id}
    v=get(s,Vehicle,p.get('vehicle_id'));version(v,p)
    if action=='delete_vehicle':
        admin(u);need(p.get('confirmation')=='삭제','삭제 확인 문구를 입력하세요.')
        need(not s.scalar(select(Outbound).where(Outbound.vehicle_id==v.id)),'출고 이력이 있는 차량은 삭제할 수 없습니다. 출고 정정을 이용하세요.',409)
        reason=clean(p.get('reason',''),2000);need(reason,'삭제 사유를 입력하세요.')
        st=s.scalar(select(Stay).where(Stay.vehicle_id==v.id,Stay.closed_at==None))
        need(not v.archived,'이미 삭제/보관된 차량입니다.',409)
        if st:
            need(assignment(s,st) is None,'배정된 주문을 먼저 취소하세요.',409)
            place=s.get(Placement,st.id)
            if place:s.delete(place)
            st.closed_at=now();stage_set(s,st.id)
        v.archived=True;v.version+=1;audit(s,u,'DELETED',{'reason':reason},v);return {'vehicle_id':v.id}
    if action=='archive_vehicle':
        admin(u);need(p.get('confirmed_vin')==v.vin,'전체 VIN 확인이 필요합니다.');reason=clean(p.get('reason',''),2000);need(reason,'보관처리 사유가 필요합니다.')
        st=s.scalar(select(Stay).where(Stay.vehicle_id==v.id,Stay.closed_at==None))
        if st:
            need(assignment(s,st) is None,'활성 주문을 먼저 취소하세요.',409)
            place=s.get(Placement,st.id)
            if place:s.delete(place)
            st.closed_at=now();stage_set(s,st.id)
        v.archived=True;v.version+=1;audit(s,u,'ARCHIVED',{'reason':reason},v);return {'vehicle_id':v.id}
    if action=='vehicle_edit':
        if 'vin' in p and p['vin']!=('' if v.vin.startswith('@PENDING:') else v.vin):
            if not v.vin.startswith('@PENDING:'):admin(u);need(clean(p.get('reason','')),'VIN 변경 사유가 필요합니다.')
            new=vin(p['vin']);need(s.scalar(select(Vehicle).where(Vehicle.vin==new,Vehicle.id!=v.id)) is None,'등록된 VIN입니다.',409);audit(s,u,'VIN_CHANGED',{'old':'' if v.vin.startswith('@PENDING:') else v.vin,'new':new,'reason':p.get('reason','최초 VIN 등록')},v);v.vin=new
        for k in ['plate','smart_key','notes']:
            if k in p:setattr(v,k,clean(p[k],4000))
        if 'model_id' in p:
            master(s,p['model_id'],'model')
            open_stay=s.scalar(select(Stay).where(Stay.vehicle_id==v.id,Stay.closed_at==None))
            loc=location(s,open_stay)
            if loc and loc.get('zone_id'):
                allowed=get(s,Zone,loc['zone_id']).model_ids;need(not allowed or p['model_id'] in allowed,'현재 구역에서 허용되지 않는 차종입니다. 먼저 위치를 이동하세요.')
            v.model_id=p['model_id']
        if 'color_id' in p:master(s,p['color_id'],'color');v.color_id=p['color_id']
        if 'year' in p:v.year=qty(p['year'],1900,2100)
        month_change={}
        if 'manufactured_month' in p:
            new_month=manufactured_month(p['manufactured_month'])
            if new_month!=v.manufactured_month:month_change={'manufactured_month':{'from':v.manufactured_month,'to':new_month}}
            v.manufactured_month=new_month
        v.version+=1;audit(s,u,'VEHICLE_EDITED',month_change,v);return {'vehicle_id':v.id}
    if action=='reenter':
        admin(u);need(not s.scalar(select(Stay).where(Stay.vehicle_id==v.id,Stay.closed_at==None)),'이미 재고에 있습니다.',409);need(clean(p.get('reason','')),'재입고 사유를 입력하세요.');s.add(Stay(vehicle_id=v.id,reason='REENTRY'));v.archived=False;v.version+=1;audit(s,u,'REENTRY',{'reason':p['reason']},v);return {'vehicle_id':v.id}
    st=current_stay(s,v);a=assignment(s,st)
    if action=='ubis':
        status=p['status'];need(status in ['INSTALLED','NOT_INSTALLED','REMOVED','UNKNOWN'],'유비스 상태 오류')
        if u.role=='ubis':need(status=='INSTALLED','설치완료만 가능합니다.',403)
        need(v.ubis!=status,'이미 같은 유비스 상태입니다.',409);v.ubis=status
        if a:a.ready=False
        audit(s,u,'UBIS_INSTALLED' if status=='INSTALLED' else 'UBIS_CHANGED',{'status':status},v)
    elif action=='move':
        sl=get(s,Slot,p['slot_id']);z=get(s,Zone,sl.zone_id)
        cfg=wh.config(s);need(any(w['id']==wh.wid(cfg,z.id) and w['active'] for w in cfg['items']),'사용 중지된 창고입니다.',409)
        need(sl.enabled and z.active and sl.row<z.rows and sl.col<z.cols,'사용할 수 없는 위치입니다.',409)
        need(not z.model_ids or v.model_id in z.model_ids,'이 구역에 허용된 차종이 아닙니다.')
        need(not s.scalar(select(Placement).where(Placement.slot_id==sl.id)),'이미 차량이 있는 위치입니다.',409)
        before=location(s,st);place=s.get(Placement,st.id)
        if st.id in staging(s):
            stage_set(s,st.id)
            if a:a.ready=False
        if place:place.slot_id=sl.id
        else:s.add(Placement(stay_id=st.id,slot_id=sl.id))
        if z.kind in ['STORAGE','USED'] and not st.first_placed_at:st.first_placed_at=now()
        audit(s,u,'MOVED',{'from':before,'to':{'zone':z.name,'label':sl.label,'slot_id':sl.id,'warehouse_id':wh.wid(cfg,z.id),'warehouse':next(w['name'] for w in cfg['items'] if w['id']==wh.wid(cfg,z.id))}},v)
    elif action=='assign':
        need(not a,'이미 주문에 배정되어 있습니다.',409)
        older=fifo_candidates(s,v)
        fifo_reason=clean(p.get('fifo_override_reason',''),1000)
        need(not older or fifo_reason,{'code':'FIFO_PRIORITY','message':'같은 차종·색상의 더 이른 제조 차량이 있습니다. 작성 내용은 유지됩니다. FIFO 차량 다시 확인을 눌러 우선 차량을 선택하거나, 예외 사유를 입력하고 현재 차량을 선택하세요.','recommended_id':older[0][0].id if older else None},409)
        number=clean(p['number'],120);need(number,'주문번호를 입력하세요.');o=s.scalar(select(Order).where(Order.number==number))
        if not o:o=Order(number=number,notes=clean(p.get('notes',''),4000));s.add(o);s.flush()
        a=Assignment(order_id=o.id,stay_id=st.id,scheduled=valid_date(p['scheduled']));s.add(a);s.flush()
        for kind,cls in [('options',OptionLine),('items',DeliveryLine)]:
            seen=set()
            for l in p.get(kind,[]):
                mid=l.get('master_id');m=master(s,mid,'option' if kind=='options' else 'item') if mid else None
                need(m or kind=='items','장착 옵션 마스터를 선택하세요.')
                if kind=='options':
                    need(mid not in seen,'중복 장착품입니다.',409);seen.add(mid);unique_option(s,v,mid)
                    qty(l.get('qty',1),1,1)
                item=item_snapshot(m) if m else {'name':clean(l.get('name',''),120),'category':'기타','notes':clean(l.get('notes',''),500)};need(item['name'],'전달품 이름을 입력하세요.')
                s.add(cls(assignment_id=a.id,master_id=m.id if m else None,item=item,qty=qty(l.get('qty',1),1),required=bool(l.get('required',True))))
        from .bundles import ensure
        ensure(s,v,a)
        audit(s,u,'ASSIGNED',{'number':number,'scheduled':a.scheduled},v)
        if older:
            audit(s,u,'FIFO_OVERRIDE',{'reason':fifo_reason,'assignment_id':a.id,'selected_vin':v.vin,'selected_manufactured_month':v.manufactured_month,'older_candidates':[{'vehicle_id':x.id,'vin':x.vin,'manufactured_month':x.manufactured_month} for x,_ in older]},v)
    elif action=='plan_line':
        need(a is not None,'활성 주문이 없습니다.',409)
        kind=p.get('kind');need(kind in ['options','items'],'품목 종류를 확인하세요.')
        cls=OptionLine if kind=='options' else DeliveryLine
        if p.get('line_id'):
            line=get(s,cls,p['line_id']);need(line.assignment_id==a.id,'다른 주문의 항목입니다.')
            new_qty=qty(p['qty'],0)
            if kind=='options':
                need(new_qty in [0,1,line.qty],'장착품은 1개만 선택할 수 있습니다.')
                if line.qty==0 and new_qty:unique_option(s,v,line.master_id,a,exclude=line.id)
            need(new_qty>=line.done,'이미 작업한 수량보다 적게 변경할 수 없습니다. 먼저 실물과 작업 수량을 확인하세요.')
            if kind=='options' and new_qty==0:
                from .bundles import rack,box
                remaining=list(s.scalars(select(OptionLine).where(OptionLine.assignment_id==a.id,OptionLine.qty>0)))
                need(not (rack(line.item) and any(box(l.item) for l in remaining) and not any(l.id!=line.id and rack(l.item) for l in remaining)), '탑박스/EPP에 필요한 짐대입니다. 박스 작업을 먼저 제외하거나 다른 짐대를 추가하세요.')
            if new_qty==0:line.qty=0;line.required=False
            else:line.qty=new_qty;line.required=True
        else:
            mid=p.get('master_id');m=master(s,mid,'option' if kind=='options' else 'item') if mid else None
            need(m or kind=='items','장착품 마스터를 선택하세요.')
            item=item_snapshot(m) if m else {'name':clean(p.get('name',''),120),'category':'기타'};need(item['name'],'품목명을 입력하세요.')
            if kind=='options':
                qty(p.get('qty',1),1,1);unique_option(s,v,mid,a)
            s.add(cls(assignment_id=a.id,master_id=m.id if m else None,item=item,qty=qty(p.get('qty',1),1),required=True))
        from .bundles import ensure
        ensure(s,v,a)
        a.ready=False;a.work='IN_PROGRESS';audit(s,u,'PLAN_CHANGED',{'kind':kind},v)
    elif action in ['schedule','cancel_order','start_work','work_line','finish_work','ready']:
        need(a is not None,'활성 주문이 없습니다.',409)
        if action=='schedule':a.scheduled=valid_date(p['scheduled']);audit(s,u,'SCHEDULED',{'day':a.scheduled},v)
        elif action=='cancel_order':
            need(clean(p.get('reason','')),'취소 사유를 입력하세요.');a.status='CANCELLED';a.ready=False;audit(s,u,'ORDER_CANCELLED',{'reason':p['reason']},v)
        elif action=='start_work':a.work='IN_PROGRESS';a.ready=False;audit(s,u,'WORK_STARTED',{},v)
        elif action=='work_line':
            cls=OptionLine if p['kind']=='options' else DeliveryLine;line=get(s,cls,p['line_id']);need(line.assignment_id==a.id,'다른 주문의 항목입니다.')
            line.done=qty(p['done'],0,line.qty);a.work='IN_PROGRESS';a.ready=False
            if cls==OptionLine:
                e=s.scalar(select(Equipment).where(Equipment.line_id==line.id))
                if not e:e=Equipment(vehicle_id=v.id,line_id=line.id,item=line.item,origin='NEW',qty=0);s.add(e)
                e.qty=line.done
            else:line.handed=min(line.handed,line.done)
            audit(s,u,'WORK_CHECKED',{'kind':p['kind'],'line_id':line.id,'done':line.done},v)
        else:
            need(v.kind=='USED' or v.ubis=='INSTALLED','작업완료 전에 유비스 설치를 확인하세요.')
            if v.kind=='USED':
                from .used_stock import summary
                need(summary(s,st)['ready'],'중고차 점검과 엔진오일 교환 후 상품화 완료를 확인하세요.')
            from .bundles import check_complete
            check_complete(s,v,a)
            opts,items=lines(s,a);need(all(l.done>=l.qty for l in opts+items if l.required),'필수 작업 또는 전달품 준비가 완료되지 않았습니다.')
            need(action!='ready' or a.work=='COMPLETED','먼저 작업완료 처리하세요.')
            before=location(s,st)
            if action=='ready':
                need(v.kind=='USED' or v.ubis=='INSTALLED','유비스 설치 여부를 확인하세요.')
                stage_set(s,st.id,{'warehouse_id':None,'from':before,'at':iso(now())})
                place=s.get(Placement,st.id)
                if place:s.delete(place)
                s.flush();a.ready=True
            else:a.work='COMPLETED';a.ready=False
            audit(s,u,'READY' if action=='ready' else 'WORK_COMPLETED',{'from':before,'to':location(s,st)} if action=='ready' else {},v)
    elif action=='equipment':
        # Existing used equipment can be entered or removed without becoming a new order installation.
        if p.get('id'):
            e=get(s,Equipment,p['id']);need(e.vehicle_id==v.id and e.line_id is None,'주문 장착품은 작업 체크리스트에서 수정하세요.');new_qty=qty(p['qty']);need(new_qty in [0,1,e.qty],'장착품은 1개만 선택할 수 있습니다.')
            if e.qty==0 and new_qty:unique_option(s,v,e.item.get('master_id'),a)
            e.qty=new_qty
        else:
            m=master(s,p['master_id'],'option');unique_option(s,v,m.id,a);s.add(Equipment(vehicle_id=v.id,item=item_snapshot(m),qty=qty(p.get('qty',1),1,1),origin='EXISTING'))
        invalidate(s,st);audit(s,u,'EQUIPMENT_CHANGED',{},v)
    elif action=='dispatch':
        need(not v.vin.startswith('@PENDING:'),'출고 전에 차대번호를 등록하세요.')
        need(a is not None,'출고 주문을 먼저 배정하세요.')
        opts,items=lines(s,a);handed=p.get('handed',{})
        for l in items:l.handed=qty(handed.get(l.id,0),0,l.done)
        missing=[l.item['name'] for l in opts if l.required and l.done<l.qty]+[l.item['name'] for l in items if l.required and l.handed<l.qty]
        if not a.ready:missing.append('출고 준비확인')
        if v.kind=='USED':
            from .used_stock import summary
            if not summary(s,st)['ready']:missing.append('중고차 상품화 완료')
        if v.kind=='NEW' and v.ubis!='INSTALLED':missing.append('유비스')
        reason=clean(p.get('exception_reason',''),2000)
        if missing:admin(u);need(reason,{'message':'미완료 항목이 있습니다. 관리자 예외 사유가 필요합니다.','missing':missing})
        snap=vehicle_dto(s,v,u);snap.pop('smart_key',None)
        if v.kind=='USED':
            from .used_stock import read
            snap['used_reconditioning']=read(s,st)
        equipment=list(s.scalars(select(Equipment).where(Equipment.vehicle_id==v.id,Equipment.qty>0)))
        current_lines={l.id for l in opts}
        out=Outbound(stay_id=st.id,vehicle_id=v.id,day=today(),snapshot={'schema_version':1,'vehicle':snap,'options':[{'item':e.item,'qty':e.qty,'origin':'NEW' if e.line_id in current_lines else 'EXISTING'} for e in equipment],'items':[{'item':l.item,'qty':l.handed} for l in items if l.handed>0],'actor':u.username,'exception_reason':reason,'missing':missing})
        s.add(out);st.closed_at=now();a.status='FULFILLED';a.ready=False
        place=s.get(Placement,st.id)
        if place:s.delete(place)
        stage_set(s,st.id)
        s.flush();audit(s,u,'DISPATCHED',{'outbound_id':out.id,'exception_reason':reason},v)
    else:fail('지원하지 않는 작업입니다.')
    if v.kind=='USED' and action in ['equipment','equipment_remove']:
        from .used_stock import read,put
        profile=read(s,st)
        if profile:profile.update(ready=False,equipment_checked=False);put(s,'used_profile:'+st.id,profile)
    v.version+=1;s.flush();return {'vehicle_id':v.id,'version':v.version}

def command(s,u,body):
    cid=clean(body.get('command_id',''),80);need(len(cid)>=16,'고유 명령 ID가 필요합니다.')
    action=body.get('action');p=body.get('payload',{});need(isinstance(p,dict),'요청 형식 오류')
    digest=hashlib.sha256(json.dumps({'action':action,'payload':p},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    old=s.get(Command,cid)
    if old:need(old.digest==digest and old.user_id==u.id,'명령 ID가 다른 요청에서 사용됐습니다.',409);return old.result
    result=execute(s,u,action,p);get(s,Guard,1).revision+=1
    s.add(Command(id=cid,digest=digest,user_id=u.id,result=result));s.flush();return result
