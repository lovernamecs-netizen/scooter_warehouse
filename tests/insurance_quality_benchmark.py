"""Compare the reviewed app.txt compressor on synthetic pages only.

Usage: python tests/insurance_quality_benchmark.py C:/Users/CCS/Downloads/app.txt
Only the explicitly reviewed compression function is extracted; the app is not run.
"""
import ast,base64,io,json,math,os,sys,tempfile
from pathlib import Path
import pymupdf as fitz
from PIL import Image,ImageChops,ImageStat
from server.insurance_documents import _encode_jpeg
source=Path(sys.argv[1]).read_text(encoding='utf-8-sig')
node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='save_jpg_under_199kb')
scope={'Image':Image,'io':io,'os':os};exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'reviewed-compressor','exec'),scope)
out=Path(__file__).resolve().parents[2]/'purchase-sheet-results';results=[]
with tempfile.TemporaryDirectory(prefix='insurance-quality-') as temp:
 for lines in (15,35,60):
  with fitz.open() as doc:
   page=doc.new_page(width=600,height=850)
   page.insert_text((35,45),'보험 고지문 · 합성 품질 비교',fontname='korea',fontsize=17,color=(0,.35,.35))
   for n in range(lines):page.insert_text((35,80+n*11),'보험 차량 고지사항 123가4567 / 계약사항 확인 0123456789',fontname='korea',fontsize=8)
   pix=page.get_pixmap(matrix=fitz.Matrix(2,2),colorspace=fitz.csRGB,alpha=False)
   reference=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
   old=Path(temp)/'old.jpg';scope['save_jpg_under_199kb'](pix,str(old),199000)
   raw,within,w,h=_encode_jpeg(reference,199000);assert within and len(raw)<=199000
   result={'lines':lines,'limit_bytes':199000}
   for label,blob in [('original',old.read_bytes()),('improved',raw)]:
    im=Image.open(io.BytesIO(blob)).convert('RGB');size=im.size
    difference=ImageChops.difference(reference,im.resize(reference.size,Image.Resampling.LANCZOS));mse=sum(ImageStat.Stat(difference).rms[i]**2 for i in range(3))/3
    result[label]={'bytes':len(blob),'width':size[0],'height':size[1],'synthetic_rgb_psnr_db':round(10*math.log10(255**2/mse),2)}
    if lines==35:im.save(out/f'insurance-quality-{label}.png')
   results.append(result)
(out/'insurance-quality.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps(results))
