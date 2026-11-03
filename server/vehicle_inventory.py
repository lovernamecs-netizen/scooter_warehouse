"""Versioned, vehicle-only daily inventory. Source movement and closing rows stay intact."""
import calendar,copy,hashlib,json,logging
from collections import Counter
from datetime import date,datetime,time,timedelta,timezone
from sqlalchemy import select
from .models import (Vehicle,Master,Stay,Outbound,Adjustment,History,Setting,PurchaseRecord,now,
 VehicleInventorySnapshot as Snapshot,VehicleInventoryEvent as Event,
 VehicleValuation as Price,VehicleInventoryFact as Fact,VehicleInventoryRequest as Request)
from .domain import need,admin,valid_date,today,KST,iso,day as local_day

ALGORITHM=1
IMMUTABLE_TABLES=['vehicle_inventory_snapshots','vehicle_inventory_events','vehicle_valuations','vehicle_inventory_facts','vehicle_inventory_requests']
def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def utc(t):return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)
def boundary(d):return datetime.combine(date.fromisoformat(valid_date(d))+timedelta(days=1),time.min,KST).astimezone(timezone.utc)
def allrows(s,cls):return list(s.scalars(select(cls)))
def attrs(s,v):
 model=s.get(Master,v.model_id);brand=s.get(Master,(model.detail or {}).get('brand_id','')) if model else None
 return {'vehicle_id':v.id,'vin':'' if v.vin.startswith('@PENDING:') else v.vin,'reference':'임시-'+v.id[:8], 'model_id':v.model_id,'model':model.name if model else '미확인','brand_id':brand.id if brand else '', 'brand':brand.name if brand else '미확인','kind':v.kind}
def capture(s):return {v.id:attrs(s,v) for v in allrows(s,Vehicle)}
def record_changes(s,before,actor):
 s.flush()
 for v in allrows(s,Vehicle):
  value=attrs(s,v)
  if before.get(v.id)==value:continue
  effective=now()
  if v.id not in before:
   st=s.scalar(select(Stay).where(Stay.vehicle_id==v.id).order_by(Stay.received_at));effective=st.received_at if st else effective
  s.add(Fact(vehicle_id=v.id,effective_at=effective,data=value,actor=actor))
def initialize(s):
 row=s.get(Setting,'vehicle_inventory_start')
 if row:return row.value['day']
 start=today();s.add(Setting(key='vehicle_inventory_start',value={'day':start}))
 existing={f.vehicle_id for f in allrows(s,Fact)}
 for v in allrows(s,Vehicle):
  if v.id not in existing:s.add(Fact(vehicle_id=v.id,effective_at=now(),data=attrs(s,v),actor='system'))
 s.flush();return start

def source_data(s):
 return {cls.__name__:(list(s.scalars(select(History).where(History.event.in_(['ARCHIVED','DELETED','MOVED','READY','ASSIGNED','ORDER_CANCELLED'])))) if cls is History else allrows(s,cls)) for cls in [Vehicle,Master,Stay,Outbound,Adjustment,History,Fact,Price,Event,PurchaseRecord]}
def valuation(data,row,d):
 eligible=[p for p in data[Price.__name__] if p.effective_day<=d and p.vehicle_kind==row['kind']]
 def last(scope,key):return max([p for p in eligible if p.scope==scope and p.target_id==key],key=lambda p:(p.effective_day,utc(p.at),p.id),default=None)
 base=last('MODEL',row['model_id']);individual=last('VEHICLE',row['vehicle_id']);chosen=individual or base
 return {'default_value':base.amount if base else None,'individual_value':individual.amount if individual else None,'has_individual_value':individual is not None,'value':chosen.amount if chosen else None,'value_source':chosen.scope if chosen else None,'price_id':chosen.id if chosen else None}
