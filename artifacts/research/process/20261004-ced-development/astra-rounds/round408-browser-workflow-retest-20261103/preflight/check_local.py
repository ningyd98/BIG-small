"""One approved local binding/tool prerequisite; no services or browser launched."""
from datetime import datetime, UTC
import ctypes
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import subprocess

root=Path('/home/ningyd/文档/ChatGPT/BIGsmall')
here=Path(__file__).resolve().parents[1]
release=json.loads((here.parent/'round409-writer-plain-run-terminal-receipts-20261103/preflight/r408-gate-release.json').read_text())
assert release['accepted']
for row in release['terminal_inputs']:
    b=(root/row['path']).read_bytes()
    assert len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256']
record={'started_utc':datetime.now(UTC).isoformat(),'kind':'dedicated local localhost ports and tool metadata; no product/server/Chromium invocation','ports':[],'tools':{},'accepted':False}
for port in [8000,5173,8123,5199]:
    entry={'port':port}
    try:
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            sock.bind(('127.0.0.1',port));sock.listen(1)
        entry['available']=True
    except OSError as error:
        entry.update(available=False,error_type=type(error).__name__,message=str(error))
    record['ports'].append(entry)
record['subreaper_return']=ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)
for relative in ['cache/node-v22.23.3-linux-x64/bin/node','.venv/bin/python','dashboard/node_modules/@playwright/test/cli.js']:
    p=root/relative;actual=p.resolve();s=actual.stat()
    record['tools'][relative]={'resolved':str(actual),'bytes':s.st_size,'mode':oct(s.st_mode),'executable':os.access(p,os.X_OK)}
record['node_version']=subprocess.check_output([str(root/'cache/node-v22.23.3-linux-x64/bin/node'),'--version'],text=True,timeout=5).strip()
record['playwright_version']=json.loads((root/'dashboard/node_modules/@playwright/test/package.json').read_text())['version']
record['mujoco_version']=importlib.metadata.version('mujoco')
record['chromium_binaries']=[str(p) for p in (root/'cache/playwright').glob('**/chrome') if p.is_file()]
record['accepted']=bool(all(r['available'] for r in record['ports']) and record['subreaper_return']==0 and record['node_version']=='v22.23.3' and record['chromium_binaries'])
record['ended_utc']=datetime.now(UTC).isoformat()
with (here/'preflight/local-prerequisite.json').open('x') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps(record,ensure_ascii=False))
if not record['accepted']:raise SystemExit(1)
