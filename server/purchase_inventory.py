"""Read-only sheet receipt overlay. Never edits original stays or dispatches."""
from types import SimpleNamespace
from datetime import datetime,time,date,timezone
from .domain import KST,day

def active_records(records):
 latest={}
 for r in records:
  if r.record_id not in latest or latest[r.record_id].revision<r.revision:latest[r.record_id]=r
 return [r for r in latest.values() if not r.data.get('deleted')]

def overlay(data):
 stays={s.id:SimpleNamespace(id=s.id,vehicle_id=s.vehicle_id,received_at=s.received_at,closed_at=s.closed_at,reason=s.reason) for s in data['Stay']}
 vehicles={v.vin:v for v in data['Vehicle']};sheets={};warnings=[]
 for record in active_records(data.get('PurchaseRecord',[])):
  values=record.data['values']
  if record.data.get('pending') or not values.get('received_date'):continue
  start=datetime.combine(date.fromisoformat(values['received_date']),time.min,KST).astimezone(timezone.utc)
  vin=values['vin'].strip().upper();vehicle=vehicles.get(vin)
  candidates=[s for s in data['Stay'] if vehicle and s.vehicle_id==vehicle.id]
  exact=[s for s in candidates if day(s.received_at)==values['received_date']]
  chosen=next((s for s in candidates if s.id==record.stay_id),None)
  if chosen is None:chosen=exact[0] if len(exact)==1 else candidates[0] if len(candidates)==1 else None
  if vehicle and candidates and chosen is None:
   warnings.append('시트 입고 회차 확인 필요: '+vin);continue
  if chosen:
   key=chosen.id
   if key in sheets:warnings.append('동일 회차에 시트 자료가 중복 연결됨: '+vin);continue
   stays[key].received_at=start
   if chosen.closed_at and day(chosen.closed_at)<values['received_date']:warnings.append('시트 입고일이 실제 출고/종료일 이후: '+vin)
  else:
   key='purchase:'+record.record_id
   stays[key]=SimpleNamespace(id=key,vehicle_id=vehicle.id if vehicle else 'sheet-vin:'+vin,received_at=start,closed_at=None,reason='RECEIPT')
  sheets[key]=record
 return stays,sheets,warnings

def inventory_row(record,stay,masters,vehicles,outs):
 values=record.data['values'];v=vehicles.get(stay.vehicle_id);m=masters.get(record.data.get('model_id'));brand=masters.get((m.detail or {}).get('brand_id')) if m else None
 outbound=outs.get(stay.id);kind=(outbound.snapshot.get('vehicle',{}).get('kind') if outbound else None) or (v.kind if v else record.data.get('inventory_kind','UNKNOWN'))
 return {'vehicle_id':stay.vehicle_id,'stay_id':stay.id,'vin':values['vin'].strip().upper(),'reference':'시트-'+record.record_id[:8],
  'model_id':m.id if m else 'sheet-model:'+values['model'],'model':m.name if m else values['model'],
  'brand_id':brand.id if brand else 'sheet-unmapped','brand':brand.name if brand else '브랜드 미연결','kind':kind,
  'color':values['color'],'source_model':values['model'],'source_received_date':values['received_date'],
  'classification_quality':'SHEET','purchase_record_id':record.record_id,'purchase_revision':record.revision,
  'default_value':None,'individual_value':values['vat_included'],'has_individual_value':True,'value':values['vat_included'],
  'value_excluded':values['vat_excluded'],'value_source':'SHEET','price_id':record.id,'operational_registered':v is not None}