def reconstruct(s,d,data=None):
 valid_date(d);need(d<=today(),'미래 날짜는 집계할 수 없습니다.')
 data=data or source_data(s);end=boundary(d) if d<today() else now();end=utc(end)
 vehicles={v.id:v for v in data['Vehicle']};stays={st.id:st for st in data['Stay']};outs={o.stay_id:o for o in data['Outbound']};by_out={o.id:o for o in data['Outbound']}
 from .purchase_inventory import overlay,inventory_row
 stays,sheet_rows,warnings=overlay(data)
 masters={m.id:m for m in data['Master']};selected={};voids={a.outbound_id:a for a in data['Adjustment'] if a.kind=='VOID'}
 for st in stays.values():
  included=utc(st.received_at)<end and (st.closed_at is None or utc(st.closed_at)>=end)
  out=outs.get(st.id)
  # A VOID bridges the erroneous dispatch interval up to the replacement stay.
  adj=voids.get(out.id) if out else None
  if adj and utc(out.at)<end<=utc(adj.at):included=True
  if included:selected[st.id]=st
  if st.closed_at and utc(st.closed_at)<end and not out:
   known=any(h.vehicle_id==st.vehicle_id and h.event in ['ARCHIVED','DELETED'] and abs((utc(h.at)-utc(st.closed_at)).total_seconds())<2 for h in data['History'])
   if not known:warnings.append('종료 근거 미확인: '+st.id)
  if out and st.closed_at is None:warnings.append('출고·입고 회차 종료 불일치: '+st.id)
 # Latest correction for each stay wins; reversal restores that correction's previous decision.
 corrections=sorted([e for e in data[Event.__name__] if e.kind=='CORRECTION' and e.day<=d],key=lambda e:(utc(e.at),e.id))
 applied=[]
 for event in corrections:
  if event.data.get('until') and d>event.data['until']:continue
  for change in event.data.get('changes',[]):
   st=stays.get(change['stay_id'])
   if not st: warnings.append('보정 회차 미확인');continue
   # A correction never keeps an old stay in stock after a later real dispatch/closure.
   if st.closed_at and utc(st.closed_at)<end:continue
   applied.append({'event':event.id,'stay_id':st.id,'include':change['include']})
   if change['include']:selected[st.id]=st
   else:selected.pop(st.id,None)
 records=[];seen=set()
 for st in sorted(selected.values(),key=lambda st:st.id):
  if st.vehicle_id in seen:warnings.append('입고 회차 중첩: '+st.vehicle_id);continue
  seen.add(st.vehicle_id);v=vehicles.get(st.vehicle_id)
  if st.id in sheet_rows:
   records.append(inventory_row(sheet_rows[st.id],st,masters,vehicles,outs));continue
  if not v:warnings.append('차량 연결 누락: '+st.id);continue
  facts=[f for f in data[Fact.__name__] if f.vehicle_id==v.id and utc(f.effective_at)<end]
  fact=max(facts,key=lambda f:(utc(f.effective_at),utc(f.at),f.id),default=None)
  if fact:row=copy.deepcopy(fact.data);quality='RECORDED'
  else:
   out=outs.get(st.id);snap=(out.snapshot.get('vehicle',{}) if out else {})
   model=masters.get(v.model_id);brand=masters.get((model.detail or {}).get('brand_id','')) if model else None
   row={'vehicle_id':v.id,'vin':'' if v.vin.startswith('@PENDING:') else v.vin,'reference':'임시-'+v.id[:8],'model_id':v.model_id,'model':model.name if model else '미확인','brand_id':brand.id if brand else '', 'brand':brand.name if brand else '미확인','kind':v.kind}
   row.update({k:snap[k] for k in row if k in snap});quality='OUTBOUND_REFERENCE' if snap else 'CURRENT_REFERENCE'
  row.update(stay_id=st.id,classification_quality=quality)
  row.update(valuation(data,row,d));records.append(row)
 records.sort(key=lambda r:(r['brand'],r['model'],r['kind'],r['vehicle_id']))
 groups={}
 for r in records:
  key=r['model_id']+':'+r['kind'];g=groups.setdefault(key,{'key':key,'brand':r['brand'],'brand_id':r['brand_id'],'model':r['model'],'model_id':r['model_id'],'kind':r['kind'],'count':0,'known_value':0,'missing_value':0,'vehicles':[]})
  g['count']+=1;g['known_value']+=r['value'] or 0;g['missing_value']+=int(r['value'] is None);g['vehicles'].append(r)
 moves={'received':0,'reentered':0,'dispatched':0,'removed':0,'voided':0}
 for st in stays.values():
  if local_day(st.received_at)==d:
   if st.reason=='VOID':continue
   moves['received' if st.reason=='RECEIPT' else 'reentered']+=1
  if st.closed_at and local_day(st.closed_at)==d and st.id not in outs:moves['removed']+=1
 for out in outs.values():
  if out.day==d:
   if out.id in voids:moves['voided']+=1
   else:moves['dispatched']+=1
 result={'day':d,'algorithm':ALGORITHM,'vehicles':records,'groups':list(groups.values()),'count':len(records),'known_value':sum(r['value'] or 0 for r in records),'missing_value':sum(r['value'] is None for r in records),'uncertain_classification':sum(r['classification_quality'] not in ['RECORDED','SHEET'] for r in records),'no_evidence':not records and not any(utc(st.received_at)<end for st in stays.values()),'warnings':sorted(set(warnings)),'movements':moves,'corrections':applied}
 result['signature']=digest(result)
 if sheet_rows:result['sheet_basis']=True
 return result

