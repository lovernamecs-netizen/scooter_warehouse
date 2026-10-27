"""Purchase sheet source preservation and explicitly reviewed receipt linking."""
import csv,io,json,html,re,hashlib,copy
from collections import Counter
from sqlalchemy import select,func,and_
from .models import PurchaseRecord,Vehicle,Stay,Master,Outbound,VehicleValuation,Command,Guard,uid
from .domain import need,vin,valid_date,today,day,receive,audit,iso

FIELDS=['invoice_date','supplier','representative','received_date','region','model','vin','color','contractor','plate','vat_included','vat_excluded']
HEADERS=['계산서발행일','구매업체명','대표자명','입고일자','보관지역','차종','차대번호','색상','계약자','차량번호','차량가격(VAT포함)','차량가격(VAT제외)']
EXTRA_FIELDS=['serial_number','memo1','memo2','ubis_installation','ubis_number']
ALL_FIELDS=FIELDS+EXTRA_FIELDS
ALL_HEADERS=HEADERS+['시리얼번호','메모 1','메모 2','유비스 설치 여부','유비스번호']

def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def text(x):return html.unescape(str(x or '')).strip().removeprefix('**').removesuffix('**').strip()
def current_query():
 grouped=select(PurchaseRecord.record_id,func.max(PurchaseRecord.revision).label('revision')).group_by(PurchaseRecord.record_id).subquery()
 return select(PurchaseRecord).join(grouped,and_(PurchaseRecord.record_id==grouped.c.record_id,PurchaseRecord.revision==grouped.c.revision))

def latest(s):
 return s.info['_purchase_records'] if '_purchase_records' in s.info else {r.record_id:r for r in s.scalars(current_query())}
def parse(p):
 if 'rows' in p:
  need(isinstance(p['rows'],list),'입력 행 형식 오류');rows=p['rows']
  need(all(isinstance(r,dict) for r in rows),'입력 행 형식 오류')
  return [{k:str(r.get(k,'') or '') for k in ALL_FIELDS if k in FIELDS or k in r} for r in rows]
 source=p.get('text','');need(isinstance(source,str) and len(source)<=1_000_000,'붙여넣기는 1MB 이하입니다.')
 lines=source.strip().splitlines()
 if lines and lines[0].strip().startswith('|'):
  values=[[text(c) for c in line.strip().strip('|').split('|')] for line in lines if not re.fullmatch(r'[\s|:\-]+',line)]
 else:values=list(csv.reader(io.StringIO(source),delimiter='\t'))
 if values and len(values[0]) in [12,17] and [re.sub(r'\s','',text(v)) for v in values[0][:12]]==HEADERS:values=values[1:]
 need(all(len(r) in [12,17] for r in values if any(r)),'12개 또는 17개 열을 그대로 붙여넣으세요. 열 제목 포함/제외 모두 가능합니다.')
 return [dict(zip(ALL_FIELDS,r)) for r in values if any(r)]
def number(v):
 cleaned=re.sub(r'[,\s₩원]','',text(v))
 if not cleaned:return None
 need(bool(re.fullmatch(r'\d+',cleaned)) and int(cleaned)<=10**12,'가격은 0 이상의 원 단위 정수로 입력하세요.')
 return int(cleaned)
