"""Actual isolated server; random loopback port and instance identity, synthetic DB/media only."""
from pathlib import Path
import subprocess,sys,os,tempfile,time,httpx,socket,uuid,shutil,json
PASSWORD='LocalTestOnly-1234'
ROOT=Path(__file__).resolve().parents[1]
RESULTS=ROOT.parent/'purchase-sheet-results';RESULTS.mkdir(exist_ok=True)
CHROME=r'C:\Program Files\Google\Chrome\Application\chrome.exe'

def start(port=0,demo=True):
    temp=tempfile.TemporaryDirectory(prefix='warehouse-smoke-')
    directory=Path(temp.name);identity=uuid.uuid4().hex
    env=dict(os.environ,DATABASE_URL='sqlite:///'+str(directory/'test.db'),WAREHOUSE_ADMIN_PASSWORD=PASSWORD,PYTHONUTF8='1',PYTHONPATH=str(ROOT));env.pop('TEST_DATABASE_URL',None);env.pop('WAREHOUSE_DATA_DIR',None)
    from cryptography.fernet import Fernet
    private=directory/'customer.key';private.write_bytes(Fernet.generate_key());env['WAREHOUSE_CUSTOMER_KEY_FILE']=str(private)
    process=log=None
    try:
        for action in (['init','demo'] if demo else ['init']):
            subprocess.run([sys.executable,'-X','utf8','-B','-m','server.cli',action],cwd=ROOT,env=env,check=True,capture_output=True)
        with socket.socket() as sock:sock.bind(('127.0.0.1',port));port=sock.getsockname()[1]
        runner=directory/'run.py'
        runner.write_text("import os,uvicorn\nfrom server.app import create_app\napp=create_app()\n@app.get('/__smoke_identity')\ndef identity():return {'id':'"+identity+"','pid':os.getpid()}\napp.router.routes.insert(0,app.router.routes.pop())\nuvicorn.run(app,host='127.0.0.1',port="+str(port)+",log_level='warning')\n",encoding='utf-8')
        log=open(directory/'server.log','w',encoding='utf-8');process=subprocess.Popen([sys.executable,'-X','utf8','-B',str(runner)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        base='http://127.0.0.1:'+str(port)
        for _ in range(150):
            if process.poll() is not None:raise RuntimeError('Isolated server exited during startup')
            try:
                data=httpx.get(base+'/__smoke_identity',trust_env=False,timeout=1).json()
                if data.get('id')==identity:return process,temp,log,base
            except (httpx.HTTPError,ValueError):pass
            time.sleep(.1)
        raise RuntimeError('Isolated server identity/startup timeout')
    except BaseException:
        if process and process.poll() is None:subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True) if os.name=='nt' else process.terminate();process.wait(timeout=10)
        if log:log.close();shutil.copy2(directory/'server.log',RESULTS/('startup-'+identity+'.log'))
        temp.cleanup();raise

def stop(runtime):
    process,temp,log,_=runtime
    if process.poll() is None:
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True) if os.name=='nt' else process.terminate()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    if OBSERVATIONS:(RESULTS/('browser-network-'+str(process.pid)+'.json')).write_text(json.dumps(OBSERVATIONS,ensure_ascii=False,indent=2),encoding='utf-8')
    log.close();shutil.copy2(Path(temp.name)/'server.log',RESULTS/('server-'+str(process.pid)+'.log'));temp.cleanup()

OBSERVATIONS={}
def observe(page,label):
    data={'pageerror':[],'console_error':[],'requestfailed':[]};OBSERVATIONS[label]=data
    page.on('pageerror',lambda e:data['pageerror'].append(str(e)))
    page.on('console',lambda m:data['console_error'].append(m.text) if m.type=='error' else None)
    page.on('requestfailed',lambda r:data['requestfailed'].append({'url':r.url.split('?')[0],'failure':r.failure}))
    return data
