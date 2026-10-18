"""Optional OCR on the warehouse PC only; never calls an external service."""
import os,shutil,subprocess,tempfile
from pathlib import Path
from .used_stock import decode_image
from .domain import need

def recognize(encoded):
 raw,mime=decode_image(encoded)
 candidates=[os.getenv('TESSERACT_CMD',''),shutil.which('tesseract') or '',r'C:\Program Files\Tesseract-OCR\tesseract.exe']
 engine=next((p for p in candidates if p and Path(p).is_file()),None)
 need(engine is not None,'PC OCR 엔진이 설치되어 있지 않습니다. 사진은 저장할 수 있으며 VIN은 직접 입력하세요.',503)
 with tempfile.TemporaryDirectory(prefix='warehouse-vin-') as folder:
  source=Path(folder)/'vin.jpg';source.write_bytes(raw);texts=[]
  for mode in ['6','11']:
   try:r=subprocess.run([engine,str(source),'stdout','-l','eng','--psm',mode],capture_output=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
   except subprocess.TimeoutExpired:need(False,'VIN 분석 시간이 초과되었습니다. 다시 촬영하거나 직접 입력하세요.',503)
   need(r.returncode==0,'PC OCR 엔진의 eng 언어 파일을 확인하세요.',503);texts.append(r.stdout.decode('utf-8',errors='replace'))
 return {'raw':'\n'.join(texts)}