def preview(s,u,p):
 need(u.role in ['admin','worker'],'구매 자료 접근 권한이 없습니다.',403)
 raw=parse(p);need(0<len(raw)<=500,'한 번에 1~500행을 입력하세요.')
 need(all(len(value)<=10000 for row in raw for value in row.values()),'한 셀은 10,000자 이하입니다.')
 records=latest(s);existing=list(records.values());choices=p.get('choices',{});need(isinstance(choices,dict),'선택 형식 오류')
 by_source={r.source_key:r for r in existing}
 learned={}
 for record in existing:
  if record.stay_id:
   for kind in ('model','color'):
    if record.data.get(kind+'_id'):learned.setdefault((kind,record.data['values'].get(kind)),set()).add(record.data[kind+'_id'])
 masters={(m.kind,m.name):m for m in s.scalars(select(Master).where(Master.active==True,Master.kind.in_(['model','color'])))}
 occurrence=Counter();seen=set();out=[]
 for index,original in enumerate(raw):
  c=copy.deepcopy(choices.get(str(index),{}));need(isinstance(c,dict),'행 선택 오류')
  info=c.get('import_source',{});xlsx=info.get('kind')=='XLSX'
  data={k:text(v) for k,v in original.items()};errors=[];diff=[];v=None;st=None
  try:
   for key in ['invoice_date','received_date']:
    if data[key]:valid_date(data[key])
   for key in ['vat_included','vat_excluded']:data[key]=number(data[key])
  except Exception:errors.append('날짜 또는 금액 형식을 확인하세요.')
  pending=not data['received_date'] or data['received_date']>today() or data['vin'] in ['','입고예정','미입고'] or data['region']=='미입고'
  normalized=''
  if data['vin'] not in ['','입고예정','미입고']:
   try:normalized=vin(data['vin'])
   except Exception:errors.append('차대번호는 유효한 17자리여야 합니다.')
  if xlsx and (not normalized or info.get('duplicate_identity') or not data['model']):pending=True;normalized=''
  keybase=digest([normalized,data['received_date']]) if normalized else digest(data)
  occurrence[keybase]+=1;source_key=keybase+':'+str(occurrence[keybase])
  if normalized:
   identity=(normalized,data['received_date'])
   if identity in seen:errors.append('이번 입력에 중복 VIN·입고일이 있습니다.')
   seen.add(identity);v=s.scalar(select(Vehicle).where(Vehicle.vin==normalized))
  if xlsx and info.get('source_identity'):
   need(bool(re.fullmatch(r'[a-f0-9]{64}:[1-9][0-9]*',str(info['source_identity']))),'원본 행 식별 오류')
   source_key='xlsx:'+digest([info.get('namespace',info.get('sheet','')),info['source_identity']])
  target_name='368G-V2' if data['model']=='존테스368T-G-V2' else data['model']
  model=s.get(Master,c['model_id']) if c.get('model_id') else masters.get(('model',target_name))
  color=s.get(Master,c['color_id']) if c.get('color_id') else masters.get(('color',data['color']))
  for key in ['model','color']:
   if c.get(key+'_id') or (model if key=='model' else color):continue
   ids=set(learned.get((key,data[key]),set()))
   if len(ids)==1:
    found=s.get(Master,ids.pop())
    if found and found.active and found.kind==key:
     if key=='model':model=found
     else:color=found
  if model:need(model.kind=='model' and model.active,'차종 선택 오류')
  if color:need(color.kind=='color' and color.active,'색상 선택 오류')
  status='미입고 자료' if pending else '시트 기준 재고 반영'
  if not pending and v:
   candidates=list(s.scalars(select(Stay).where(Stay.vehicle_id==v.id)))
   exact=[x for x in candidates if day(x.received_at)==data['received_date']]
   st=next((x for x in candidates if x.id==c.get('stay_id')),None)
   if not st:st=exact[0] if len(exact)==1 else candidates[0] if len(candidates)==1 else None
   if not st:diff.append('입고 회차가 여러 개입니다. 연결 회차를 선택하세요.')
   elif day(st.received_at)!=data['received_date']:diff.append('입고일 차이 · 시트 날짜 적용')
   if not model or model.id!=v.model_id:diff.append('차종 불일치/미연결')
   if not color or color.id!=v.color_id:diff.append('색상 불일치/미연결')
   status='시트 기준 · 기존 출고 유지' if st and st.closed_at else '시트 기준 · 기존 차량 참고 연결'
  if not pending and not v and (not model or not color):diff.append('차종/색상 매핑 필요')
  prior=records.get(c.get('record_id')) if c.get('record_id') else by_source.get(source_key)
  if not prior and not xlsx and normalized and not info.get('duplicate_identity'):
   related=[r for r in existing if text(r.data['values'].get('vin')).upper()==normalized]
   same_stay=[r for r in related if st and r.stay_id==st.id]
   if len(same_stay)==1:prior=same_stay[0]
   elif len(related)==1 and sum(text(x.get('vin')).upper()==normalized for x in raw)==1:prior=related[0]
  if c.get('record_id'):need(prior,'수정할 자료를 찾을 수 없습니다.')
  if 'ubis_installation' in data:
   mark=data['ubis_installation'];num=data.get('ubis_number','')
   if not ((mark=='유비스' and num) or (not mark and not num)):errors.append('유비스 설치 표기와 번호를 함께 입력하거나 둘 다 비워주세요.')
  sheet_ids={k:data[k] for k in ['serial_number','ubis_number'] if k in data}
  if sheet_ids and not xlsx:c['identifiers']={**c.get('identifiers',{}),**sheet_ids}
  identifiers=c.get('identifiers')
  if identifiers is not None:
   need(isinstance(identifiers,dict) and set(identifiers)<= {'serial_number','ubis_number'},'번호 입력 형식 오류')
   need(all(isinstance(value,str) and len(value)<=120 for value in identifiers.values()),'번호는 120자 이하로 입력하세요.')
  if xlsx:
   diff.extend(errors);errors=[]
   if v and not st: v=None
   for key in ['vat_included','vat_excluded']:
    try:data[key]=number(original[key])
    except Exception:data[key]=None
   for key in ['invoice_date','received_date']:
    try:
     if data[key]:valid_date(data[key])
    except Exception:
     data[key]=''
     if key=='received_date':pending=True
   status='원본 자료 저장'
  out.append({'index':index,'original':original,'data':data,'normalized_vin':normalized,'source_key':source_key,'status':status,'pending':pending,'differences':diff,'errors':errors,'model_id':model.id if model else None,'color_id':color.id if color else None,'vehicle_id':v.id if v else None,'vehicle_version':v.version if v else None,'stay_id':st.id if st else None,'existing_received_dates':[day(x.received_at) for x in s.scalars(select(Stay).where(Stay.vehicle_id==v.id))] if v else [],'record_id':prior.record_id if prior else None,'record_revision':prior.revision if prior else 0,'choice':c})
  out[-1]['stay_choices']=[{'id':x.id,'received_date':day(x.received_at),'closed':bool(x.closed_at)} for x in s.scalars(select(Stay).where(Stay.vehicle_id==v.id))] if v else []
  out[-1]['existing_vehicle']={'model':s.get(Master,v.model_id).name,'color':s.get(Master,v.color_id).name} if v else None
 return {'rows':out,'token':digest([out,[x.id for x in s.scalars(select(VehicleValuation).order_by(VehicleValuation.id))]])}
