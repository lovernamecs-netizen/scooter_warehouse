import base64,io,json,uuid
import pytest
from sqlalchemy import select
from PIL import Image
from test_workflow import env
from server import insurance_coolsms as sms,insurance_settings as settings
from server.insurance_api import InsuranceSend
from server.insurance_documents import extract_page_plate,convert_pdf,_encode_jpeg

@pytest.fixture
def configured(env,monkeypatch,tmp_path):
 monkeypatch.setenv('INSURANCE_CONFIG_DIR',str(tmp_path/'settings'))
 monkeypatch.setattr(settings,'credentials',lambda:('synthetic','synthetic','01011112222'))
 monkeypatch.setattr(sms,'credentials',settings.credentials)
 calls=[]
 def provider(*args):calls.append(1);return {'state':'accepted','group_id':'synthetic'}
 monkeypatch.setattr(sms,'_send_with_provider',provider)
 stream=io.BytesIO();Image.new('RGB',(100,100),'white').save(stream,'JPEG')
 data={'request_id':str(uuid.uuid4()),'plate':'123가4567','phone':'01012345678','text':'{차량번호} 합성 안내','jpeg_base64':base64.b64encode(stream.getvalue()).decode()}
 return env,data,calls

def test_durable_dedup_permissions_and_encrypted_audit(configured):
 e,data,calls=configured;db,c,h,*_=e
 worker=c.post('/api/login',json={'username':'worker','password':'test-password-123'}).json()['token']
 assert c.post('/api/insurance/mms/send',headers={'Authorization':'Bearer '+worker},json=data).status_code==403
 assert c.post('/api/insurance/mms/send',headers=h,json=data).json()['state']=='accepted'
 sms._idempotency.clear() # Simulate loss of process cache on restart.
 repeated=c.post('/api/insurance/mms/send',headers=h,json={**data,'request_id':str(uuid.uuid4())}).json()
 assert repeated['repeated_request'] and len(calls)==1
 assert c.post('/api/insurance/mms/send',headers=h,json={**data,'phone':'01099998888'}).status_code==409
 with db.read() as s:
  row=s.scalar(select(InsuranceSend));assert data['phone'] not in row.encrypted_detail and data['plate'] not in row.encrypted_detail
 history=c.get('/api/insurance/mms/history',headers=h).json();assert history[0]['plate']==data['plate'] and history[0]['actor_id']

def test_unknown_does_not_resend_after_restart(configured,monkeypatch):
 e,data,calls=configured;db,c,h,*_=e
 def timeout(*a):calls.append(1);raise TimeoutError('synthetic timeout')
 monkeypatch.setattr(sms,'_send_with_provider',timeout)
 assert c.post('/api/insurance/mms/send',headers=h,json=data).json()['state']=='unknown'
 sms._idempotency.clear()
 assert c.post('/api/insurance/mms/send',headers=h,json={**data,'request_id':str(uuid.uuid4())}).json()['state']=='unknown'
 assert len(calls)==1

def test_region_before_full_text_and_ambiguous_confirmation():
 import fitz
 with fitz.open() as doc:
  page=doc.new_page(width=600,height=850)
  page.insert_text((20,210),'차 량 번 호 : 123가4567',fontname='korea')
  page.insert_text((20,600),'참고 차량번호: 234나5678',fontname='korea')
  result=extract_page_plate(page)
  assert result['plate']=='123가4567' and result['review_required']
  assert '234나5678' in result['candidates']
  converted=convert_pdf(doc.tobytes())['pages'][0]
  assert converted['plate']=='123가4567' and converted['size_bytes']<=199000

def test_quality_search_and_strict_budget():
 import random
 from PIL import ImageDraw
 image=Image.new('RGB',(1000,1400),'white');draw=ImageDraw.Draw(image)
 for y in range(30,1350,20):draw.text((20,y),'Insurance notice 123-ABC fine text 0123456789 '*4,fill='black')
 raw,within,w,h=_encode_jpeg(image,199000)
 assert within and len(raw)<=199000 and w>=800 and h>=1120
 # Dense noise should be explicitly refused, never marked valid above the cap.
 rng=random.Random(73);noise=Image.frombytes('RGB',(1500,1440),rng.randbytes(1500*1440*3))
 raw,within,w,h=_encode_jpeg(noise,199000)
 assert not within and len(raw)>199000

def test_pdf_oversized_geometry_rejected():
 import fitz
 with fitz.open() as doc:
  doc.new_page(width=10000,height=10000)
  with pytest.raises(ValueError,match='너무 큽니다'):convert_pdf(doc.tobytes())

def test_actual_api_conversion_and_contacts(configured):
 import fitz
 e,_,_=configured;db,c,h,*_=e
 with fitz.open() as doc:
  page=doc.new_page(width=600,height=850);page.insert_text((20,210),'차량번호 : 123가4567',fontname='korea')
  result=c.post('/api/insurance/convert',headers=h,files={'file':('synthetic.pdf',doc.tobytes(),'application/pdf')})
 assert result.status_code==200 and result.json()['pages'][0]['plate']=='123가4567'
 result=c.post('/api/insurance/contacts',headers=h,files={'file':('synthetic.csv','차량번호,연락처\n123가4567,01012345678'.encode(),'text/csv')})
 assert result.status_code==200 and result.json()['count']==1

def test_send_history_survives_verified_backup(configured,tmp_path):
 from server.photo_backup import backup,restore
 import sqlite3
 from contextlib import closing
 e,data,_=configured;db,c,h,*_=e
 assert c.post('/api/insurance/mms/send',headers=h,json=data).status_code==200
 saved=backup(db);destination=tmp_path/'restored'
 restore(saved['file'],destination,True)
 with closing(sqlite3.connect(destination/'warehouse.db')) as con:
  rows=con.execute('SELECT id,state,encrypted_detail FROM insurance_sends').fetchall()
 assert len(rows)==1 and rows[0][0]==data['request_id'] and rows[0][1]=='accepted'
 assert data['phone'] not in rows[0][2]

def test_same_document_concurrent_new_ids_only_calls_provider_once(configured):
 from concurrent.futures import ThreadPoolExecutor
 e,data,calls=configured;db,c,h,*_=e
 def submit(_):return c.post('/api/insurance/mms/send',headers=h,json={**data,'request_id':str(uuid.uuid4())})
 with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(submit,range(2)))
 assert all(r.status_code==200 for r in responses) and len(calls)==1

def test_solapi_installed_sdk_contract_without_network(monkeypatch,tmp_path):
 import solapi
 from types import SimpleNamespace
 seen=[]
 class Provider:
  def __init__(self,**kwargs):pass
  def upload_file(self,file_path,upload_type):assert upload_type.value=='MMS';return SimpleNamespace(file_id='synthetic-file')
  def send(self,message):
   seen.append(message);return SimpleNamespace(group_info=SimpleNamespace(group_id='synthetic-group',count=SimpleNamespace(registered_success=1,registered_failed=0)))
 monkeypatch.setattr(solapi,'SolapiMessageService',Provider)
 image=tmp_path/'synthetic.jpg';image.write_bytes(b'fake-for-contract')
 outcome=sms._send_with_provider(image,'fake','fake','01011112222','01012345678','합성 안내')
 assert outcome['state']=='accepted' and seen[0].image_id=='synthetic-file'