def latest(s,d):return s.scalar(select(Snapshot).where(Snapshot.day==d).order_by(Snapshot.version.desc()))
def store(s,d,source,actor,expected=None):
 need(d<today(),'오늘은 예상 재고입니다. 날짜 종료 후 기록할 수 있습니다.')
 current=reconstruct(s,d);need(not current['no_evidence'],'입출고 기록 시작 전 날짜입니다. 근거 확인이 필요합니다.');need(not current['warnings'],{'message':'원본 입출고 근거를 확인하세요.','warnings':current['warnings']})
 prior=latest(s,d)
 if expected is not None:need((prior.id if prior else None)==expected,'기준 버전이 변경되었습니다.',409)
 snapshot=Snapshot(day=d,version=prior.version+1 if prior else 1,source=source,signature=current['signature'],data=current,previous_id=prior.id if prior else None,actor=actor);s.add(snapshot);s.flush();return snapshot

def detail(s,d,data=None):
 current=reconstruct(s,d,data);snap=latest(s,d);events=list(s.scalars(select(Event).where(Event.day==d).order_by(Event.at,Event.id)))
 inspection=next((e for e in reversed(events) if e.kind=='INSPECTION'),None)
 stale=bool(snap and snap.signature!=current['signature'])
 if inspection and (not snap or utc(inspection.at)>=utc(snap.at)) and inspection.signature!=current['signature']:stale=True
 status='집계 대기'
 if snap:status='정정 완료' if snap.source=='CORRECTED' else '자동 집계 완료'
 if inspection and (not snap or utc(inspection.at)>=utc(snap.at)):
  status='재고 차이 발생' if inspection.data['different'] else '실사 확인 완료' if inspection.data['complete'] else status
 if stale:status='재확인 필요'
 if current['warnings']:status='재확인 필요'
 token=digest({'day':d,'current':current['signature'],'snapshot':snap.id if snap else None,'events':[e.id for e in events]})
 shown=copy.deepcopy(current if current.get('sheet_basis') else snap.data if snap else current)
 previous=reconstruct(s,(date.fromisoformat(d)-timedelta(days=1)).isoformat(),data)
 movement=current['movements'];flow={'opening':previous['count'],**movement,'closing':current['count']}
 flow['correction_delta']=current['count']-previous['count']-movement['received']-movement['reentered']+movement['dispatched']+movement['removed']
 return {'day':d,'today':today(),'status':status,'saved_outdated':bool(snap and snap.signature!=current['signature']),'flow':flow,'token':token,'saved':{'id':snap.id,'version':snap.version,'source':snap.source,'at':iso(snap.at),'actor':snap.actor} if snap else None,'display':shown,'current':current,'inspection':{'id':inspection.id,'actor':inspection.actor,'at':iso(inspection.at),'data':inspection.data,'stale':inspection.signature!=current['signature']} if inspection else None,'events':[{'id':e.id,'kind':e.kind,'at':iso(e.at),'actor':e.actor,'data':e.data} for e in events],'versions':[{'id':v.id,'version':v.version,'source':v.source,'at':iso(v.at),'actor':v.actor,'data':v.data} for v in s.scalars(select(Snapshot).where(Snapshot.day==d).order_by(Snapshot.version.desc()))]}

def view(s,u,d,month):
 need(u.role!='ubis','조회 권한이 없습니다.',403);valid_date(d)
 try:first=date.fromisoformat(month+'-01');need(first.strftime('%Y-%m')==month,'월 형식 오류')
 except ValueError:need(False,'월 형식 오류')
 data=source_data(s);cells=[]
 for n in range(1,calendar.monthrange(first.year,first.month)[1]+1):
  datekey=first.replace(day=n).isoformat()
  if datekey>today():cells.append({'day':datekey,'future':True});continue
  item=detail(s,datekey,data);cells.append({'day':datekey,'count':None if item['display'].get('no_evidence') else item['display']['count'],'status':item['status'],'saved':bool(item['saved']),'source':item['saved']['source'] if item['saved'] else 'LIVE' if datekey==today() else 'RECONSTRUCTED','inspection':bool(item['inspection']),'difference':bool(item['inspection'] and item['inspection']['data']['different'])})
 result=detail(s,d,data) if d<=today() else {'day':d,'today':today(),'future':True}
 result.update(month=month,calendar=cells,models=[{'id':m.id,'name':m.name,'brand_id':m.detail.get('brand_id','')} for m in data['Master'] if m.kind=='model' and m.active],prices=[{'id':p.id,'scope':p.scope,'target_id':p.target_id,'kind':p.vehicle_kind,'effective_day':p.effective_day,'amount':p.amount,'reason':p.reason,'at':iso(p.at),'actor':p.actor} for p in sorted(data[Price.__name__],key=lambda x:utc(x.at),reverse=True)])
 return result

