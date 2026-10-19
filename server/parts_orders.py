"""Order plans and atomic inventory postings. Existing snapshots are never rewritten."""
import copy
from collections import Counter
from sqlalchemy import select
from .models import Setting, Master, OptionLine, DeliveryLine, Outbound, Adjustment, uid, now
from .domain import need, today, lines

TEMPLATES = {
    'PCX': {'slide':'SSP','bracket':'RBP','screen_b2b':'WPCX_0','screen_b2c':'WPCX_1'},
    'NMAX': {'slide':'SSN','bracket':'RBN','screen_b2b':'WNMAX_1','screen_b2c':'WNMAX_1'},
    'FORZA350': {'bracket':'RBF'}, 'XMAX': {'bracket':'RBX'},
    'ADV350': {'bracket':'RBA'}, 'ZONTES368G': {'bracket':'RBZ','factory_rack':True},
    'HUSKY': {'factory_rack':True,'factory_label':'허스키 출고 기본 짐대 확인'},
}
STOCK_DRAFT = dict(MITT=487,SE=46,ST01=187,ST02=None,YC=12,SC=54,WPCX_0=51,
    WPCX_1=46,WNMAX_0=None,WNMAX_1=40,SSP=51,SSN=32,RBP=44,RBN=56,RBF=19,RBX=8,RBA=16,RBZ=1,CUP=348)

def config(data):
    return copy.deepcopy(data.get('order_rules', {'version':1,'models':{},'defaults':{'B2B':['SC','CUP'],'B2C':['SC']},'sets':{'EPP':{'item_id':'SE','component':'slide'},'TOP01':{'item_id':'ST01','component':'bracket'},'TOP02':{'item_id':'ST02','component':'bracket'}}}))

def plan(s,a):
    row=s.get(Setting,'parts_order:'+a.id) if a else None
    return copy.deepcopy(row.value) if row else None

def snapshot(i):
    return {k:copy.deepcopy(i.get(k)) for k in ['id','code','name','pack','price','category_id','supplier','product','color']}

