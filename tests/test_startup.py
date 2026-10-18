import os,sys,socket,subprocess,time,tempfile
from pathlib import Path
import httpx

def test_windows_startup_and_port_collision(tmp_path):
 root=Path(__file__).resolve().parents[1]
 env=dict(os.environ,PYTHONPATH=str(root),DATABASE_URL='sqlite:///'+str(tmp_path/'test.db'),WAREHOUSE_ADMIN_PASSWORD='Isolated-test-1234',PYTHONUTF8='1');env.pop('TEST_DATABASE_URL',None)
 subprocess.run([sys.executable,'-m','server.cli','init'],cwd=tmp_path,env=env,check=True,capture_output=True)
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 args=[sys.executable,'-X','utf8','-B',str(root/'windows/start_local.py'),'--port',str(port),'--no-browser','--no-dialog']
 with (tmp_path/'startup-output.log').open('w') as log:
  process=subprocess.Popen(args,cwd=tmp_path,env=env,stdout=log,stderr=subprocess.STDOUT)
  try:
   for _ in range(100):
    assert process.poll() is None
    try:
     r=httpx.get(f'http://127.0.0.1:{port}/_startup_identity',trust_env=False,timeout=1)
     if r.status_code==200 and r.json().get('id'):break
    except httpx.HTTPError:pass
    time.sleep(.1)
   else:raise AssertionError('startup timeout')
   assert httpx.get(f'http://127.0.0.1:{port}/health',trust_env=False).json()['ok']
   collision=subprocess.run(args,cwd=tmp_path,env=env,capture_output=True,timeout=10)
   assert collision.returncode==1 and (tmp_path/'logs/startup.log').exists()
   assert process.poll() is None
  finally:
   if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
   else:process.terminate()
   process.wait(timeout=10)
