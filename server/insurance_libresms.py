"""Optional private-network LibreSMS transport. No cloud fallback or inbox access."""
import base64,json,ipaddress
from urllib.parse import urlsplit
import httpx
from .models import Setting
from . import customer_privacy as privacy
from .insurance_documents import InsuranceDocumentError

KEY='insurance_libresms'
NETWORKS=[ipaddress.ip_network(x) for x in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','100.64.0.0/10')]
DEFAULT={'enabled':False,'url':'','sender':'','name':'회사 전용폰','interval':5}

def validate_url(value):
    try:
        parts=urlsplit(str(value).strip());address=ipaddress.ip_address(parts.hostname or '')
        if parts.scheme not in ('http','https') or not any(address in net for net in NETWORKS) or parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('','/') or not parts.port or not 1024<=parts.port<=65535:raise ValueError()
        return f'{parts.scheme}://{address}:{parts.port}'
    except ValueError:raise InsuranceDocumentError('사내망 또는 Tailscale의 휴대폰 IPv4 주소와 포트를 입력하세요. 예: http://100.64.1.2:8686') from None

def device_key(device_id='phone1'):
    if device_id not in ('phone1','phone2'):raise InsuranceDocumentError('업무용 휴대폰을 선택하세요.')
    return KEY if device_id=='phone1' else KEY+'_phone2'

def config(db,device_id='phone1'):
    with db.read() as s:
        row=s.get(Setting,device_key(device_id))
        value={**DEFAULT,**json.loads(privacy.decrypt(row.value['encrypted']))} if row else dict(DEFAULT)
        hold=s.get(Setting,'libresms_restore_hold')
        if hold and hold.value.get('held'):value['enabled']=False;value['restore_hold']=True
        value['device_id']=device_id
        return value

def configure(db,uid,p):
    import re
    device_id=p.get('device_id','phone1');key=device_key(device_id)
    enabled=p.get('enabled',False)
    if not isinstance(enabled,bool):raise InsuranceDocumentError('사용 여부를 확인하세요.')
    url=validate_url(p.get('url','')) if p.get('url') else ''
    sender=re.sub(r'\D','',str(p.get('sender','')));name=str(p.get('name','회사 전용폰')).strip()
    try:interval=int(p.get('interval',5))
    except (ValueError,TypeError):raise InsuranceDocumentError('발송 간격은 2~60초로 입력하세요.') from None
    if not 2<=interval<=60 or not name or len(name)>80 or (sender and not re.fullmatch(r'0\d{8,10}',sender)):raise InsuranceDocumentError('장치명·발신번호·발송 간격을 확인하세요.')
    if enabled and (not url or not sender or p.get('private_network_confirmed') is not True):raise InsuranceDocumentError('전용폰 주소·발신번호와 전용망 접근 제한 확인이 필요합니다.')
    value={'device_id':device_id,'enabled':enabled,'url':url,'sender':sender,'name':name,'interval':interval}
    with db.transaction() as s:
        row=s.get(Setting,device_key(device_id));stored={'encrypted':privacy.encrypt(json.dumps(value,ensure_ascii=False))}
        if row:row.value=stored
        else:s.add(Setting(key=key,value=stored))
        hold=s.get(Setting,'libresms_restore_hold')
        if hold:hold.value={'held':False}
        privacy.audit(s,type('Actor',(),{'id':uid})(),'LIBRESMS_CONFIG_CHANGED')
    return value

def request(url,path,payload=None):
    # Literal private IPv4 only; redirects/proxies disabled. Never log request payload or upstream text.
    url=validate_url(url)
    with httpx.Client(trust_env=False,follow_redirects=False,timeout=httpx.Timeout(150 if payload else 5,connect=5)) as client:
        with client.stream('POST' if payload else 'GET',url+path,json=payload) as response:
            body=bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body)>65536:raise ValueError('Oversized response')
            return response.status_code,json.loads(body)

def health(cfg):
    if not cfg.get('url'):return {'online':False,'message':'휴대폰 주소를 설정하세요.','mms_verified':False}
    try:
        code,value=request(cfg['url'],'/health');online=code==200 and (value.get('success') is True or value.get('Success') is True)
    except Exception:online=False
    return {'online':online,'message':'휴대폰 API 연결 확인 · MMS 수신 검증은 별도입니다.' if online else '휴대폰 연결을 확인할 수 없습니다. 대기 중인 요청은 보존됩니다.','mms_verified':False}

def send(cfg,phone,message,image):
    result={'state':'unknown','provider':'libresms','delivery_confirmed':False,'group_id':'','title':'전용폰 발송 결과 확인 필요','action':'전용폰과 수신자에게 확인하기 전 재발송하지 마세요.','technical':{'code':'','detail':'LibreSMS 결과 미확인'}}
    try:
        code,value=request(cfg['url'],'/sendmms',{'to':phone,'message':message,'image':base64.b64encode(image).decode('ascii')})
        if code==200 and (value.get('success') is True or value.get('Success') is True):
            result.update(state='accepted',title='전용폰 MMS 접수 응답 확인',action='수신자 단말 도착은 확인되지 않았습니다.',technical={'code':'','detail':'LibreSMS success 응답'})
        # A false/error/timeout may follow a carrier submission. Keep unknown, never auto-retry.
    except Exception:pass
    return result