def xlsx_import(c):return c.get('import_source',{}).get('kind')=='XLSX'

def apply(s,u,p,_checked=None):
 need(u.role in ['admin','worker'],'변경 권한이 없습니다.',403)
 rid=p.get('request_id','');need(isinstance(rid,str) and 16<=len(rid)<=100,'요청 ID 오류');hashed=digest(p);old=s.get(Command,rid)
 if old:need(old.user_id==u.id and old.digest==hashed,'요청 ID 충돌',409);return old.result
 result=_checked if _checked is not None else preview(s,u,p);need(result['token']==p.get('token'),'대조 기준이 변경되었습니다. 다시 검수하세요.',409)
 need(all(not r['errors'] for r in result['rows']),'오류 행을 수정한 뒤 검수하세요.')
 saved=[];skipped=0;current_records=latest(s)
 for row in result['rows']:
  c=row['choice'];vid=row['vehicle_id'];sid=row['stay_id'];model=row['model_id'];color=row['color_id']
  if c.get('create'):
   need(not row['pending'] and not vid and model and color and not row['differences'],'신규 입고 조건을 확인하세요.')
   need(c.get('kind') in ['NEW','USED'],'신차/중고를 선택하세요.')
   from .vehicle_inventory import capture,record_changes
   before=capture(s)
   vid=receive(s,u,{'vin':row['normalized_vin'],'model_id':model,'color_id':color,'year':c.get('year'),'kind':c['kind'],'received_date':row['data']['received_date']})['vehicle_id'];record_changes(s,before,u.username)
   sid=s.scalar(select(Stay).where(Stay.vehicle_id==vid,Stay.closed_at==None)).id
  payload={'source':row['original'],'values':row['data'],'model_id':model,'color_id':color,'status':'미입고 자료' if row['pending'] else '시트 기준 재고','differences':row['differences'],'pending':row['pending']}
  if c.get('import_source',{}).get('kind')=='XLSX':payload['status']='원본 자료 저장'
  prior=current_records.get(row['record_id'])
  if prior and xlsx_import(c):
   # Re-import is never an implicit undo of an operator edit or deletion.
   if prior.data.get('deleted') or prior.data.get('local_override'):
    skipped+=1
    if '_purchase_bindings' in s.info:s.info['_purchase_bindings'].append({'row':c['import_source']['row'],'id':prior.record_id,'revision':prior.revision})
    continue
  if prior and 'import_source' in prior.data:payload['import_source']=prior.data['import_source']
  elif c.get('import_source'):
   info=c['import_source'];need(isinstance(info,dict) and info.get('kind')=='XLSX' and isinstance(info.get('row'),int) and 2<=info['row']<=20000 and bool(re.fullmatch('[a-f0-9]{64}',str(info.get('sha256','')))),'가져오기 출처 오류');payload['import_source']={k:info[k] for k in ['kind','sha256','sheet','row','namespace','label'] if k in info}
  if prior:
   for key in EXTRA_FIELDS:
    for section in ['source','values']:
     if key not in payload[section] and key in prior.data[section]:payload[section][key]=prior.data[section][key]
  if xlsx_import(c):payload['import_baseline']=copy.deepcopy(row['original'])
  if c.get('import_source',{}).get('source_cells'):payload['source_cells']=c['import_source']['source_cells']
  if prior and 'identifiers' in prior.data:payload['identifiers']=dict(prior.data['identifiers'])
  if c.get('identifiers') is not None:
   payload['identifiers']={**payload.get('identifiers',{}),**{k:value.strip() for k,value in c['identifiers'].items()}}
   if vid:
    vehicle=s.get(Vehicle,vid);updates={k:value.strip() for k,value in c['identifiers'].items() if getattr(vehicle,k)!=value.strip()}
    if updates:
     from .domain import execute
     execute(s,u,'vehicle_edit',{'vehicle_id':vid,'version':vehicle.version,**updates})
  payload['inventory_kind']=(s.get(Vehicle,vid).kind if vid else (c.get('kind') if c.get('create') else None) or (prior.data.get('inventory_kind') if prior else None) or 'UNKNOWN')
  if vid and not row['pending']:need(sid,'재입고 이력이 여러 개입니다. 연결 회차만 선택하세요.')
  if prior and prior.stay_id:need(prior.stay_id==sid,'연결된 자료의 VIN·입고 회차를 바꿀 수 없습니다. 원본 입고 기록을 먼저 확인하세요.',409)
  if prior and any(prior.data['values'].get(k)!=payload['values'].get(k) for k in ('vat_included','vat_excluded')):payload['value_effective_day']=today()
  elif prior and prior.data.get('value_effective_day'):payload['value_effective_day']=prior.data['value_effective_day']
  actual=prior
  if prior and prior.data==payload and prior.vehicle_id==vid and prior.stay_id==sid:skipped+=1
  else:
   if prior:need(str(p.get('reason','')).strip(),'기존 자료 변경 사유를 입력하세요.')
   # One source record per linked receipt; never silently duplicate a reviewed link.
   linked=next((r for r in current_records.values() if sid and r.stay_id==sid and (not prior or r.record_id!=prior.record_id)),None)
   need(not linked,'이미 다른 구매 자료에 연결된 입고 회차입니다. 해당 자료를 수정하세요.',409)
   rec=PurchaseRecord(record_id=prior.record_id if prior else uid(),revision=prior.revision+1 if prior else 1,source_key=row['source_key'],data=payload,vehicle_id=vid,stay_id=sid,actor=u.username);s.add(rec);s.flush();saved.append(rec.record_id);current_records[rec.record_id]=rec;actual=rec
   audit(s,u,'PURCHASE_SHEET_SAVED',{'record_id':rec.record_id,'revision':rec.revision,'reason':p.get('reason','')},s.get(Vehicle,vid) if vid else None)
  if '_purchase_bindings' in s.info:s.info['_purchase_bindings'].append({'row':c['import_source']['row'],'id':actual.record_id,'revision':actual.revision})
 response={'ok':True,'saved':len(saved),'unchanged':skipped};s.add(Command(id=rid,user_id=u.id,digest=hashed,result=response));s.get(Guard,1).revision+=1;return response
def listing(s,u):
 need(u.role in ['admin','worker'],'구매 자료 접근 권한이 없습니다.',403)
 rows=[{'id':r.record_id,'revision':r.revision,'data':r.data,'vehicle_id':r.vehicle_id,'stay_id':r.stay_id,'actor':r.actor,'at':iso(r.at)} for r in latest(s).values()]
 for row in rows:
  vehicle=s.get(Vehicle,row['vehicle_id']) if row['vehicle_id'] else None
  row['identifiers']={k:getattr(vehicle,k) if vehicle else row['data'].get('identifiers',{}).get(k,'') for k in ['serial_number','ubis_number']}
 return {'headers':ALL_HEADERS,'fields':ALL_FIELDS,'rows':rows,'masters':[{'id':m.id,'kind':m.kind,'name':m.name} for m in s.scalars(select(Master).where(Master.active==True,Master.kind.in_(['model','color'])))],'history':[{'id':r.record_id,'revision':r.revision,'data':r.data,'at':iso(r.at),'actor':r.actor} for r in s.scalars(select(PurchaseRecord))]}
