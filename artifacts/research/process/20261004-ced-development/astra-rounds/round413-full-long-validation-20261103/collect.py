"""Freeze current sources and perform one read-only pytest collection."""
from pathlib import Path
import hashlib, importlib.metadata, json, os, signal, subprocess, time
from datetime import datetime, UTC
ROOT=Path.cwd(); ROUND=Path(__file__).resolve().parent; D=ROUND/'preflight'
def save(p,x):
    with p.open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2);f.write('\n')
raw=subprocess.run(['git','ls-files','-z','--cached','--others','--exclude-standard'],check=True,capture_output=True).stdout
files=[];digest=hashlib.sha256()
for name in sorted(set(s.decode() for s in raw.split(b'\0') if s)):
    p=Path(name)
    if p.parts[0] in {'artifacts','docs','thesis'} or p.name.endswith('.pyc') or '__pycache__' in p.parts:continue
    data=p.read_bytes() if p.is_file() else b'<missing>'
    files.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    digest.update(name.encode());digest.update(b'\0');digest.update(data);digest.update(b'\0')
head=subprocess.run(['git','rev-parse','HEAD'],check=True,text=True,capture_output=True).stdout.strip()
save(D/'source-before.json',{'source_commit':head,'source_tree_hash':digest.hexdigest(),'files':files,'file_count':len(files)})
versions={}
for n in ['pytest','ruff','mypy','mujoco','numpy','pydantic','httpx']:
    try:versions[n]=importlib.metadata.version(n)
    except importlib.metadata.PackageNotFoundError:versions[n]=None
save(D/'versions.json',versions)
env={k:os.environ[k] for k in ['HOME','USER','LOGNAME','TMPDIR','LD_LIBRARY_PATH','DISPLAY','XAUTHORITY'] if k in os.environ}
env.update(PATH=str(ROOT/'cache/node-v22.23.3-linux-x64/bin')+':'+str(ROOT/'.venv/bin')+':/usr/bin:/bin',LANG='C.UTF-8',PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTHONPATH=str(ROOT/'src')+':'+str(ROOT)+':'+str(ROUND/'adapters'),REAL_MOTION_DISPATCH_ENABLED='false',MUJOCO_GL='egl',GIT_OPTIONAL_LOCKS='0',R413_COLLECTION=str(D/'collection.json'))
argv=[str(ROOT/'.venv/bin/python'),'-m','pytest','--collect-only','-q','-p','no:cacheprovider','-p','r413_collect']
save(D/'collection-invocation.json',{'argv':argv,'cwd':str(ROOT),'env':env,'timeout_s':120,'started_utc':datetime.now(UTC).isoformat(),'purpose':'READ_ONLY_PLAN_INPUT'})
start=time.monotonic();state='FINISHED';signals=[]
with (D/'collection.stdout').open('xb') as out,(D/'collection.stderr').open('xb') as err:
    proc=subprocess.Popen(argv,env=env,stdout=out,stderr=err,stdin=subprocess.DEVNULL,start_new_session=True)
    try:proc.wait(timeout=120)
    except subprocess.TimeoutExpired:
        state='TIMEOUT';os.killpg(proc.pid,signal.SIGTERM);signals.append('SIGTERM')
        try:proc.wait(timeout=5)
        except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);signals.append('SIGKILL');proc.wait()
save(D/'collection-result.json',{'state':state,'returncode':proc.returncode,'elapsed_s':time.monotonic()-start,'reaped':True,'signals':signals,'ended_utc':datetime.now(UTC).isoformat()})
print(json.dumps({'state':state,'returncode':proc.returncode,'source_hash':digest.hexdigest(),'files':len(files)}))
