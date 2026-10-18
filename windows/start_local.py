"""Bind the requested socket before opening a browser; never adopt another server."""
import argparse,os,socket,sys,threading,time,json,urllib.request,webbrowser,uuid
from pathlib import Path

def main(argv=None):
 parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);parser.add_argument('--no-browser',action='store_true');parser.add_argument('--no-dialog',action='store_true');args=parser.parse_args(argv)
 root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
 try:
  sock=socket.socket();sock.bind(('127.0.0.1',args.port));sock.listen(128)
 except OSError:return fail('포트를 사용할 수 없습니다. 실행 중인 서버와 포트 설정을 확인하세요.',args)
 try:
  import uvicorn
  from server.app import create_app
  app=create_app();identity=uuid.uuid4().hex
  @app.get('/_startup_identity')
  def identify():return {'id':identity}
  app.router.routes.insert(0,app.router.routes.pop())
  url='http://127.0.0.1:'+str(sock.getsockname()[1])
  def open_when_ready():
   for _ in range(150):
    try:
     with urllib.request.urlopen(url+'/_startup_identity',timeout=1) as r:ready=json.load(r).get('id')==identity
     if ready:
      print('서버 준비 완료: '+url,flush=True)
      if not args.no_browser:webbrowser.open(url)
      return
    except Exception:pass
    time.sleep(.2)
  threading.Thread(target=open_when_ready,daemon=True).start()
  server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=args.port));server.run(sockets=[sock])
  return 0 if server.started else fail('서버 준비에 실패했습니다. DB 접근 권한과 시작 로그를 확인하세요.',args,'STARTUP_FAILED')
 except (Exception,SystemExit) as exc:
  return fail('서버를 시작하지 못했습니다. Python 의존성과 DB 접근 권한을 확인하세요.',args,type(exc).__name__)
 finally:sock.close()

def fail(message,args,kind='PORT_UNAVAILABLE'):
 # Startup is before API handling; report concise diagnostics without credentials.
 try:
  from server.storage_paths import data_root
  base=data_root();directory=base/'Logs' if base else Path.cwd()/'logs'
  directory.mkdir(parents=True,exist_ok=True)
 except Exception:
  directory=Path(os.getenv('TEMP',str(Path.home())))/'ScooterWarehouse-startup-logs';directory.mkdir(parents=True,exist_ok=True)
 from logging.handlers import RotatingFileHandler
 import logging
 handler=RotatingFileHandler(directory/'startup.log',maxBytes=1024*1024,backupCount=2,encoding='utf-8')
 handler.emit(logging.LogRecord('startup',logging.ERROR,'',0,kind,(),None));handler.close()
 text=message+'\n상세 확인: '+str(directory/'startup.log');print(text,file=sys.stderr)
 if os.name=='nt' and not args.no_dialog:
  import ctypes
  ctypes.windll.user32.MessageBoxW(None,text,'ScooterWarehouse 시작 실패',16)
 return 1

if __name__=='__main__':sys.exit(main())
