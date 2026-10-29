"""Encrypted customer identity; explicit grants; no customer names in common snapshots."""
import base64,hashlib,hmac,json,os,unicodedata
from pathlib import Path
from cryptography.fernet import Fernet,InvalidToken
from sqlalchemy import select,tuple_
from datetime import datetime
from fastapi import HTTPException
from .models import User,SecurityOwner,CustomerAccess,Customer,CustomerSearch,OrderCustomer,OutboundCustomer,CustomerAudit,Order,Outbound,VehicleCustomerEvent

def require(ok,message='고객정보 접근 권한이 없습니다.',status=403):
    if not ok:raise HTTPException(status,message)

def owner_id(s):
    row=s.get(SecurityOwner,1)
    if row:return row.user_id
    # Bootstrap is limited to the existing original admin, never any administrator.
    return s.scalar(select(User.id).where(User.username=='admin',User.role=='admin',User.active==True))

def pin_owner(s):
    ident=owner_id(s)
    if ident and not s.get(SecurityOwner,1):s.add(SecurityOwner(id=1,user_id=ident));s.flush()
    return ident

def permissions(s,u):
    primary=u.active and u.role=='admin' and u.id==owner_id(s)
    grant=s.get(CustomerAccess,u.id)
    return {'security_owner':bool(primary),'customer_access':bool(primary or (u.active and u.role=='admin' and grant and grant.allowed))}

def allowed(s,u):require(permissions(s,u)['customer_access'])

def audit(s,u,event,target=''):s.add(CustomerAudit(actor_id=u.id,event=event,target_id=target))

def key_path():
    value=os.getenv('WAREHOUSE_CUSTOMER_KEY_FILE')
    return Path(value) if value else Path(os.getenv('LOCALAPPDATA',str(Path.home())))/'ScooterWarehouse'/'keys'/'customer.key'

def key():
    try:
        value=key_path().read_bytes().strip();Fernet(value);return value
    except (OSError,ValueError):raise HTTPException(503,'고객정보 암호화 키 설정이 필요합니다.') from None

def token(value):return hmac.new(base64.urlsafe_b64decode(key()),b'customer-search-v1\0'+value.encode('utf8'),hashlib.sha256).hexdigest()
def normalize(value):return unicodedata.normalize('NFKC',value).strip().casefold()
def encrypt(value):return Fernet(key()).encrypt(value.encode('utf8')).decode('ascii')
def decrypt(value):
    try:return Fernet(key()).decrypt(value.encode('ascii')).decode('utf8')
    except (InvalidToken,ValueError):raise HTTPException(503,'고객정보 복호화 키를 확인하세요.') from None
def validate_key(s):
    key()
    probe=s.scalar(select(Customer.encrypted_name).limit(1))
    if probe:decrypt(probe)
def dto(row):return {'id':row.id,'kind':row.kind,'name':decrypt(row.encrypted_name)}

def create(s,u,p):
    allowed(s,u);validate_key(s);pin_owner(s)
    name=str(p.get('name','')).strip();kind=p.get('kind');request=str(p.get('request_id',''))
    require(1<=len(name)<=120 and kind in ('COMPANY','PERSON') and 16<=len(request)<=80,'업체명 또는 주문자명을 입력하세요.',422)
    digest=token(json.dumps([name,kind],ensure_ascii=False))
    old=s.scalar(select(Customer).where(Customer.request_id==request))
    if old:
        require(old.created_by==u.id and old.request_digest==digest,'다른 요청에 사용된 ID입니다.',409)
        return {'id':old.id}
    if p.get('prevent_duplicate'):
        candidates=s.scalars(select(Customer).join(CustomerSearch).where(CustomerSearch.token==token(normalize(name)),Customer.kind==kind))
        require(not any(normalize(decrypt(c.encrypted_name))==normalize(name) for c in candidates),'같은 이름의 고객이 있습니다. 기존 고객 목록에서 선택하세요.',409)
    row=Customer(kind=kind,encrypted_name=encrypt(name),created_by=u.id,request_id=request,request_digest=digest)
    s.add(row);s.flush()
    norm=normalize(name)
    for length in range(1,len(norm)+1):s.add(CustomerSearch(token=token(norm[:length]),customer_id=row.id))
    audit(s,u,'CUSTOMER_CREATED',row.id)
    return {'id':row.id}