def build(data,model_id,vehicle_kind,p):
    from .parts import itemmap, integer
    cfg=config(data);model=cfg['models'].get(model_id)
    need(model is not None,'차종 ID에 부품 규칙을 연결해야 합니다. 관리자 설정에서 확인하세요.')
    channel=p.get('channel');need(channel in ['B2B','B2C'],'B2B/B2C를 선택하세요.')
    items=itemmap(data);result=[];bykey={};purposes=p.get('purposes',{});sources=p.get('sources',{});excluded=p.get('exclude',[])
    need(isinstance(excluded,list),'기본품 제외 형식 오류')
    reason=str(p.get('reason','')).strip()
    need(not excluded or reason,'기본품 제외 사유가 필요합니다.')
    defaults=cfg['defaults'].get(channel,[])
    if channel=='B2B' and model.get('screen_b2b'):defaults=defaults+[model['screen_b2b']]
    need(set(excluded)<=set(defaults),'기본품 제외 대상 오류')
    def add(ident,origin,purpose=None,qty=1,source=None,label=None):
        i=items.get(ident) if ident else None
        need(i is not None or (source=='FACTORY' and label),'미등록 부품입니다: '+str(ident))
        if i:
            need(i['active'],'사용 중지 품목: '+i['code'])
            compatible=i.get('model_ids',[]);need(not compatible or model_id in compatible,'호환 차종이 아닙니다: '+i['code'])
            bound={r.get(k) for r in [*TEMPLATES.values(),*cfg['models'].values()] for k in ['slide','bracket','screen_b2b','screen_b2c'] if r.get(k)}
            allowed={model.get(k) for k in ['slide','bracket','screen_b2b','screen_b2c']}
            need(ident not in bound or ident in allowed,'차종 규칙과 다른 구성품입니다: '+i['code'])
            screens={r.get(k) for r in [*TEMPLATES.values(),*cfg['models'].values()] for k in ['screen_b2b','screen_b2c'] if r.get(k)}
            if ident in screens:need(ident==model.get('screen_b2c' if channel=='B2C' else 'screen_b2b'),'주문 구분에 맞는 윈드스크린을 선택하세요.')
        purpose=purpose or purposes.get(ident) or (i.get('purpose') if i else 'INSTALL')
        need(purpose in ['INSTALL','DELIVERY'],'장착/전달 용도를 지정하세요: '+(i['code'] if i else label))
        source=source or sources.get(ident,'WAREHOUSE');need(source in ['WAREHOUSE','FACTORY','EXISTING'],'조달 출처 오류')
        need(purpose!='DELIVERY' or source=='WAREHOUSE','추가 전달은 창고 출고로 기록하세요.')
        need(source!='FACTORY' or vehicle_kind=='NEW','중고차는 공장 기본 장착으로 추정할 수 없습니다.')
        if source!='WAREHOUSE':need(reason or origin=='factory','기존/공장 장착 확인 사유가 필요합니다.')
        key=(ident or 'factory-rack')+':'+purpose
        if key in bykey:
            old=bykey[key];need(old['source']==source,'동일 품목의 조달 출처가 충돌합니다.')
            if purpose=='DELIVERY':old['qty']+=qty
            if origin not in old['origins']:old['origins'].append(origin)
            return
        row={'key':key,'part_id':ident,'item':snapshot(i) if i else {'id':None,'code':None,'name':label,'pack':None,'price':None},'qty':qty,'purpose':purpose,'source':source,'origins':[origin]}
        result.append(row);bykey[key]=row
    for ident in defaults:
        if ident not in excluded:add(ident,'default',('DELIVERY' if model.get('bracket')=='RBF' else 'INSTALL') if channel=='B2B' and ident=='CUP' else None)
    choice=p.get('set','')
    if choice:
        rule=cfg['sets'].get(choice);need(rule,'미등록 세트입니다.')
        modes=p.get('set_modes',{})
        need(isinstance(modes,dict) and set(modes)<={'item','component'},'세트 구성 방식 오류')
        need(all(m in ['INSTALL','DELIVERY','OMIT'] for m in modes.values()),'세트 장착/전달 선택 오류')
        need(not modes or any(modes.get(k,'INSTALL')!='OMIT' for k in ['item','component']),'세트 품목을 하나 이상 선택하세요.')
        for key,ident in [('item',rule['item_id']),('component',model.get(rule['component']))]:
            mode=modes.get(key,'INSTALL')
            need(mode=='INSTALL' or ident not in p.get('install',[]),'세트 선택과 추가 장착이 충돌합니다. 추가 장착을 해제하세요.')
            if mode=='OMIT':continue
            factory=key=='component' and rule['component']=='bracket' and vehicle_kind=='NEW' and model.get('factory_rack')
            if factory and mode=='INSTALL':add(ident,'factory',mode,source=sources.get(ident,'FACTORY'),label=model.get('factory_label'))
            else:
                need(ident,'해당 차종의 세트 구성품이 미등록입니다.')
                add(ident,'set',mode,source='WAREHOUSE' if mode=='DELIVERY' else None)
    elif vehicle_kind=='NEW' and model.get('factory_rack'):
        add(model.get('bracket'),'factory','INSTALL',source=sources.get(model.get('bracket'),'FACTORY'),label=model.get('factory_label'))
    if p.get('screen'):
        need(channel=='B2C' and model.get('screen_b2c'),'선택 가능한 B2C 쉴드가 없습니다.')
        add(model['screen_b2c'],'selection')
    chosen=[cfg['sets'][choice]['item_id']] if choice else []
    chosen+=p.get('install',[])
    selected_sets=[r for r in cfg['sets'].values() if r['item_id'] in chosen]
    need(len({r['item_id'] for r in selected_sets})<=1,'EPP/탑박스 세트는 하나만 선택하세요.')
    for ident in p.get('install',[]):
        add(ident,'selection','INSTALL')
        for rule in selected_sets:
            if rule['item_id']!=ident:continue
            component=model.get(rule['component'])
            factory=rule['component']=='bracket' and vehicle_kind=='NEW' and model.get('factory_rack')
            if factory:add(component,'factory','INSTALL',source=sources.get(component,'FACTORY'),label=model.get('factory_label'))
            else:need(component,'해당 차종의 세트 구성품이 미등록입니다.');add(component,'set','INSTALL')
    for delivery in p.get('deliveries',[]):add(delivery['item_id'],'additional','DELIVERY',integer(delivery.get('qty',1),1),'WAREHOUSE')
    omitted=p.get('omit_lines',[])
    need(isinstance(omitted,list) and all(isinstance(k,str) and len(k)<=150 for k in omitted) and len(omitted)<=200,'제외 품목 형식 오류')
    # Keep exact purpose keys: excluding an installation must not remove separate delivery.
    omitted=set(omitted);removed=[r for r in result if r['key'] in omitted]
    result=[r for r in result if r['key'] not in omitted]
    return {'version':cfg['version'],'channel':channel,'model_id':model_id,'vehicle_kind':vehicle_kind,'lines':result,'request':copy.deepcopy(p),'reason':reason,'excluded_lines':removed}

