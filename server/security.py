import hashlib,hmac,secrets
from datetime import timedelta,timezone
from .models import Session,now,User
from fastapi import HTTPException

def hash_password(password):
    if len(password)<10: raise ValueError('비밀번호는 10자 이상이어야 합니다.')
    salt=secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),600000).hex()
    return f'{salt}${digest}'
def verify(password,stored):
    salt,digest=stored.split('$')
    return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),600000).hex(),digest)
def issue(s,user):
    token=secrets.token_urlsafe(40)
    s.add(Session(id=hashlib.sha256(token.encode()).hexdigest(),user_id=user.id,expires=now()+timedelta(hours=12)))
    return token
def authorize(s,token):
    sess=s.get(Session,hashlib.sha256(token.encode()).hexdigest()) if token else None
    if not sess or sess.expires.replace(tzinfo=timezone.utc)<now(): raise HTTPException(401,'로그인이 필요합니다.')
    user=s.get(User,sess.user_id)
    if not user or not user.active: raise HTTPException(401,'비활성 계정입니다.')
    return user
