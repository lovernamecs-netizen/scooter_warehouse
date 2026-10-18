"""Build a file-only release from a known Git baseline; never include runtime data."""
import argparse,hashlib,json,shutil,subprocess,zipfile
from pathlib import Path

def build(root,output,git):
    base='0087e51151d61a6b1d2962f8db028bea85d6519c'
    def run(*args):return subprocess.check_output([git,'-C',str(root),*args])
    names=run('ls-tree','-r','--name-only',base).decode().splitlines()
    baseline={n:hashlib.sha256(run('show',base+':'+n)).hexdigest() for n in names if n.startswith(('server/','web/')) or n=='requirements.txt'}
    changed=run('diff','--name-only',base).decode().splitlines()+run('ls-files','--others','--exclude-standard').decode().splitlines()
    runtime=[n for n in changed if n.startswith(('server/','web/'))]
    output.mkdir(parents=True,exist_ok=False)
    m={'format':1,'patch':'1.0.31-closing-20261016','base_version':'1.0.30','target_version':'1.0.31','base_commit':base,'baseline':baseline,'files':{}}
    for name in sorted(runtime):
        src=root/name
        if not src.is_file() or src.suffix not in ['.py','.js','.json','.html','.css','.svg']:raise ValueError('Unsupported runtime change: '+name)
        dest=output/'payload'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
        m['files'][name]={'before':baseline.get(name),'after':hashlib.sha256(src.read_bytes()).hexdigest()}
    (output/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    shutil.copy2(root/'tools/install_patch.py',output/'install_patch.py')
    review=[n for n in changed if n.startswith(('tests/','tools/','docs/')) or n in ['android/app/build.gradle','android/app/src/main/java/com/hakom/warehouse/MainActivity.java']]
    for name in sorted(review):
        src=root/name
        if src.suffix not in ['.py','.md','.java','.gradle']:raise ValueError('Unsupported review file: '+name)
        dest=output/'review'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
    return m

def seal(output):
    hashes=[]
    for p in sorted(output.rglob('*')):
        if p.is_file() and p.name!='SHA256SUMS.txt':hashes.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(output).as_posix())
    (output/'SHA256SUMS.txt').write_text('\n'.join(hashes)+'\n',encoding='utf-8')
    archive=Path(str(output)+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(output.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(output).as_posix())
    return archive,hashlib.sha256(archive.read_bytes()).hexdigest()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--git',required=True);a=p.parse_args()
    m=build(Path(__file__).resolve().parents[1],a.output,a.git);archive,digest=seal(a.output);print(json.dumps({'archive':str(archive),'sha256':digest,'files':len(m['files'])}))
