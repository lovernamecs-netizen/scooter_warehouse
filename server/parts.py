"""Parts closing ledger. Additive tables only; never mutates vehicle tables."""
import calendar,csv,io,json,re,hashlib,copy
from collections import Counter
from datetime import date,timedelta
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import String,JSON,Integer
from .models import Base,uid,now,Outbound,Adjustment
from .domain import need,today

class PartsBook(Base):
    __tablename__='parts_book'
    id: Mapped[int]=mapped_column(primary_key=True)
    revision: Mapped[int]=mapped_column(Integer,default=0)
    data: Mapped[dict]=mapped_column(JSON)
class PartsRequest(Base):
    __tablename__='parts_requests'
    id: Mapped[str]=mapped_column(String,primary_key=True)
    digest: Mapped[str]
    result: Mapped[dict]=mapped_column(JSON)

def hashof(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def norm(x):return re.sub(r'[\s-]+','',str(x)).upper()
def day(x):
    try:d=date.fromisoformat(str(x));need(d.isoformat()==x,'날짜 형식 오류');return x
    except (ValueError,TypeError):need(False,'날짜 형식 오류')
def integer(x,minimum=0):
    need(not isinstance(x,bool) and re.fullmatch(r'-?\d+',str(x)) is not None,'수량은 정수로 입력하세요.')
    v=int(x);need(minimum<=v<=10000000,'수량 범위 오류');return v

def initial():return {'items':json.loads((Path(__file__).parent/'parts_seed.json').read_text(encoding='utf-8')),'entries':[],'closings':[],'audit':[]}
def load(s):
    b=s.get(PartsBook,1);return (b.revision,copy.deepcopy(b.data)) if b else (0,initial())
def live(data):
    cancelled={e['target'] for e in data['entries'] if e['kind']=='CANCEL'}
    return [e for e in data['entries'] if e['kind']!='CANCEL' and e['id'] not in cancelled]
def itemmap(data):return {x['id']:x for x in data['items']}
def quantity(item,x):
    text=str(x).strip().upper().replace('EA','').strip()
    if text in ('','-','미확인'):return None
    if item['kind']=='box' and '/' in text:
        parts=text.split('/');need(len(parts)==2,'박스/낱개 형식 오류')
        boxes,loose=map(integer,parts);need(loose<item['pack'],'낱개는 박스당 수량보다 작아야 합니다.');return boxes*item['pack']+loose
    return integer(text)
def formatted(item,q):
    if q is None:return '-'
    if item['kind']=='box' and q>=0:return f"{q//item['pack']}/{q%item['pack']}"
    return f'{q}EA'
def report(data,d):
    day(d);events=live(data);items=data['items'];previous=(date.fromisoformat(d)-timedelta(days=1)).isoformat()
    def balance(until):
        bs=[e for e in events if e['kind']=='STOCKTAKE' and e['day']<=until]
        base=max(bs,key=lambda e:(e['day'],e['at'],e['id'])) if bs else None
        vals={i['id']:base['quantities'].get(i['id']) if base else None for i in items}
        deps=[base['id']] if base else []
        for e in events:
            if e['kind']=='STOCKTAKE' or e['day']>until or (base and e['day']<=base['day']):continue
            deps.append(e['id'])
            for line in e.get('lines',[]):
                if vals.get(line['item_id']) is not None:vals[line['item_id']]+=line['delta']
        return vals,base,deps
    opening,base,_=balance(previous);ending,endbase,deps=balance(d)
    daily=[e for e in events if e['day']==d];totals=Counter();rows=[]
    for i in sorted(items,key=lambda x:(x['order'],x['id'])):
        sums=Counter()
        for e in daily:
            for l in e.get('lines',[]):
                if l['item_id']==i['id']:sums[e['kind']]+=l['delta']
        row={'id':i['id'],'code':i['code'],'name':i['name'],'active':i['active'],'opening':opening[i['id']], 'inbound':sums['IN'],'vehicle':-sums['VEHICLE'],'outbound':-sums['OUT'],'returned':sums['RETURN'],'adjustment':sums['ADJUST'],'ending':ending[i['id']]}
        calculated=None if row['opening'] is None else row['opening']+sum(sums.values())
        row['stocktake']=endbase is not None and endbase['day']==d
        row['count_difference']=None if not row['stocktake'] or calculated is None or row['ending'] is None else row['ending']-calculated
        row['display']=formatted(i,row['ending']);rows.append(row)
        for k in ['inbound','vehicle','outbound','returned']:totals[k]+=row[k]
    # A later stocktake terminates dependency on previous transactions, while same-day audit remains visible.
    signature=hashof({'day':d,'rows':rows,'deps':sorted(deps),'daily':sorted(e['id'] for e in daily)})
    cs=[c for c in data['closings'] if c['day']==d];closing=cs[-1] if cs else None
    return {'day':d,'rows':rows,'totals':dict(totals),'base_day':base['day'] if base else None,'stocktake':bool(endbase and endbase['day']==d),'signature':signature,'status':('재확인 필요' if closing['signature']!=signature else '확정') if closing else ('미확정' if daily else '미입력'),'closing':closing,'entries':daily}

def source_warnings(s,data,d):
    warnings=[];seen={e.get('outbound_id') for e in live(data) if e['kind']=='VEHICLE'}
    for e in live(data):
        if e['kind']=='VEHICLE' and e['day']==d and e.get('outbound_id'):
            adj=list(s.scalars(select(Adjustment).where(Adjustment.outbound_id==e['outbound_id'])))
            if any(a.kind in ['VOID','CORRECTION'] and a.id not in e.get('adjustments_seen',[]) for a in adj):warnings.append('창고 출고 취소/정정 확인 필요: '+e.get('label',''))
    return warnings

def view(s,u,d,month):
    need(u.role!='ubis','권한이 없습니다.',403);day(d)
    try:y,m=map(int,month.split('-'));count=calendar.monthrange(y,m)[1]
    except (ValueError,TypeError):need(False,'월 형식 오류')
    rev,data=load(s);r=report(data,d);r['warnings']=source_warnings(s,data,d)
    days=[]
    for n in range(1,count+1):
        x=report(data,f'{y:04}-{m:02}-{n:02}');days.append({k:x[k] for k in ['day','totals','stocktake','status']})
    used={e.get('outbound_id') for e in live(data) if e['kind']=='VEHICLE'}
    outs=[]
    for o in s.scalars(select(Outbound).where(Outbound.day==d)):
        adj=list(s.scalars(select(Adjustment).where(Adjustment.outbound_id==o.id)))
        outs.append({'id':o.id,'vin':o.snapshot['vehicle']['vin'],'model':o.snapshot['vehicle']['model'],'used':o.id in used,'void':any(a.kind=='VOID' for a in adj),'adjusted':bool(adj),'options':o.snapshot['options'],'items':o.snapshot['items']})
    return {'revision':rev,'items':data['items'],'calendar':days,'report':r,'outbounds':outs,'closing_history':[{'day':c['day'],'at':c['at'],'actor':c['actor']} for c in data['closings'] if c['day']==d]}

def resolve(data,text,allow_inactive=False):
    codes=[x.strip() for x in re.split(r'[,\n]+',text) if x.strip() and x.strip()!='-'];mapping={norm(c):i for i in data['items'] for c in [i['code']]+i['aliases']};lines=[];issues=[];seen=Counter()
    for c in codes:
        item=mapping.get(norm(c))
        if not item:issues.append('미등록 코드: '+c);continue
        if not item['active'] and not allow_inactive:issues.append('사용 중지 코드: '+c);continue
        seen[item['id']]+=1;lines.append({'item_id':item['id'],'delta':-1})
    issues+=['중복 코드 수량 확인: '+itemmap(data)[k]['code'] for k,v in seen.items() if v>1]
    return lines,issues

def preview(s,u,p):
    need(u.role in ['admin','worker'],'권한이 없습니다.',403);rev,data=load(s);d=day(p['day']);text=str(p.get('text',''));need(0<len(text)<=500000,'붙여넣기 자료를 입력하세요.')
    try:raw=list(csv.reader(io.StringIO(text),delimiter='\t',strict=True))
    except csv.Error:need(False,'표의 따옴표/줄바꿈을 확인하세요.')
    need(len(raw)<=1000,'한 번에 1,000행 이하로 입력하세요.');rows=[];seen=set();active=live(data)
    cols=p.get('columns',{});indexes={k:integer(cols.get(k,v)) for k,v in {'date':2,'category':3,'model':6,'client':5,'code':0}.items()}
    for number,cells in enumerate(raw,1):
        if not any(c.strip() for c in cells):continue
        if any(c.strip() in ['출고일','출고일자','날짜'] for c in cells):continue
        def cell(k):
            idx=indexes[k];return cells[idx-1].strip() if idx and idx<=len(cells) else (cells[-1].strip() if k=='code' and idx==0 else '')
        rawday=cell('date');match=re.fullmatch(r'\s*(\d{4})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})\s*\.?\s*',rawday)
        rowday=''
        if match:
            try:rowday=date(*map(int,match.groups())).isoformat()
            except ValueError:pass
        cat=cell('category').upper();model=cell('model');codes=[c.strip() for c in re.split(r'[,\n]+',re.sub(r'<br\s*/?>',',',cell('code'),flags=re.I)) if c.strip() not in ['','-']]
        for i in data['items']:
            applies=i['rule']=='all' or i['rule']=='b2b' and cat=='B2B' or i['rule']=='pcx_b2b' and cat=='B2B' and 'PCX' in norm(model)
            if applies and i['active'] and not any(norm(c) in [norm(a) for a in [i['code']]+i['aliases']] for c in codes):codes.append(i['code'])
        source=hashof([d,[c.strip() for c in cells]])
        _,issues=resolve(data,','.join(codes));duplicate=source in seen or any(e.get('source')==source for e in active);seen.add(source)
        if duplicate:issues.append('동일 원문 중복: 재반영 금지. 별도 차량이면 고유 출고번호가 포함된 원문으로 구분하세요.')
        if rowday!=d:issues.append('출고일 확인 필요: '+(rowday or '읽을 수 없음'))
        if cat not in ['B2B','B2C']:issues.append('B2B/B2C 미확인: 기본 지급품 확인')
        if any('중고' in c for c in cells):issues.append('중고: 기존 장착품을 제외하고 실제 신규 사용품만 남기세요.')
        rows.append({'source':source,'label':f'{cells[0]} · {cat} · {cell("client")} · {model}','codes':', '.join(codes),'delivery_codes':'','issues':issues,'duplicate':duplicate,'source_day':rowday,'original':cells,'outbound_id':'','include':not duplicate})
    need(rows,'분석할 행이 없습니다.');return {'revision':rev,'rows':rows}

def mutate(s,u,p):
    need(u.role in ['admin','worker'],'변경 권한이 없습니다.',403);request_id=str(p.get('request_id',''));need(10<len(request_id)<100,'요청 ID 오류')
    digest=hashof([u.id,p]);prior=s.get(PartsRequest,request_id)
    if prior:need(prior.digest==digest,'같은 요청 ID의 내용이 다릅니다.',409);return prior.result
    rev,data=load(s);need(p.get('revision')==rev,'다른 작업으로 재고가 변경되었습니다. 새로고침 후 확인하세요.',409)
    action=p.get('action');at=now().isoformat();entries=data['entries'];items=itemmap(data)
    def add(kind,d,**kw):
        entry={'id':uid(),'kind':kind,'day':day(d),'at':at,'actor':u.username,**kw};entries.append(entry);return entry
    if action=='item':
        need(u.role=='admin','품목 설정은 관리자만 가능합니다.',403);v=p['item'];ident=v.get('id') or uid();old=items.get(ident)
        code=str(v.get('code','')).strip();need(code and len(code)<=60 and not re.search(r'[,\t\n]',code),'코드 형식 오류')
        if old:need(code==old['code'],'기존 내부 코드는 바꿀 수 없습니다. 별칭을 추가하세요.')
        name=str(v.get('name','')).strip();need(name and len(name)<=150,'품목명을 입력하세요.')
        aliases=[x.strip() for x in str(v.get('aliases','')).split(',') if x.strip()];keys=[norm(code)]+[norm(x) for x in aliases]
        need(len(set(keys))==len(keys),'코드/별칭 중복')
        used={norm(c) for i in data['items'] if i['id']!=ident for c in [i['code']]+i['aliases']};need(not used.intersection(keys),'다른 품목에 등록된 코드입니다.')
        kind=v.get('kind','ea');rule=v.get('rule','');need(kind in ['ea','box'] and rule in ['','all','b2b','pcx_b2b'],'설정값 오류')
        item={'id':ident,'code':code,'name':name,'aliases':aliases,'kind':kind,'pack':integer(v.get('pack',1),1),'active':bool(v.get('active',True)),'order':integer(v.get('order',len(items))),'rule':rule,'export_group':old.get('export_group') if old else None}
        data['items']=[item if i['id']==ident else i for i in data['items']]+([] if old else [item]);data['audit'].append({'at':at,'actor':u.username,'action':'ITEM','before':old,'after':item})
    elif action=='stocktake':
        need(u.role=='admin','실사 확정은 관리자만 가능합니다.',403);d=day(p['day']);reason=str(p.get('reason','')).strip();need(reason,'실사 사유/기준을 입력하세요.');qs=p.get('quantities',{})
        need(set(qs)==set(items),'모든 품목 수량을 확인하세요. 모르면 -를 입력하세요.');need(not any(e['kind']=='STOCKTAKE' and e['day']==d for e in live(data)),'같은 날짜 실사가 있습니다. 기존 기록을 취소한 뒤 다시 입력하세요.')
        add('STOCKTAKE',d,quantities={k:quantity(items[k],v) for k,v in qs.items()},reason=reason,scope='END_OF_DAY')
    elif action=='movement':
        kind=p['kind'];need(kind in ['IN','OUT','RETURN','ADJUST'],'거래 유형 오류');reason=str(p.get('reason','')).strip();need(reason,'공급처/수령처와 사유를 입력하세요.');lines=[]
        for line in p.get('lines',[]):
            i=items.get(line['item_id']);need(i and i['active'],'사용 가능한 품목을 선택하세요.');q=integer(line['qty'],-10000000 if kind=='ADJUST' else 1);need(q!=0,'수량은 0일 수 없습니다.');lines.append({'item_id':i['id'],'delta':-q if kind=='OUT' else q})
        need(lines,'품목을 추가하세요.');add(kind,p['day'],lines=lines,reason=reason)
    elif action=='import':
        d=day(p['day']);need(p.get('checked') is True,'실제 출고일·중복·중고·신규 사용품을 검수해 주세요.');rs=p.get('rows',[]);need(0<len(rs)<=1000,'출고 행을 선택하세요.')
        for row in rs:
            source=str(row.get('source',''));need(re.fullmatch('[a-f0-9]{64}',source) is not None,'원문 식별값 오류')
            need(not any(e.get('source')==source for e in live(data)),'이미 반영된 원문입니다. 중복 차감을 중단했습니다.',409)
            need(not row.get('source_day') or row['source_day']==d,'다른 날짜 출고 행이 포함되어 있습니다. 날짜별로 나누어 입력하세요.')
            outid=row.get('outbound_id','');need(bool(outid) or p.get('external_confirmed') is True,'창고 출고와 연결하거나 외부 자료 중복 확인을 완료하세요.')
            adjustments_seen=[]
            if outid:
                adjustments_seen=[a.id for a in s.scalars(select(Adjustment).where(Adjustment.outbound_id==outid))]
                o=s.get(Outbound,outid);need(o and o.day==d,'선택 날짜의 출고 차량이 아닙니다.');need(not any(a.kind=='VOID' for a in s.scalars(select(Adjustment).where(Adjustment.outbound_id==outid))),'취소된 출고입니다.')
                need(not any(e.get('outbound_id')==outid for e in live(data)),'이미 부품 사용이 반영된 차량입니다.',409)
            lines,issues=resolve(data,str(row.get('codes','')));delivery,di=resolve(data,str(row.get('delivery_codes','')))
            need(not any(not w.startswith('중복 코드') for w in issues+di),'미등록/사용 중지 코드를 수정하거나 품목 설정에서 확인하세요.')
            for l in lines:l['purpose']='INSTALL'
            for l in delivery:l['purpose']='DELIVERY'
            if not lines and not delivery:need(str(row.get('reason','')).strip(),'사용품 없는 행은 제외 사유를 입력하세요.')
            add('VEHICLE',d,lines=lines+delivery,source=source,outbound_id=outid,adjustments_seen=adjustments_seen,label=str(row.get('label',''))[:300],original=row.get('original',[]),codes=row.get('codes',''),delivery_codes=row.get('delivery_codes',''),reason=row.get('reason',''))
    elif action=='cancel':
        need(u.role=='admin','기록 취소는 관리자만 가능합니다.',403);target=next((e for e in live(data) if e['id']==p['id']),None);need(target,'이미 취소되었거나 없는 기록입니다.');reason=str(p.get('reason','')).strip();need(reason,'취소 사유를 입력하세요.');add('CANCEL',target['day'],target=target['id'],reason=reason)
    elif action=='close':
        d=day(p['day']);r=report(data,d);need(not source_warnings(s,data,d),'창고 출고 취소/정정 내역을 먼저 확인하고 부품 기록을 취소·재입력하세요.')
        need(all(x['ending'] is not None and x['ending']>=0 for x in r['rows'] if x['active']),'미확인/부족 재고를 확인하세요. 실사 또는 입출고를 입력해야 마감할 수 있습니다.')
        need(p.get('checked') is True,'당일 입출고 입력 완료를 확인하세요.');data['closings'].append({'day':d,'at':at,'actor':u.username,'signature':r['signature'],'rows':r['rows'],'exports':exports(data,r)})
    else:need(False,'지원하지 않는 작업입니다.')
    b=s.get(PartsBook,1)
    if b:b.data=data;b.revision=rev+1
    else:s.add(PartsBook(id=1,revision=1,data=data))
    result={'revision':rev+1,'ok':True};s.add(PartsRequest(id=request_id,digest=digest,result=result));return result

def exports(data,r):
    items=sorted(data['items'],key=lambda i:(i['order'],i['id']));rs={x['id']:x for x in r['rows']};values=[];groups=set()
    for i in items:
        group=i.get('export_group')
        if group:
            if group in groups:continue
            groups.add(group);members=[j for j in items if j.get('export_group')==group];values.append('/'.join(rs[j['id']]['display'] for j in members))
        else:values.append(rs[i['id']]['display'])
    header=['코드','품목','기초(EA)','입고','차량사용','별도반출','반입','보정','실사차이','마감(EA)','시트표기']
    def safe(v):
        x=str(v if v is not None else '-').replace('\t',' ').replace('\n',' ');return "'"+x if x.startswith(('=','+','@')) or (x.startswith('-') and not re.fullmatch(r'-\d+|-',x)) else x
    rows=[[x[k] for k in ['code','name','opening','inbound','vehicle','outbound','returned','adjustment','count_difference','ending','display']] for x in r['rows']]
    return {'quantities':'\n'.join(values),'table':'\n'.join('\t'.join(safe(v) for v in row) for row in [header]+rows)}

def export(s,u,d):
    need(u.role!='ubis','권한이 없습니다.',403);_,data=load(s);r=report(data,d);need(r['status']=='확정' and not source_warnings(s,data,d),'마감을 확정하거나 재확인한 뒤 복사하세요.');return r['closing']['exports']
