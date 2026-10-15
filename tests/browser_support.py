"""Isolated, reproducible browser test server. Never opens a production DB."""
from pathlib import Path
import subprocess,sys,os,tempfile,time,httpx
PASSWORD='LocalTestOnly-1234'
ROOT=Path(__file__).resolve().parents[1]
def start(port):
    temp=tempfile.TemporaryDirectory(prefix='warehouse-ui-')
    env=dict(os.environ,DATABASE_URL='sqlite:///'+str(Path(temp.name)/'test.db'),WAREHOUSE_ADMIN_PASSWORD=PASSWORD)
    for action in ['init','demo']:
        subprocess.run([sys.executable,'-m','server.cli',action],cwd=ROOT,env=env,check=True,capture_output=True)
    log=open(Path(temp.name)/'server.log','w')
    process=subprocess.Popen([sys.executable,'-m','uvicorn','server.app:app','--port',str(port)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    base='http://127.0.0.1:'+str(port)
    for _ in range(50):
        try:
            if httpx.get(base+'/health',trust_env=False).status_code==200:break
        except httpx.HTTPError:pass
        time.sleep(.1)
    else:raise RuntimeError('Test server did not start')
    return process,temp,log,base

def stop(runtime):
    process,temp,log,_=runtime;process.terminate();process.wait(timeout=10);log.close();temp.cleanup()
