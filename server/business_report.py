"""Vehicle daily business summary. Original closing snapshots remain immutable."""
from collections import defaultdict
from sqlalchemy import select
from .models import Assignment,PurchaseRecord,Stay,Vehicle
from .vehicle_inventory import reconstruct,source_data,utc,boundary,valuation
from .domain import today,location,day
from .warehouses import config

def report(s,d):
 from .parts_orders import effective_outbounds
 data=source_data(s);stock=reconstruct(s,d,data);end=utc(boundary(d));current=d==today()
 history=defaultdict(list)
 for h in data['History']:
  if utc(h.at)<end:history[h.vehicle_id].append(h)
 for events in history.values():events.sort(key=lambda h:(utc(h.at),h.id))
 active={a.stay_id:a for a in s.scalars(select(Assignment).where(Assignment.status=='ACTIVE'))}
 stays={st.id:st for st in data['Stay']};vehicles={v.id:v for v in data['Vehicle']}
 prices=defaultdict(list)
 for rec in data['PurchaseRecord']:
  effective=rec.data.get('value_effective_day') or rec.data.get('values',{}).get('received_date','')
  if effective and effective<=d:prices[rec.record_id].append(rec)
 valued={}
 for ident,items in prices.items():valued[ident]=max(items,key=lambda r:(r.data.get('value_effective_day') or r.data['values'].get('received_date',''),r.revision))
 priced_groups=defaultdict(list)
 for rec in valued.values():priced_groups[(rec.data['values'].get('vin','').strip().upper(),rec.data['values'].get('received_date'))].append(rec)
 def amount(row):
  if row.get('purchase_record_id'):
   original=valued.get(row['purchase_record_id'])
   if not original:return None,None,None
   candidates=priced_groups.get((row['vin'],original.data['values'].get('received_date')),[])
   pairs={(r.data['values'].get('vat_included'),r.data['values'].get('vat_excluded')) for r in candidates}
   if len(pairs)>1:
    stock['warnings'].append('동일 VIN 원본 가액 차이: '+row['vin']);return None,None,None
   return original.data['values'].get('vat_included'),original.data['values'].get('vat_excluded'),original.id
  return row.get('value'),None,row.get('price_id')
 names={w['id']:w['name'] for w in config(s)['items']}
 buckets={name:{'name':name,'unsold':0,'waiting':0,'unknown':0,'count':0,'value':0,'value_excluded':0,'missing':0,'missing_excluded':0,'unsold_value':0,'waiting_value':0} for name in names.values()}
 def place(vid,st):
  if current and st and vid in vehicles:return location(s,st)
  events=[h for h in history.get(vid,[]) if (not st or utc(h.at)>=utc(st.received_at)) and h.event in ('MOVED','READY') and 'to' in h.data]
  return events[-1].data['to'] if events else None
 def bucket_name(loc):return (names.get(loc.get('warehouse_id')) or loc.get('warehouse') or '공통 출고대기') if loc else '위치 확인 필요'
 details=[];unlinked=[]
 for row in stock['vehicles']:
  vid=row['vehicle_id'];st=stays.get(row['stay_id'])
  if not st or vid not in vehicles:
   value,excluded,price_id=amount(row);unlinked.append({'vin':row['vin'],'model':row['model'],'value':value,'value_excluded':excluded,'price_id':price_id});continue
  loc=place(vid,st);name=bucket_name(loc)
  state='unknown'
  if st and vid in vehicles:
   if current:state='waiting' if st.id in active else 'unsold'
   else:
    events=[h for h in history.get(vid,[]) if utc(h.at)>=utc(st.received_at) and h.event in ('ASSIGNED','ORDER_CANCELLED')]
    state=('waiting' if events[-1].event=='ASSIGNED' else 'unsold') if events else 'unknown'
  value,excluded,price_id=amount(row)
  bucket=buckets.setdefault(name,{'name':name,'unsold':0,'waiting':0,'unknown':0,'count':0,'value':0,'value_excluded':0,'missing':0,'missing_excluded':0,'unsold_value':0,'waiting_value':0})
  bucket[state]+=1;bucket['count']+=1;bucket['value']+=value or 0;bucket['value_excluded']+=excluded or 0;bucket['missing']+=value is None;bucket['missing_excluded']+=excluded is None
  if state in ('unsold','waiting'):bucket[state+'_value']+=value or 0
  details.append({'vin':row['vin'],'model':row['model'],'warehouse':name,'state':state,'value':value,'value_excluded':excluded,'price_id':price_id})
 delivered=[]
 for out in effective_outbounds(s,d):
  v=out.snapshot['vehicle'];loc=v.get('location');matched=[r for r in data['PurchaseRecord'] if r.stay_id==out.stay_id or (r.data['values'].get('vin','').strip().upper()==v['vin'] and r.data['values'].get('received_date')==day(stays[out.stay_id].received_at))]
  latest_matched={r.record_id:valued.get(r.record_id) for r in matched}
  candidates=[r for r in latest_matched.values() if r and (r.data.get('value_effective_day') or r.data['values'].get('received_date',''))<=d]
  rec=max(candidates,key=lambda r:(r.data.get('value_effective_day') or r.data['values'].get('received_date',''),r.revision),default=None)
  value=rec.data['values'].get('vat_included') if rec else None;excluded=rec.data['values'].get('vat_excluded') if rec else None
  if rec is None:value=valuation(data,{**v,'vehicle_id':out.vehicle_id},d)['value']
  if len({(r.data['values'].get('vat_included'),r.data['values'].get('vat_excluded')) for r in candidates})>1:value=None;excluded=None
  if not loc or not loc.get('warehouse_id'):
   places=[h.data.get('to') or h.data.get('from') for h in history.get(out.vehicle_id,[]) if h.event=='MOVED' and utc(h.at)>=utc(stays[out.stay_id].received_at) and utc(h.at)<=utc(out.at)]
   if places:loc=places[-1]
  delivered.append({'vin':v['vin'],'model':v['model'],'warehouse':bucket_name(loc),'value':value,'value_excluded':excluded,'price_id':rec.id if rec else None,'outbound_id':out.id})
 totals={k:sum(b[k] for b in buckets.values()) for k in ('unsold','waiting','unknown','count','value','value_excluded','missing','missing_excluded')}
 moves=sum(bool(h.event=='MOVED' and day(h.at)==d and h.data.get('from',{} ) and h.data.get('to',{}) and h.data['from'].get('warehouse_id')!=h.data['to'].get('warehouse_id')) for h in data['History'])
 return {'day':d,'live':current,'warehouses':list(buckets.values()),'totals':totals,'stock':details,'unlinked_count':len(unlinked),'unlinked':unlinked,'delivered':delivered,'delivered_count':len(delivered),'delivered_value':sum(r['value'] or 0 for r in delivered),'delivered_missing':sum(r['value'] is None for r in delivered),'received':len({(r.data['values'].get('vin','').strip().upper(),r.data['values'].get('received_date')) for r in valued.values() if r.data['values'].get('received_date')==d and not r.data.get('pending') and not r.data.get('deleted')} | {(v.vin,d) for st in data['Stay'] if day(st.received_at)==d and st.reason!='VOID' and (v:=vehicles.get(st.vehicle_id))}),'warehouse_moves':int(moves),'warnings':stock['warnings'],'value_label':'입력 가액 (VAT 포함)'}
