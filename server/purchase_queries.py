"""Bounded purchase reads: database filters/counts, page data, lazy history."""
import json,re
from sqlalchemy import select,func,case
from .models import PurchaseRecord,Master
from .purchase_sheet import current_query,ALL_FIELDS,ALL_HEADERS
from .domain import need,iso

def dto(r):
 return {'id':r.record_id,'revision':r.revision,'data':r.data,'vehicle_id':r.vehicle_id,'stay_id':r.stay_id,'actor':r.actor,'at':iso(r.at),'identifiers':r.data.get('identifiers',{})}

def page(s,u,month,selected='',page=0,filters='{}',deleted=False):
 need(u.role in ('admin','worker'),'접근 권한이 없습니다.',403)
 need(bool(re.fullmatch(r'\d{4}-\d{2}',month)) and 0<=page<=100000,'조회 범위 오류')
 try:conditions=json.loads(filters)
 except Exception:need(False,'검색 조건 오류')
 need(isinstance(conditions,dict) and set(conditions)<=set(ALL_FIELDS),'검색 항목 오류')
 q=current_query()
 if not deleted:q=q.where(PurchaseRecord.data['deleted'].as_boolean().is_not(True))
 for key,item in conditions.items():
  need(isinstance(item,dict) and item.get('mode') in ('empty','filled','equal','contains'),'검색 조건 오류')
  value=func.lower(func.trim(func.coalesce(PurchaseRecord.data['source'][key].as_string(),'')))
  term=str(item.get('text','')).strip().lower();need(len(term)<=10000,'검색어가 너무 깁니다.')
  q=q.where(value=='' if item['mode']=='empty' else value!='' if item['mode']=='filled' else value==term if item['mode']=='equal' else value.contains(term,autoescape=True))
 raw_total=s.scalar(select(func.count()).select_from(q.subquery()))
 vin=func.upper(func.trim(func.coalesce(PurchaseRecord.data['source']['vin'].as_string(),'')))
 receipt=func.coalesce(PurchaseRecord.data['values']['received_date'].as_string(),'')
 identity=PurchaseRecord.record_id if deleted else case((func.length(vin)==17,vin+'|'+receipt),else_=PurchaseRecord.record_id)
 grouped=q.with_only_columns(PurchaseRecord.id.label('id'),func.row_number().over(partition_by=identity,order_by=PurchaseRecord.record_id).label('rn'),func.count().over(partition_by=identity).label('duplicates')).subquery()
 q=select(PurchaseRecord).join(grouped,PurchaseRecord.id==grouped.c.id).where(grouped.c.rn==1)
 total=s.scalar(select(func.count()).select_from(q.subquery()))
 date=PurchaseRecord.data['values']['received_date'].as_string()
 calendar=q.where(date.startswith(month+'-')).with_only_columns(date.label('day'),func.sum(case((func.length(vin)==17,1),else_=0)).label('count'),func.sum(case((func.length(vin)!=17,1),else_=0)).label('unknown')).group_by(date)
 days=s.execute(calendar).all();counts={d:n for d,n,_ in days};unknown={d:n for d,_,n in days}
 if selected=='pending':q=q.where(PurchaseRecord.data['pending'].as_boolean()==True)
 elif selected=='month':q=q.where(date.startswith(month+'-'))
 elif selected:
  need(bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}',selected)),'조회 날짜 오류');q=q.where(date==selected)
 count=s.scalar(select(func.count()).select_from(q.subquery()))
 page=min(page,max(0,(count-1)//50))
 result_rows=s.execute(q.add_columns(grouped.c.duplicates).order_by(PurchaseRecord.record_id).offset(page*50).limit(50)).all()
 rows=[r for r,_ in result_rows];duplicates={r.id:n for r,n in result_rows}
 return {'rows':[{**dto(r),'duplicate_count':duplicates.get(r.id,1)} for r in rows],'history':[],'total':total,'raw_total':raw_total,'count':count,'page':page,'days':counts,'day_unidentified':unknown,'fields':ALL_FIELDS,'headers':ALL_HEADERS,'masters':[{'id':m.id,'kind':m.kind,'name':m.name} for m in s.scalars(select(Master).where(Master.active==True,Master.kind.in_(['model','color'])))]}

def history(s,u,ident,page=0):
 need(u.role in ('admin','worker'),'접근 권한이 없습니다.',403);need(0<=page<=100000,'페이지 오류')
 q=select(PurchaseRecord).where(PurchaseRecord.record_id==ident)
 count=s.scalar(select(func.count()).select_from(q.subquery()))
 return {'count':count,'rows':[dto(r) for r in s.scalars(q.order_by(PurchaseRecord.revision.desc()).offset(page*50).limit(50))]}

def sources(s,u):
 need(u.role in ('admin','worker'),'접근 권한이 없습니다.',403)
 q=current_query().with_only_columns(PurchaseRecord.data['import_source'].label('source')).distinct()
 result={}
 for info in s.scalars(q):
  if not info:continue
  key=info.get('namespace') or 'legacy:'+info['sheet']
  result.setdefault(key,{'id':key,'label':info.get('label') or ('기존 자료 · '+info['sheet'])})
 return {'sources':list(result.values())}
