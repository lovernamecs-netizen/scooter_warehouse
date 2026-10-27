"""OAuth authorization-code + PKCE, per warehouse user, memory-only tokens."""
import os,time,secrets,hashlib,base64,threading,json
from pathlib import Path
from urllib.parse import urlencode,urlparse
import httpx
from fastapi import Request
from fastapi.responses import HTMLResponse
from .domain import need
_lock=threading.Lock();_states={};_tokens={}
SCOPE='https://www.googleapis.com/auth/drive.readonly'

def config():
 keys=('CLIENT_ID','CLIENT_SECRET','REDIRECT_URI')
 values={k:os.environ.get('WAREHOUSE_GOOGLE_'+k,'') for k in keys}
 # Explicit environment configuration takes precedence as a complete set.
 if any(values.values()):return values
 filename=os.environ.get('WAREHOUSE_GOOGLE_CONFIG')
 if not filename and os.name=='nt' and os.environ.get('LOCALAPPDATA'):
  filename=str(Path(os.environ['LOCALAPPDATA'])/'ScooterWarehouse'/'google-oauth.json')
 if not filename:return values
 try:
  data=json.loads(Path(filename).read_text(encoding='utf-8-sig'))
  if not isinstance(data,dict):return values
  result={k:data.get(k.lower(),'') for k in keys}
  return result if all(isinstance(v,str) and v.strip() for v in result.values()) else values
 except (OSError,ValueError):return values
def start(user_id):
 c=config();need(all(c.values()),'Google 로그인 설정이 필요합니다. 관리자에게 OAuth 클라이언트 설정을 요청하세요.',422)
 uri=urlparse(c['REDIRECT_URI']);need(uri.scheme=='https' or (uri.scheme=='http' and uri.hostname in ('127.0.0.1','localhost')),'Google 콜백 주소 설정 오류')
 state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48)
 with _lock:
  for key in list(_states):
   if _states[key]['until']<time.time() or _states[key]['user']==user_id:_states.pop(key)
  _states[state]={'user':user_id,'verifier':verifier,'until':time.time()+600}
 challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
 return {'url':'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({'client_id':c['CLIENT_ID'],'redirect_uri':c['REDIRECT_URI'],'response_type':'code','scope':SCOPE,'state':state,'code_challenge':challenge,'code_challenge_method':'S256','access_type':'online','prompt':'select_account consent'})}
def finish(state,code,client=None):
 with _lock:item=_states.pop(state,None)
 need(item and item['until']>=time.time(),'로그인 요청이 만료되었거나 유효하지 않습니다.',400)
 need(isinstance(code,str) and 0<len(code)<=4096,'Google 로그인이 취소되었습니다.')
 c=config();own=client is None;client=client or httpx.Client(timeout=30,follow_redirects=False)
 try:
  response=client.post('https://oauth2.googleapis.com/token',data={'code':code,'client_id':c['CLIENT_ID'],'client_secret':c['CLIENT_SECRET'],'redirect_uri':c['REDIRECT_URI'],'grant_type':'authorization_code','code_verifier':item['verifier']})
  need(response.status_code==200,'Google 로그인 연결에 실패했습니다.',403);data=response.json()
  need(SCOPE in data.get('scope','').split() and data.get('access_token'),'읽기 권한을 승인해야 합니다.',403)
  with _lock:_tokens[item['user']]={'access_token':data['access_token'],'until':time.time()+min(int(data.get('expires_in',3600)),3600)-30}
 except httpx.HTTPError:need(False,'Google 인증 서버 연결에 실패했습니다.',502)
 finally:
  if own:client.close()
def token(user_id):
 with _lock:
  data=_tokens.get(user_id)
  if data and data['until']>time.time():return data['access_token']
  _tokens.pop(user_id,None)
 return None

def connection_key(user_id,request):
 return user_id+':'+hashlib.sha256(request.headers.get('Authorization','').encode()).hexdigest()

def install(app,db,user):
 @app.post('/api/purchases/google/login')
 def login(request:Request):
  with db.read() as s:
   u=user(s,request);need(u.role in ('admin','worker'),'접근 권한이 없습니다.',403);ident=connection_key(u.id,request)
  return start(ident)
 @app.get('/api/purchases/google/status')
 def status(request:Request):
  with db.read() as s:ident=connection_key(user(s,request).id,request)
  return {'configured':all(config().values()),'connected':bool(token(ident))}
 @app.post('/api/purchases/google/disconnect')
 def disconnect(request:Request):
  with db.read() as s:ident=connection_key(user(s,request).id,request)
  with _lock:
   _tokens.pop(ident,None)
   for key in list(_states):
    if _states[key]['user']==ident:_states.pop(key)
  return {'ok':True}
 @app.get('/api/google/callback')
 def callback(request:Request):
  query=dict(request.query_params);request.scope['query_string']=b''
  finish(query.get('state',''),query.get('code',''))
  return HTMLResponse('<html lang="ko"><meta charset="utf-8"><h1>Google 연결 완료</h1><p>창고 프로그램으로 돌아가 가져오기를 누르세요.</p></html>',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