def number(x):
 need(isinstance(x,int) and not isinstance(x,bool) and 0<=x<=10**12,'0 이상의 정수를 입력하세요.');return x

def mutate(s,u,p):
 need(u.role in ['admin','worker'],'변경 권한이 없습니다.',403)
 rid=p.get('request_id');need(isinstance(rid,str) and 16<=len(rid)<=100,'요청 ID 오류');h=digest([u.id,p]);prior=s.get(Request,rid)
 if prior:need(prior.digest==h,'같은 요청 ID의 내용이 다릅니다.',409);return prior.result
 action=p.get('action');d=valid_date(p.get('day',''));need(d<=today(),'미래 날짜는 확정할 수 없습니다.')
 state=detail(s,d);need(p.get('token')==state['token'],'기준 재고가 변경되었습니다. 새로 조회하고 확인하세요.',409)
 reason=str(p.get('reason','')).strip();need(len(reason)<=1000,'사유가 너무 깁니다.')
 if action=='price':
  admin(u);need(reason,'가액 변경 사유가 필요합니다.');scope=p.get('scope');kind=p.get('kind');need(scope in ['MODEL','VEHICLE'] and kind in ['NEW','USED'],'가액 구분 오류')
  target=s.get(Master if scope=='MODEL' else Vehicle,p.get('target_id'));need(target and (scope!='MODEL' or target.kind=='model'),'가액 대상 오류')
  amount=p.get('amount');need(amount is None or isinstance(amount,int),'가액 형식 오류')
  if amount is not None:number(amount)
  effective=valid_date(p.get('effective_day',d));need(effective<=today(),'미래 가액은 현재 등록할 수 없습니다.')
  s.add(Price(scope=scope,target_id=target.id,vehicle_kind=kind,effective_day=effective,amount=amount,reason=reason,actor=u.username));s.flush()
 elif action=='inspection':
  mode=p.get('mode');need(mode in ['COUNT','VIN'],'실사 방식 오류');basis=state['display'];need(not (state['saved'] and state['saved']['id'] and basis['signature']!=state['current']['signature']),'재확인 필요한 원본을 먼저 관리자 재집계하세요.',409)
  expected={g['key']:g['count'] for g in basis['groups']};difference=[];missing=[];unexpected=[]
  if mode=='COUNT':
   counts=p.get('counts');need(isinstance(counts,dict) and (counts or not expected and p.get('complete') is True),'확인한 품목 수량을 입력하세요.')
   for key,value in counts.items():
    mid,sep,kind=key.rpartition(':');m=s.get(Master,mid);need(key in expected or m and m.kind=='model' and kind in ['NEW','USED'],'차종 그룹 오류');number(value)
    if value!=expected.get(key,0):difference.append({'key':key,'system':expected.get(key,0),'physical':value,'delta':value-expected.get(key,0)})
   complete=p.get('complete') is True and set(expected)<=set(counts);physical=sum(counts.values());actual=counts
  else:
   ids=p.get('vehicle_ids');need(isinstance(ids,list) and len(ids)==len(set(ids)),'중복 차량 확인값입니다.');need(all(s.get(Vehicle,k) or any(r['vehicle_id']==k for r in basis['vehicles']) for k in ids),'등록되지 않은 차량입니다.')
   expected_ids={r['vehicle_id'] for r in basis['vehicles']};complete=p.get('complete') is True;missing=sorted(expected_ids-set(ids)) if complete else [];unexpected=sorted(set(ids)-expected_ids);physical=len(ids);actual=ids
  different=bool(difference or missing or unexpected);need(not different or reason,'불일치 사유를 입력하세요.')
  payload={'mode':mode,'actual':actual,'complete':complete,'different':different,'system_count':basis['count'],'physical_count':physical,'delta':physical-basis['count'] if complete else None,'groups':difference,'missing_vehicle_ids':missing,'unexpected_vehicle_ids':unexpected,'vin_mismatch_unresolved':mode=='COUNT' and different,'reason':reason,'basis':basis,'unexpected_details':[attrs(s,s.get(Vehicle,k)) for k in unexpected]}
  s.add(Event(day=d,kind='INSPECTION',basis_id=state['saved']['id'] if state['saved'] else None,signature=state['current']['signature'],data=payload,actor=u.username))
 elif action in ['rebuild','correct']:
  admin(u);need(d<today(),'오늘은 예상 재고입니다. 날짜 종료 후 정정하세요.');need(reason,'정정 사유를 입력하세요.')
  if not state['saved']:store(s,d,'RECONSTRUCTED',u.username)
  if action=='correct':
   changes=p.get('changes');need(isinstance(changes,list) and 0<len(changes)<=500,'보정할 차량을 선택하세요.');need(len({x.get('stay_id') for x in changes})==len(changes),'중복 보정 회차입니다.')
   until=p.get('until') or None
   if until:valid_date(until);need(d<=until<=today(),'보정 종료일을 확인하세요.')
   affected=[]
   for x in changes:
    st=s.get(Stay,x.get('stay_id'));need(st is not None and isinstance(x.get('include'),bool),'보정 대상 오류')
    need(not st.closed_at or utc(st.closed_at)>=boundary(d),'이미 실제 종료된 회차입니다. 원 출고 정정 절차를 먼저 확인하세요.')
    before=any(r['stay_id']==st.id for r in state['current']['vehicles']);need(before!=x['include'],'현재 재고와 같은 보정입니다.')
    affected.append({'stay_id':st.id,'vehicle_id':st.vehicle_id,'include':x['include'],'before_include':before})
   event=Event(day=d,kind='CORRECTION',basis_id=state['saved']['id'] if state['saved'] else latest(s,d).id,signature=state['current']['signature'],data={'reason':reason,'changes':affected,'until':until,'inspection_id':p.get('inspection_id'),'reverses':p.get('reverses')},actor=u.username);s.add(event);s.flush()
  snap=store(s,d,'CORRECTED',u.username)
  s.add(Event(day=d,kind='REBUILT',basis_id=snap.id,signature=snap.signature,data={'reason':reason,'before_count':state['display']['count'],'after_count':snap.data['count']},actor=u.username))
 else:need(False,'지원하지 않는 차량 재고 명령입니다.')
 s.flush();result={'ok':True,'day':d};s.add(Request(id=rid,digest=h,result=result));return result

