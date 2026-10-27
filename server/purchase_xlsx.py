"""Read-only original XLSX import. Never saves or modifies the workbook."""
import io,zipfile,re,hashlib,posixpath
from xml.etree import ElementTree as ET
from datetime import datetime,date
from collections import Counter
from openpyxl import load_workbook
from .domain import need
from .purchase_sheet import ALL_FIELDS,HEADERS

def parse(data,filename,sheet="재고"):
 need(filename.lower().endswith('.xlsx'),'XLSX 파일을 선택하세요.')
 need(len(data)<=20_000_000,'파일은 20MB 이하입니다.')
 try:
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   need(len(z.infolist())<10000 and sum(i.file_size for i in z.infolist())<=100_000_000,'압축 해제 크기 제한을 초과했습니다.')
  values=load_workbook(io.BytesIO(data),read_only=True,data_only=True,keep_links=False)
  formulas=load_workbook(io.BytesIO(data),read_only=True,data_only=False,keep_links=False)
 except Exception:
  need(False,'XLSX 파일을 읽을 수 없습니다. 파일 형식과 크기를 확인하세요.')
 try:
  need(sheet in values.sheetnames,'지정한 탭을 찾을 수 없습니다. 탭 이름을 확인하세요.')
  ws=values[sheet];fs=formulas[sheet];need(ws.max_row is None or ws.max_row<=20000,'20,000행까지 지원합니다.')
  rows=[];excluded=[];blank=0
  # Keep underlying numeric/text/formula representation before date-style conversion.
  ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   book=ET.fromstring(z.read('xl/workbook.xml'))
   chosen=next(x for x in book.find('m:sheets',ns) if x.attrib['name']==sheet)
   rid=chosen.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
   relations=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
   target=next(x.attrib['Target'] for x in relations if x.attrib['Id']==rid)
   path=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
   rawcells={}
   for _,cell in ET.iterparse(io.BytesIO(z.read(path)),events=('end',)):
    if cell.tag.endswith('}c'):
     coordinate=cell.attrib.get('r','')
     if re.fullmatch(r'[B-R][0-9]+',coordinate):
      value=cell.find('m:v',ns);formula=cell.find('m:f',ns)
      rawcells[coordinate]={'type':cell.attrib.get('t','n'),'value':value.text if value is not None else None,'formula':formula.text if formula is not None else None,'inline':''.join(cell.itertext()) if cell.attrib.get('t')=='inlineStr' else None}
     cell.clear()
  def display(cell):
   value=cell.value
   if value is None:return ''
   if isinstance(value,(datetime,date)):return value.strftime('%Y-%m-%d')
   if isinstance(value,(int,float)) and not isinstance(value,bool):
    if float(value).is_integer():
     text=str(int(value))
     if re.fullmatch('0+',cell.number_format or ''):text=text.zfill(len(cell.number_format))
     return text
   return str(value)
  vit=ws.iter_rows(min_col=2,max_col=18);fit=fs.iter_rows(min_col=2,max_col=18)
  header=next(vit,[]);next(fit,[])
  need([re.sub(r'\s','',display(c)) for c in header[:12]]==HEADERS,'B:M의 12개 항목 순서가 다릅니다. 원본을 바꾸지 말고 매핑을 확인하세요.')
  for rownum,(cells,fcells) in enumerate(zip(vit,fit),2):
   need(rownum<=20000,'20,000행까지 지원합니다.')
   raw=dict(zip(ALL_FIELDS,map(display,cells)))
   source_cells={key:{**rawcells.get(c.coordinate,{}),'format':c.number_format} for key,c in zip(ALL_FIELDS,fcells) if hasattr(c,'coordinate')}
   for key in ('serial_number','ubis_number','vin'):
    cell=source_cells.get(key,{})
    if cell.get('type')=='n' and cell.get('value') is not None:
     raw[key]=cell['value']
     if re.fullmatch('0+',cell.get('format','')) and raw[key].isdigit():raw[key]=raw[key].zfill(len(cell['format']))
   formula_cells=[c.coordinate for c in fcells if c.data_type=='f']
   missing=[c.coordinate for c,v in zip(fcells,cells) if c.data_type=='f' and v.value is None]
   if not any(raw.values()) and not formula_cells:blank+=1;continue
   # Preserve every populated source row; absent identifiers are not import errors.
   for key,c,v in zip(ALL_FIELDS,fcells,cells):
    if c.data_type=='f' and v.value is None:raw[key]=str(c.value)
   rows.append({'row':rownum,'data':raw,'errors':[],'formula_cells':formula_cells,'source_cells':source_cells})
  occurrences=Counter()
  counts=Counter((r['data']['vin'].strip().upper(),r['data']['received_date']) for r in rows)
  for r in rows:
   content=hashlib.sha256(__import__('json').dumps(r['data'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
   occurrences[content]+=1
   r['source_identity']=content+':'+str(occurrences[content])
   r['duplicate_identity']=counts[(r['data']['vin'].strip().upper(),r['data']['received_date'])]>1
  return {'filename':filename,'sha256':hashlib.sha256(data).hexdigest(),'sheet':sheet,'range':'B:R','rows':rows,'excluded':excluded,'blank_rows':blank,'headers':[display(c) for c in header],'count':len(rows)}
 finally:values.close();formulas.close()