def search(s,u,p):
    allowed(s,u);validate_key(s);query=normalize(str(p.get('query','')))
    require(len(query)<=120,'검색어가 너무 깁니다.',422)
    stmt=select(Customer)
    if query:stmt=stmt.join(CustomerSearch).where(CustomerSearch.token==token(query))
    after=str(p.get('after',''))
    if after:stmt=stmt.where(Customer.id>after)
    rows=list(s.scalars(stmt.order_by(Customer.id).limit(21)))
    audit(s,u,'CUSTOMER_SEARCH')
    return {'items':[dto(row) for row in rows[:20]],'next':rows[19].id if len(rows)>20 else None}

def attach(s,u,order_id,customer_id):
    allowed(s,u)
    row=s.get(Customer,str(customer_id or ''))
    require(row is not None,'새 주문은 업체 또는 주문자를 선택·등록해야 합니다.',422)
    # Re-encrypt a frozen name so later profile changes cannot rewrite order history.
    s.add(OrderCustomer(order_id=order_id,customer_id=row.id,encrypted_name=encrypt(decrypt(row.encrypted_name)),kind=row.kind))
    audit(s,u,'CUSTOMER_ORDER_LINKED',order_id)

def dispatch(s,u,order_id,outbound_id):
    row=s.get(OrderCustomer,order_id)
    if row:
        out=s.get(Outbound,outbound_id)
        s.add(OutboundCustomer(outbound_id=outbound_id,order_id=order_id,customer_id=row.customer_id,encrypted_name=row.encrypted_name,kind=row.kind,at=out.at))
        s.add(VehicleCustomerEvent(vehicle_id=out.vehicle_id,customer_id=row.customer_id,outbound_id=outbound_id,effective_day=out.day,actor_id=u.id,kind='DELIVERY'))

def order_name(s,u,order_id):
    allowed(s,u);row=s.get(OrderCustomer,order_id);audit(s,u,'CUSTOMER_ORDER_VIEWED',order_id)
    return {'id':row.customer_id,'kind':row.kind,'name':decrypt(row.encrypted_name)} if row else None

def history(s,u,customer_id,after=''):
    allowed(s,u);customer=s.get(Customer,customer_id);require(customer is not None,'고객 기록이 없습니다.',404)
    stmt=select(OutboundCustomer,Outbound,Order).join(Outbound,Outbound.id==OutboundCustomer.outbound_id).join(Order,Order.id==OutboundCustomer.order_id).where(OutboundCustomer.customer_id==customer_id)
    if after:
        try:stamp,ident=after.split('~',1);cursor=datetime.fromisoformat(stamp)
        except ValueError:raise HTTPException(422,'조회 위치를 확인하세요.') from None
        stmt=stmt.where(tuple_(OutboundCustomer.at,OutboundCustomer.outbound_id)<tuple_(cursor,ident))
    rows=s.execute(stmt.order_by(OutboundCustomer.at.desc(),OutboundCustomer.outbound_id.desc()).limit(51)).all();audit(s,u,'CUSTOMER_HISTORY_VIEWED',customer_id)
    return {'customer':dto(customer),'items':[{'id':link.outbound_id,'order_id':order.id,'number':order.number,'day':out.day,'vehicle_id':out.vehicle_id,'vin':out.snapshot['vehicle']['vin'],'model':out.snapshot['vehicle']['model'],'name_at_dispatch':decrypt(link.encrypted_name)} for link,out,order in rows[:50]],'next':rows[49][0].at.isoformat()+'~'+rows[49][0].outbound_id if len(rows)>50 else None}

def grant(s,u,target,enabled):
    require(permissions(s,u)['security_owner'],'최초 관리자만 고객정보 권한을 부여할 수 있습니다.')
    require(target.role=='admin' and target.active,'활성 관리자에게만 권한을 부여할 수 있습니다.',422)
    require(target.id!=u.id,'최초 관리자 권한은 변경할 수 없습니다.',422)
    pin_owner(s);row=s.get(CustomerAccess,target.id)
    if not row:row=CustomerAccess(user_id=target.id,granted_by=u.id);s.add(row)
    row.allowed=enabled;row.granted_by=u.id;audit(s,u,'CUSTOMER_ACCESS_GRANTED' if enabled else 'CUSTOMER_ACCESS_REVOKED',target.id)


def order_names(s,u,ids):
    allowed(s,u)
    require(isinstance(ids,list) and len(ids)<=200 and all(isinstance(x,str) and 0<len(x)<=80 for x in ids),'주문 목록을 확인하세요.',422)
    ids=list(dict.fromkeys(ids));result={x:None for x in ids}
    for row in s.scalars(select(OrderCustomer).where(OrderCustomer.order_id.in_(ids))):
        result[row.order_id]={'name':decrypt(row.encrypted_name),'kind':row.kind}
    if ids:audit(s,u,'CUSTOMER_ORDERS_VIEWED',','.join(ids))
    return result
