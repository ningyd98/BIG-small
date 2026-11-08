import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

repo = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
out = repo / 'artifacts/research/process/20261004-ced-development/astra-rounds/round489-encrypted-model-secret-persistence-20261108/execution'
label, *args = sys.argv[1:]
cwd = repo
dashboard = False
if args and args[0] == '--dashboard':
    cwd = repo / 'dashboard'
    dashboard = True
    args.pop(0)
if args and args[0] == '--':
    args.pop(0)
paths = {kind: out / f'{label}.{kind}' for kind in ('stdout', 'stderr', 'json')}
if any(path.exists() for path in paths.values()):
    raise SystemExit('Evidence name already exists; choose a unique attempt name')
env = os.environ.copy()
env.pop('MODEL_CONTROL_SECRET_DIR', None)
env.pop('MODEL_CONTROL_SECRET_STORE', None)
env['BIGSMALL_VLM_ALLOW_PAID_CALL'] = 'false'
env['PIP_DISABLE_PIP_VERSION_CHECK'] = '1'
isolated_xdg = tempfile.TemporaryDirectory(prefix='bigsmall-r492-xdg-', dir='/tmp') if 'pytest' in args else None
if isolated_xdg is not None:
    env['XDG_DATA_HOME'] = isolated_xdg.name
runtime = None
if dashboard:
    runtime = json.loads((Path(__file__).parent / 'r490-node-identity.json').read_text())
    node = Path(runtime['path'])
    assert hashlib.sha256(node.read_bytes()).hexdigest() == runtime['sha256']
    env['PATH'] = str(node.parent) + os.pathsep + env['PATH']
    selected_version = subprocess.check_output(['node','--version'], env=env, text=True).strip()
    assert selected_version == runtime['version']
started = time.monotonic()
proc = subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
timeout = False
try:
    stdout, stderr = proc.communicate(timeout=180)
except subprocess.TimeoutExpired:
    timeout = True
    os.killpg(proc.pid, signal.SIGKILL)
    stdout, stderr = proc.communicate()
paths['stdout'].write_bytes(stdout)
paths['stderr'].write_bytes(stderr)
if isolated_xdg is not None:
    isolated_xdg.cleanup()
report = {'command': args, 'cwd': str(cwd), 'returncode': proc.returncode, 'elapsed_seconds': round(time.monotonic()-started,3), 'timeout': timeout,
          'dashboard_runtime': runtime,
          'temporary_test_xdg': isolated_xdg.name if isolated_xdg is not None else None,
          'files': {kind: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for kind, data in [('stdout',stdout),('stderr',stderr)]}}
paths['json'].write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report, ensure_ascii=False))
print(stdout.decode(errors='replace')[-7000:])
print(stderr.decode(errors='replace')[-2000:])
raise SystemExit(proc.returncode)