def candidates(s,u,d):
 need(u.role in ['admin','worker'],'권한이 없습니다.',403);valid_date(d)
 result=[]
 for st in allrows(s,Stay):
  v=s.get(Vehicle,st.vehicle_id)
  if not v:continue
  value=attrs(s,v);value.update(stay_id=st.id,received_at=iso(st.received_at),closed_at=iso(st.closed_at));result.append(value)
 real_ids={r['vehicle_id'] for r in result}
 for row in reconstruct(s,d)['vehicles']:
  if row['vehicle_id'] not in real_ids:result.append({**row,'received_at':row.get('source_received_date'),'closed_at':None,'sheet_only':True})
 return result

def backfill(db,limit=20):
 with db.transaction() as s:
  start=initialize(s)
  from .purchase_inventory import overlay
  effective,_,_=overlay(source_data(s));stays=list(effective.values())
  if not stays:return 0
  first=min(local_day(st.received_at) for st in stays);existing={x.day for x in allrows(s,Snapshot)}
  pending=[];d=date.fromisoformat(first);last=date.fromisoformat(today())
  while d<last and len(pending)<limit:
   key=d.isoformat()
   if key not in existing:pending.append(key)
   d+=timedelta(days=1)
 count=0;failed=[]
 for d in pending:
  try:
   with db.transaction() as s:
    if latest(s,d):continue
    store(s,d,'AUTO' if d>=start else 'RECONSTRUCTED','system');count+=1
  except Exception as error:
   failed.append({'day':d,'error':type(error).__name__})
   logging.getLogger('vehicle_inventory').error('Inventory day %s needs review: %s',d,type(error).__name__)
 with db.transaction() as s:
  row=s.get(Setting,'vehicle_inventory_job') or Setting(key='vehicle_inventory_job')
  row.value={'at':iso(now()),'failed':failed,'saved':count};s.add(row)
 return count

def scheduler(db,stop):
 while not stop.is_set():
  try:
   count=backfill(db)
   if count==20:
    if stop.wait(.2):break
    continue
  except Exception as error:logging.getLogger('vehicle_inventory').error('Vehicle inventory catch-up failed: %s',type(error).__name__)
  if stop.wait(60):break
