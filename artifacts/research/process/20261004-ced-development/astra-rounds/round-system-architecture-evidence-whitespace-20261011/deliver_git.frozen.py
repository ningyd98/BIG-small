from pathlib import Path
from hashlib import sha256
import json
import shutil
import subprocess

source_root = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
delivery_root = Path('/home/ningyd/.codex/worktrees/t12-p1-delivery/BIGsmall')
work = Path('/tmp/bigsmall-system-architecture-20261011')
branch = 'codex/research-20261007-p1-delivery'
expected_head = '0bb613a6e927ae817e70abfc8b9ecaeb8f88d1c1'
manifest = json.loads((work / 'delivery-manifest.json').read_text(encoding='utf-8'))

def git(*args):
    return subprocess.check_output(['git', *args], cwd=delivery_root, text=True).strip()

assert git('status', '--porcelain') == ''
assert git('branch', '--show-current') == branch
assert git('rev-parse', 'HEAD') == expected_head
for entry in manifest:
    source = source_root / entry['path']
    target = delivery_root / entry['path']
    assert sha256(source.read_bytes()).hexdigest() == entry['sha256']
    assert not target.exists()

for entry in manifest:
    source = source_root / entry['path']
    target = delivery_root / entry['path']
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    assert sha256(target.read_bytes()).hexdigest() == entry['sha256']

paths = [entry['path'] for entry in manifest]
git('add', '--', *paths)
git('diff', '--cached', '--check')
staged = set(git('diff', '--cached', '--name-only').splitlines())
expected_staged = set(paths)
# Git normally quotes non-ASCII paths, so request literal UTF-8 for this check.
staged = set(git('-c', 'core.quotepath=false', 'diff', '--cached', '--name-only').splitlines())
assert staged == expected_staged
print(git('commit', '--only', '-m', 'docs(research): add system architecture diagram to opening report', '--', *paths))
print(git('push', 'origin', branch))
local_sha = git('rev-parse', 'HEAD')
upstream_sha = git('rev-parse', '@{upstream}')
remote_sha = git('ls-remote', 'origin', f'refs/heads/{branch}').split()[0]
assert local_sha == upstream_sha == remote_sha
assert git('status', '--porcelain') == ''
result = {'branch': branch, 'local_sha': local_sha, 'upstream_sha': upstream_sha, 'remote_sha': remote_sha, 'all_equal': True, 'clean_delivery_worktree': True, 'delivered_files': paths}
(work / 'push-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in result.items() if k != 'delivered_files'}, ensure_ascii=False, indent=2))
