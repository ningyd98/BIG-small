from pathlib import Path
from datetime import UTC, datetime
import hashlib
import json
import os
import subprocess
import sys

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUND = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round145-p6-mypy-type-contract-recovery-20261012'
PLAN_SHA = '91ae27194e5a2d5c09e3610a3ef52af12a9e888a124fef443dec46d13197c558'
key = sys.argv[1]
order = ['formatter', 'delta_proof', 'ruff', 'mypy']
assert key in order
plan_bytes = (ROUND / 'plan.json').read_bytes()
assert hashlib.sha256(plan_bytes).hexdigest() == PLAN_SHA
plan = json.loads(plan_bytes)
ledger_path = ROUND / 'command-ledger.json'
ledger = json.loads(ledger_path.read_bytes())
assert ledger['plan_sha256'] == PLAN_SHA
assert ledger['script_gate'] == 'ROOT_FULL_TEXT_REVIEW_APPROVED'
assert ledger['reviewed_runner_sha256'] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
assert ledger['reviewed_delta_script_sha256'] == hashlib.sha256((ROUND / 'implementation/type-delta-proof.py').read_bytes()).hexdigest()
if key == 'formatter':
    assert set(ledger['reviewed_draft_source_sha256']) == set(plan['scope']['edit_paths'])
    for path, expected in ledger['reviewed_draft_source_sha256'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected
for prior in order[:order.index(key)]:
    previous = ledger['commands'][prior]
    assert previous['used'] == 1 and previous['remaining'] == 0
    result_path = Path(previous['evidence_dir']) / 'result.json'
    assert hashlib.sha256(result_path.read_bytes()).hexdigest() == previous['actual_result_sha256']
    assert json.loads(result_path.read_bytes())['actual_exit_code'] == 0
command = ledger['commands'][key]
assert command['authorized'] == 1 and command['used'] == 0 and command['remaining'] == 1
for field in ('argv', 'cwd', 'env', 'evidence_dir', 'expected_exit'):
    assert command[field] == plan['new_commands'][key][field]
assert command['cwd'] == str(ROOT)
output = Path(command['evidence_dir'])
assert not output.exists()
if key == 'mypy':
    assert not Path('/tmp/bigsmall-p6-r145-mypy').exists()
started = datetime.now(UTC).isoformat()
command.update(used=1, remaining=0, status='SPENT_BEFORE_INVOCATION', started_utc=started)
ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n')
output.mkdir(parents=True, exist_ok=False)
invocation = {'argv': command['argv'], 'cwd': command['cwd'], 'env_overrides': command['env'], 'started_utc': started, 'capture': 'Independent binary subprocess stdout and stderr; actual return code'}
(output / 'invocation.json').write_text(json.dumps(invocation, ensure_ascii=False, indent=2) + '\n')
env = os.environ.copy()
env.update(command['env'])
with (output / 'stdout.txt').open('xb') as stdout, (output / 'stderr.txt').open('xb') as stderr:
    completed = subprocess.run(command['argv'], cwd=command['cwd'], env=env, stdout=stdout, stderr=stderr)
result = dict(invocation, ended_utc=datetime.now(UTC).isoformat(), actual_exit_code=completed.returncode, expected_exit_code=command['expected_exit'])
result['raw_outputs'] = {name: {'path': str(output / name), 'bytes': (output / name).stat().st_size, 'sha256': hashlib.sha256((output / name).read_bytes()).hexdigest()} for name in ('stdout.txt', 'stderr.txt')}
serialized = (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode()
with (output / 'result.json').open('xb') as stream:
    stream.write(serialized)
command.update(status='COMPLETED', actual_exit_code=completed.returncode, actual_result_sha256=hashlib.sha256(serialized).hexdigest(), ended_utc=result['ended_utc'])
ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'command': key, 'actual_exit_code': completed.returncode, 'result': str(output / 'result.json'), 'sha256': command['actual_result_sha256']}, ensure_ascii=False))
