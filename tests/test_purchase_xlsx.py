import io,zipfile
from xml.sax.saxutils import escape
from server.purchase_xlsx import parse
from server.purchase_sheet import ALL_HEADERS
from test_workflow import env

def fixture(count=3110,formula=False):
 rows=[['']+ALL_HEADERS]+[['','2026-01-01','합성 공급업체','대표','2026-01-02','지역','PCX125',f'MLHJK05A1P5{i:06d}','블랙','','재고','4342400','3947636','054687311','','','유비스','0253293322'] for i in range(count)]
 body=''
 for n,row in enumerate(rows,1):
  cells=''.join(f'<c r="{chr(65+i)}{n}" t="inlineStr"><is><t>{escape(v)}</t></is></c>' for i,v in enumerate(row))
  if formula and n==2:cells=cells.replace('<c r="L2" t="inlineStr"><is><t>4342400</t></is></c>','<c r="L2"><f>1+1</f></c>')
  body+=f'<row r="{n}" hidden="1">{cells}</row>'
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
  z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
  z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="재고" sheetId="1" r:id="rId1"/></sheets></workbook>')
  z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
  z.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:R{len(rows)}"/><sheetData>{body}</sheetData></worksheet>')
 return b.getvalue()

def test_large_hidden_rows_and_no_mutation():
 data=fixture();before=data;result=parse(data,'original.xlsx');assert result['count']==3110 and data==before
 assert result['rows'][0]['data']['serial_number']=='054687311';assert result['rows'][0]['data']['ubis_number']=='0253293322'
 assert not result['rows'][0]['errors']

def test_formula_and_authenticated_endpoint(env):
 result=parse(fixture(1,True),'x.xlsx');assert not result['rows'][0]['errors'];assert result['rows'][0]['data']['vat_included']=='=1+1'
 assert env[1].post('/api/purchases/xlsx',files={'file':('x.xlsx',fixture(1))}).status_code==401
 response=env[1].post('/api/purchases/xlsx',headers=env[2],files={'file':('x.xlsx',fixture(1))});assert response.status_code==200 and response.json()['count']==1
 assert not env[1].get('/api/purchases',headers=env[2]).json()['rows']


def test_missing_dimension():
 data=fixture(2);out=io.BytesIO()
 with zipfile.ZipFile(io.BytesIO(data)) as source,zipfile.ZipFile(out,'w') as dest:
  for item in source.infolist():
   content=source.read(item.filename)
   if item.filename=='xl/worksheets/sheet1.xml':
    import re
    content=re.sub(rb'<dimension[^>]*/>',b'',content)
   dest.writestr(item,content)
 assert parse(out.getvalue(),'no-dimension.xlsx')['count']==2


def test_all_source_rows_saved_without_identifiers(env):
 from test_purchase_sheet import apply
 data=fixture(252);out=io.BytesIO()
 with zipfile.ZipFile(io.BytesIO(data)) as source,zipfile.ZipFile(out,'w') as dest:
  for item in source.infolist():
   content=source.read(item.filename)
   if item.filename=='xl/worksheets/sheet1.xml':
    import re
    content=re.sub(rb'MLHJK05A1P5[0-9]{6}',b'',content)
    content=content.replace(b'054687311',b'').replace(b'0253293322',b'')
   dest.writestr(item,content)
 parsed=parse(out.getvalue(),'missing-identifiers.xlsx')
 assert len(parsed['rows'])==252 and all(not r['errors'] for r in parsed['rows'])
 def batch(rows):
  return {'rows':[r['data'] for r in rows],'choices':{str(i):{'import_source':{'kind':'XLSX','sha256':parsed['sha256'],'sheet':'재고','row':r['row'],'source_identity':r['source_identity'],'duplicate_identity':r['duplicate_identity']}} for i,r in enumerate(rows)}}
 for offset in (0,250):apply(env,batch(parsed['rows'][offset:offset+250]))
 records=env[1].get('/api/purchases',headers=env[2]).json()['rows']
 assert len(records)==252
 assert all(r['data']['source']==parsed['rows'][0]['data'] for r in records)
 for offset in (0,250):
  result,_=apply(env,batch(parsed['rows'][offset:offset+250]));assert result.json()['saved']==0
 assert len(env[1].get('/api/purchases',headers=env[2]).json()['rows'])==252
