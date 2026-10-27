"""Client-side Windows OCR connection. Never starts a process on the server."""
import os
from pathlib import Path
from .domain import need
URI='scooterwarehouse-ocr://open'

def launch(request,user):
 need(user.active,'비활성 계정입니다.',401)
 return {'ok':True,'uri':URI,'mode':'client'}

def installer():
 filename=os.getenv('WAREHOUSE_OCR_CONNECTOR_ZIP')
 path=Path(filename) if filename else Path(os.getenv('LOCALAPPDATA',''))/'ScooterWarehouse'/'Tools'/'ocr-connector.zip'
 need(path.is_file(),'OCR 연결 설치 파일이 준비되지 않았습니다. 관리자에게 문의하세요.',503)
 return path
