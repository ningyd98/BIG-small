from pathlib import Path
from datetime import UTC, datetime
import json
import os
import shutil
import subprocess
import urllib.request

repo = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
work = Path(__file__).parent
result = {'kind': 'actual_readonly_resource_process_admission', 'captured_utc': datetime.now(UTC).isoformat(), 'runtime_mutations': 0, 'planner_posts': 0, 'commands': []}
for args in [
    ['nvidia-smi', '--query-gpu=index,memory.free', '--format=csv,noheader,nounits'],
    ['nvidia-smi', '--query-compute-apps=pid,process_name,used_memory', '--format=csv,noheader,nounits'],
    ['systemctl', '--user', 'show', 'qwen38-flash-strata.service', '--property=LoadState,ActiveState,SubState,MainPID,ControlPID'],
    ['git', 'rev-parse', 'HEAD'],
]:
    completed = subprocess.run(args, cwd=repo, capture_output=True, text=True, timeout=10)
    result['commands'].append({'argv': args, 'returncode': completed.returncode, 'stdout': completed.stdout, 'stderr': completed.stderr})
lock = repo / 'cache/research/.r468-r469-gpu.lock'
info = lock.stat()
key = f'{os.major(info.st_dev):02x}:{os.minor(info.st_dev):02x}:{info.st_ino}'
result['lock'] = {'path': str(lock), 'inode': info.st_ino, 'kernel_rows': [line for line in Path('/proc/locks').read_text().splitlines() if key in line]}
result['disk_free_bytes'] = shutil.disk_usage(repo).free
result['processes'] = []
for pid in (1506084, 159968):
    path = Path('/proc') / str(pid)
    item = {'pid': pid, 'exists': path.exists()}
    if path.exists():
        fields = (path / 'stat').read_text().rsplit(')', 1)[1].split()
        item.update({'state': fields[0], 'starttime_ticks': int(fields[19]), 'cwd': os.readlink(path / 'cwd'), 'uid': path.stat().st_uid})
    result['processes'].append(item)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
result['health'] = []
for url in ('http://127.0.0.1:8000/health', 'http://127.0.0.1:5173/models'):
    try:
        with opener.open(url, timeout=2) as response:
            result['health'].append({'url': url, 'status': response.status})
    except Exception as error:
        result['health'].append({'url': url, 'error_class': type(error).__name__})
target = work / 'r498-readonly-admission-20261109.json'
with target.open('x') as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print(json.dumps({'saved': str(target), 'command_returncodes': [row['returncode'] for row in result['commands']], 'lock_free': not result['lock']['kernel_rows'], 'processes_present': all(p['exists'] for p in result['processes'])}))
