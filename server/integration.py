"""File-only exchange port. No Google API, browser session, or company API access."""
import csv,io,json,hashlib,zipfile
from abc import ABC,abstractmethod
from openpyxl import load_workbook,Workbook
from sqlalchemy import select
from .models import Master,Vehicle,ImportJob
from .domain import vin,need,valid_date,today,qty,manufactured_month
class IntegrationAdapter(ABC):
    @abstractmethod
    def parse(self,data:bytes,filename:str,mapping:dict):pass
class GoogleSheetFileAdapter(IntegrationAdapter):
    fields=['vin','model','color','year','manufactured_month','kind','plate','smart_key','received_date','notes']
    def parse(self,data,filename,mapping):
        need(len(data)<=3_000_000,'가져오기는 3MB 이하 파일만 지원합니다.')
        if filename.lower().endswith('.xlsx'):
            with zipfile.ZipFile(io.BytesIO(data)) as z:need(sum(i.file_size for i in z.infolist())<20_000_000,'압축 해제 파일이 너무 큽니다.')
            wb=load_workbook(io.BytesIO(data),read_only=True,data_only=True)
            ws=wb['VEHICLES'] if 'VEHICLES' in wb.sheetnames else wb.active
            iterator=ws.iter_rows(values_only=True);header=[str(v or '').strip() for v in next(iterator,[])];raw=[]
            for n,line in enumerate(iterator):
                need(n<2000,'한 번에 2,000행까지만 지원합니다.');raw.append(dict(zip(header,[str(v if v is not None else '') for v in line])))
            wb.close()
        else:
            text=data.decode('utf-8-sig');delimiter='\t' if '\t' in text.split('\n')[0] else ','
            raw=list(csv.DictReader(io.StringIO(text),delimiter=delimiter));need(len(raw)<=2000,'한 번에 2,000행까지만 지원합니다.')
        return [{f:str(r.get(mapping.get(f,f),'') or '').strip() for f in self.fields} for r in raw if any(r.values())]
    def preview(self,s,u,data,filename,mapping):
        digest=hashlib.sha256(data+json.dumps(mapping,sort_keys=True).encode()).hexdigest();old=s.scalar(select(ImportJob).where(ImportJob.digest==digest))
        if old:
            need(old.actor==u.username or u.role=='admin','이미 다른 사용자가 검수한 파일입니다.',409)
            return old
        parsed=self.parse(data,filename,mapping);out=[];seen=set()
        for n,r in enumerate(parsed,2):
            errors=[];p=dict(r)
            if r['vin']:
                try:p['vin']=vin(r['vin'])
                except Exception:errors.append('VIN 17자리 형식 확인')
                if r['vin'].upper() in seen:errors.append('파일 내 중복 VIN')
                seen.add(r['vin'].upper())
                if s.scalar(select(Vehicle).where(Vehicle.vin==r['vin'].upper())):errors.append('이미 등록된 VIN — 신규 입고 가져오기는 기존 데이터를 덮어쓰지 않습니다.')
            for kind in ['model','color']:
                m=s.scalar(select(Master).where(Master.kind==kind,Master.name==r[kind],Master.active==True))
                if not m:errors.append(f'{kind} 마스터 미등록: {r[kind]}')
                else:p[kind+'_id']=m.id
            try:p['year']=int(r['year']);qty(p['year'],1900,2100)
            except Exception:errors.append('연식 오류')
            try:p['manufactured_month']=manufactured_month(r.get('manufactured_month'))
            except Exception:errors.append('제조년월 오류 · YYYY-MM 형식과 미래 날짜 여부 확인')
            p['kind']=r['kind'] or 'NEW'
            if p['kind'] not in ['NEW','USED']:errors.append('kind는 NEW 또는 USED')
            p['received_date']=r['received_date'] or today()
            try:valid_date(p['received_date']);need(p['received_date']<=today(),'미래일')
            except Exception:errors.append('입고일 오류')
            out.append({'row':n,'data':p,'error':'; '.join(errors)})
        job=ImportJob(digest=digest,actor=u.username,rows=out);s.add(job);s.flush();return job

def workbook(tables):
    wb=Workbook();wb.remove(wb.active)
    for name,data in tables.items():
        ws=wb.create_sheet(name[:31]);headers=list(dict.fromkeys(k for r in data for k in r)) or ['empty']
        ws.append(headers)
        for row in data:
            values=[]
            for h in headers:
                v=row.get(h,'')
                if isinstance(v,(dict,list)):v=json.dumps(v,ensure_ascii=False)
                values.append(v)
            ws.append(values)
            for cell in ws[ws.max_row]:
                if isinstance(cell.value,str):cell.data_type='s'
        ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
        for col in ws.columns:ws.column_dimensions[col[0].column_letter].width=24
    bio=io.BytesIO();wb.save(bio);return bio.getvalue()
