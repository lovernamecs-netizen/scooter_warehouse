"""Read-only Google Drive download; never changes the remote file."""
import os,re,json
from urllib.parse import urlparse,urljoin,quote
import httpx
from .domain import need
from .purchase_xlsx import parse
MAX_BYTES=20_000_000
XLSX='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

def file_id(url):
 need(isinstance(url,str) and len(url)<2048,'구글시트 URL을 입력하세요.')
 u=urlparse(url.strip())
 need(u.scheme=='https' and u.hostname=='docs.google.com' and not u.username and u.port in (None,443),'구글시트의 전체 페이지 주소를 입력하세요. 주소창에서 복사한 HTTPS 주소가 필요합니다.')
 m=re.fullmatch(r'/spreadsheets/d/([A-Za-z0-9_-]{10,200})(?:/[^?]*)?',u.path)
 need(m is not None,'구글시트 파일 주소를 확인하세요.')
 return m.group(1)

def download(client,url,headers=None):
 for _ in range(5):
  with client.stream('GET',url,headers=headers or {}) as response:
   if response.status_code in (301,302,303,307,308):
    target=urljoin(url,response.headers.get('location',''));u=urlparse(target)
    allowed=u.hostname in ('docs.google.com','drive.google.com','drive.usercontent.google.com') or (u.hostname or '').endswith('.googleusercontent.com')
    need(not headers and u.scheme=='https' and allowed and not u.username and u.port in (None,443),'Google 인증이 필요합니다. 관리자에게 읽기 전용 연결 설정을 요청하세요.',403)
    url=target;continue
   if response.status_code in (401,403,404):
    reason=''
    try:
     error=json.loads(response.read()).get('error',{});reason=next(iter(error.get('errors',[])),{}).get('reason','')
    except Exception:pass
    messages={'accessNotConfigured':'Google Drive API가 OAuth 클라이언트와 같은 프로젝트에서 활성화되었는지 확인하세요.','insufficientPermissions':'Google 읽기 권한이 부족합니다. 연결 해제 후 다시 로그인하여 읽기 권한을 승인하세요.','fileNotDownloadable':'현재 원본은 이 다운로드 방식으로 읽을 수 없습니다. 파일 형식 확인이 필요합니다.','downloadRestrictedForRevision':'원본 파일 다운로드가 제한되어 있습니다. 파일 소유자의 다운로드 권한 설정을 확인하세요.','notFound':'로그인한 Google 계정에서 해당 파일을 찾을 수 없습니다. URL과 파일 공유 권한을 확인하세요.'}
    message=messages.get(reason,'Google에서 파일 읽기를 거부했습니다. 로그인 계정의 파일 열기·다운로드 권한을 확인하세요.')
    if response.status_code==401:message='Google 인증이 만료되었습니다. 다시 로그인하세요.'
    need(False,message,403)
   need(response.status_code==200,'Google 파일을 읽을 수 없습니다. 읽기 권한과 API 연결 설정을 확인하세요.',403 if response.status_code in (401,403,404) else 422)
   chunks=[];size=0
   for chunk in response.iter_bytes():
    size+=len(chunk);need(size<=MAX_BYTES,'파일은 20MB 이하만 가져올 수 있습니다.');chunks.append(chunk)
   return b''.join(chunks)
 need(False,'Google 다운로드 경로를 확인하지 못했습니다.')

def read(url,sheet,client=None,access_token=None):
 ident=file_id(url);need(isinstance(sheet,str) and 0<len(sheet.strip())<=100,'탭 이름을 입력하세요.');sheet=sheet.strip()
 own=client is None;client=client or httpx.Client(timeout=60,follow_redirects=False)
 try:
  credentials_path=os.environ.get('WAREHOUSE_GOOGLE_CREDENTIALS','')
  if credentials_path or access_token:
   if not access_token:
    try:
     from google.oauth2 import service_account
     from google.auth.transport.requests import Request
     credentials=service_account.Credentials.from_service_account_file(credentials_path,scopes=['https://www.googleapis.com/auth/drive.readonly']);credentials.refresh(Request());access_token=credentials.token
    except Exception:
     need(False,'Google 읽기 전용 인증 설정을 확인하세요.',403)
   headers={'Authorization':'Bearer '+access_token}
   base='https://www.googleapis.com/drive/v3/files/'+ident
   meta=json.loads(download(client,base+'?fields=mimeType&supportsAllDrives=true',headers))
   mime=meta.get('mimeType')
   need(mime in (XLSX,'application/vnd.google-apps.spreadsheet'),'XLSX 또는 Google 스프레드시트만 지원합니다.')
   endpoint=base+('/export?mimeType='+quote(XLSX,safe='') if mime=='application/vnd.google-apps.spreadsheet' else '?alt=media&supportsAllDrives=true')
   data=download(client,endpoint,headers)
  else:
   data=download(client,'https://drive.usercontent.google.com/download?id='+ident+'&export=download')
   need(data.startswith(b'PK'),'이 파일은 Google 인증 연결이 필요합니다. 파일 공개 설정을 바꾸지 말고 관리자에게 읽기 전용 연결을 요청하세요.',403)
  result=parse(data,'google-source.xlsx',sheet)
  result['google_source']={'file_id':ident,'sheet':sheet,'url':'https://docs.google.com/spreadsheets/d/'+ident+'/edit'}
  return result
 except httpx.HTTPError:
  need(False,'Google 연결에 실패했습니다. 잠시 후 다시 시도하세요.',502)
 finally:
  if own:client.close()