def apply(s,u,v,a,p,convert=False):
    from .parts import load
    _,data=load(s);new=build(data,v.model_id,v.kind,p);old=plan(s,a);opts,deliveries=lines(s,a)
    need(old or not opts+deliveries or convert,'기존 주문은 명시적으로 전환해야 합니다.')
    need(not convert or str(p.get('reason','')).strip(),'기존 주문 전환 사유를 입력하세요.')
    # No completed or unrecognised work can disappear during a recalculation.
    desired={r['key']:r for r in new['lines']};existing={}
    for line in opts+deliveries:
        key=line.item.get('parts_key');target=desired.get(key)
        need(not line.done or (target and line.done<=target['qty'] and target['source']==line.item.get('parts_source')),'완료된 작업을 제거하거나 출처를 변경할 수 없습니다. 실제 작업을 먼저 확인하세요.')
        if key:existing[key]=line
        elif line.qty:need(convert and not line.done,'기존 작업은 미완료 항목만 명시적 전환할 수 있습니다.')
        if not target:line.qty=0;line.required=False
    for row in new['lines']:
        key=row['key'];line=existing.get(key)
        item={**row['item'],'parts_key':key,'part_id':row['part_id'],'parts_source':row['source'],'parts_purpose':row['purpose'],'requires_rack':False}
        if row['purpose']=='INSTALL' and row['source']=='WAREHOUSE':
            from .models import Equipment
            duplicate=any(e.item.get('part_id')==row['part_id'] and (not line or e.line_id!=line.id) for e in s.scalars(select(Equipment).where(Equipment.vehicle_id==v.id,Equipment.qty>0))) if row['part_id'] else False
            need(not duplicate,'이미 장착된 품목입니다. 기존 장착 확인 또는 실제 교체 작업을 먼저 확인하세요.')
        if not line:
            mid='parts:'+key;m=s.get(Master,mid)
            if not m:
                m=Master(id=mid,kind='option' if row['purpose']=='INSTALL' else 'item',name='[재고 '+key+'] '+item['name'],detail={'part_id':row['part_id']});s.add(m);s.flush()
            cls=OptionLine if row['purpose']=='INSTALL' else DeliveryLine
            line=cls(assignment_id=a.id,master_id=mid,item=item,qty=row['qty'],done=0,required=True);s.add(line)
        else:line.item=item;line.qty=row['qty'];line.required=True
        s.flush();row['line_id']=line.id
    row=s.get(Setting,'parts_order:'+a.id) or Setting(key='parts_order:'+a.id)
    row.value=new;s.add(row);a.ready=False;a.work='PENDING';return new

def prepare_dispatch(s,u,v,a,p):
    from .parts import load,report,itemmap
    saved=plan(s,a)
    if not saved:
        _,data=load(s)
        if data.get('order_rules'):
            need(u.role=='admin' and str(p.get('stock_exception_reason') or p.get('exception_reason','')).strip(),'기존 주문은 부품 연동 전환 또는 관리자 수동 재고 검수 예외 사유가 필요합니다.')
        return None  # No historical backfill; legacy exceptions remain visibly unlinked.
    need(saved['model_id']==v.model_id,'차종이 변경되었습니다. 부품 계획을 재검토하세요.')
    _,data=load(s);items=itemmap(data);balances={r['id']:r['ending'] for r in report(data,today())['rows']}
    opts,delivery=lines(s,a);actual={l.id:l for l in opts+delivery};used=Counter();result=copy.deepcopy(saved);result['lines']=[]
    for row in saved['lines']:
        line=actual.get(row['line_id']);need(line is not None,'부품 작업 연결이 없습니다.')
        q=line.done if row['purpose']=='INSTALL' else line.handed
        if not q:continue
        i=items.get(row['part_id'])
        if row['part_id']:need(i and i['active'],'사용 중지/미등록 부품을 출고할 수 없습니다.')
        entry={**row,'qty':q}
        # Freeze prices and labels at actual dispatch, not at assignment.
        if i:entry['item']=snapshot(i)
        result['lines'].append(entry)
        if row['source']=='WAREHOUSE':used[row['part_id']]+=q
    warnings=[items[k]['code']+(' 재고 미확인' if balances.get(k) is None else ' 재고 부족') for k,q in used.items() if balances.get(k) is None or balances[k]<q]
    reason=str(p.get('stock_exception_reason','')).strip()
    need(not warnings or (u.role=='admin' and reason),{'message':'부품 재고를 확인하거나 관리자 재고 예외 사유를 입력하세요.','warnings':warnings})
    result['stock_warnings']=warnings;result['stock_exception_reason']=reason
    return result

def write_book(s,rev,data):
    from .parts import PartsBook
    b=s.get(PartsBook,1) or PartsBook(id=1);b.revision=rev+1;b.data=data;s.add(b)

def post_dispatch(s,u,out):
    from .parts import load
    snapshot_=out.snapshot.get('parts_order')
    if not snapshot_:return
    rev,data=load(s)
    need(not any(e.get('outbound_id')==out.id for e in data['entries']),'이미 차감된 출고입니다.',409)
    ls=[{'item_id':r['part_id'],'delta':-r['qty'],'purpose':r['purpose'],'source':r['source'],'line_key':r['key'],'snapshot':r['item']} for r in snapshot_['lines'] if r['source']=='WAREHOUSE']
    data['entries'].append({'id':'dispatch:'+out.id,'kind':'VEHICLE','day':out.day,'at':now().isoformat(),'actor':u.username,'outbound_id':out.id,'auto':True,'lines':ls,'label':out.snapshot['vehicle']['vin'],'channel':snapshot_['channel']})
    write_book(s,rev,data)

def post_adjustment(s,u,out,adj):
    from .parts import load
    if not out.snapshot.get('parts_order'):return
    rev,data=load(s);original=next((e for e in data['entries'] if e.get('auto') and e.get('outbound_id')==out.id and e['kind']=='VEHICLE'),None)
    need(original,'출고 재고 기록이 없습니다.')
    if adj.kind=='RETURN':return
    need(not any(e.get('outbound_id')==out.id and e['kind']=='VOID' for e in data['entries']),'이미 취소된 출고입니다.',409)
    if adj.kind=='VOID':
        all_lines=[l for e in data['entries'] if e.get('auto') and e.get('outbound_id')==out.id for l in e.get('lines',[])]
        ls=[{**l,'delta':-l['delta']} for l in all_lines]
    else:
        key=adj.detail.get('line_key');line=next((r for r in out.snapshot['parts_order']['lines'] if r['key']==key),None)
        need(line is not None,'원 출고 부품 행을 선택해야 합니다.')
        delta=adj.detail['delta'];previous=sum(-l['delta'] for e in data['entries'] if e.get('auto') and e.get('outbound_id')==out.id for l in e.get('lines',[]) if l['line_key']==key)
        need(line['source']=='WAREHOUSE','공장/기존 장착 정정은 창고 재고 조정 대상이 아닙니다.')
        need(previous+delta>=0,'원 사용량보다 많이 반환할 수 없습니다.')
        need(adj.detail['category']==('options' if line['purpose']=='INSTALL' else 'items'),'장착/전달 정정 종류 오류')
        ls=[{'item_id':line['part_id'],'delta':-delta,'purpose':line['purpose'],'source':'WAREHOUSE','line_key':key,'snapshot':line['item']}]
    # Corrections affect the original business date; closing snapshots stay intact and become stale.
    data['entries'].append({'id':'adjustment:'+adj.id,'kind':adj.kind,'day':out.day,'at':now().isoformat(),'actor':u.username,'outbound_id':out.id,'adjustment_id':adj.id,'auto':True,'reason':adj.reason,'lines':ls})
    write_book(s,rev,data)

def effective_outbounds(s,d):
    voided=set(s.scalars(select(Adjustment.outbound_id).where(Adjustment.kind=='VOID')))
    return [o for o in s.scalars(select(Outbound).where(Outbound.day==d)) if o.id not in voided]

def daily(s,d):
    counts=Counter();usage=Counter();vehicles=[];models=Counter()
    for out in s.scalars(select(Outbound).where(Outbound.day==d)):
        adjustments=list(s.scalars(select(Adjustment).where(Adjustment.outbound_id==out.id)))
        void=any(a.kind=='VOID' for a in adjustments);p=out.snapshot.get('parts_order');channel=p['channel'] if p else 'LEGACY'
        vehicle={'id':out.id,'vin':out.snapshot['vehicle']['vin'],'model':out.snapshot['vehicle']['model'],'channel':channel,'void':void,'parts':[],'linked':bool(p),'adjusted':any(a.kind=='CORRECTION' for a in adjustments)}
        if p:
            for row in p.get('lines',[]):
                quantity=row['qty']+sum(a.detail['delta'] for a in adjustments if a.kind=='CORRECTION' and a.detail.get('line_key')==row['key'])
                if quantity:vehicle['parts'].append({'name':row['item']['name'],'purpose':row['purpose'],'source':row['source'],'qty':quantity})
        else:
            for category,purpose,quantity_key in [('options','INSTALL','qty'),('items','DELIVERY','qty')]:
                for row in out.snapshot.get(category,[]):
                    quantity=row.get(quantity_key,0)
                    if quantity:vehicle['parts'].append({'name':row['item']['name'],'purpose':purpose,'source':'UNLINKED','qty':quantity})
        vehicles.append(vehicle)
        if void:continue
        counts[channel]+=1
        models[out.snapshot['vehicle']['model']]+=1
        for row in (p or {}).get('lines',[]):usage[(row['item']['name'],row['purpose'],row['source'])]+=row['qty']
        for adj in adjustments:
            if adj.kind=='CORRECTION' and p:
                row=next((r for r in p['lines'] if r['key']==adj.detail.get('line_key')),None)
                if row:usage[(row['item']['name'],row['purpose'],row['source'])]+=adj.detail['delta']
    return {'counts':dict(counts),'models':dict(models),'vehicles':vehicles,'usage':[{'name':k[0],'purpose':k[1],'source':k[2],'qty':v} for k,v in usage.items()]}
