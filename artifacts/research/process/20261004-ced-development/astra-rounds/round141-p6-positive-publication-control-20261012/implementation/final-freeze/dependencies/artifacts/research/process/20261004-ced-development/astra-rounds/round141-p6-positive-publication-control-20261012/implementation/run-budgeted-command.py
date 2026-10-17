"""R141 one-shot exact subprocess capture, author ledger only, no retries."""

import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

BASE = Path(__file__).resolve().parent.parent
ORDER = ('test_formatter', 'scope_proof', 'test_ruff', 'positive_control')
key = sys.argv[1]
assert len(sys.argv) == 2 and key in ORDER
plan_blob = (BASE / 'plan.json').read_bytes()
assert hashlib.sha256(plan_blob).hexdigest() == '2bb2e3e28c15e10f0af1d05b9f7815ac0e87b9f76c8536b8b755a77c58b9b6c5'
plan = json.loads(plan_blob)
ledger_path = BASE / 'command-ledger.json'
ledger = json.loads(ledger_path.read_text())
assert ledger['script_gate'] == 'ROOT_FULL_TEXT_REVIEW_APPROVED'
assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == ledger['reviewed_runner_sha256']
assert hashlib.sha256((BASE / 'implementation/scope-proof.py').read_bytes()).hexdigest() == ledger['reviewed_scope_script_sha256']
if key == 'test_formatter':
    assert hashlib.sha256(Path(plan['scope']['edit_path']).read_bytes()).hexdigest() == ledger['reviewed_test_sha256']
if key == 'positive_control':
    assert ledger['positive_gate'] == 'ROOT_FINAL_SOURCE_FIXTURE_PROOF_REVIEW_APPROVED'
    assert hashlib.sha256(Path(plan['scope']['edit_path']).read_bytes()).hexdigest() == ledger['positive_reviewed_test_sha256']
command = ledger['commands'][key]
assert command['used'] == 0 and command['remaining'] == 1
for prior in ORDER[:ORDER.index(key)]:
    assert ledger['commands'][prior]['used'] == 1
    assert ledger['commands'][prior]['remaining'] == 0
    assert ledger['commands'][prior]['actual_exit_code'] == 0
for field in ('argv', 'cwd', 'env', 'expected_exit', 'evidence_dir'):
    assert command[field] == plan['new_commands'][key][field]
output = Path(command['evidence_dir'])
assert not output.exists()
if key == 'positive_control':
    assert not Path('/tmp/bigsmall-p6-r141-positive-control').exists()
    assert command['worker_poll_lifecycle_cap'] == command['episode_calls_cap'] == 1
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
invocation = {'argv': command['argv'], 'cwd': command['cwd'],
              'env_overrides': command['env'], 'started_utc': started,
              'capture': 'Independent binary subprocess stdout and stderr; actual return code'}
command.update(used=1, remaining=0, status='SPENT_BEFORE_INVOCATION', started_utc=started)
ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n')
output.mkdir()
with (output / 'invocation.json').open('x') as stream:
    stream.write(json.dumps(invocation, ensure_ascii=False, indent=2) + '\n')
environment = os.environ.copy()
environment.update(command['env'])
with (output / 'stdout.txt').open('xb') as stdout, (output / 'stderr.txt').open('xb') as stderr:
    completed = subprocess.run(command['argv'], cwd=command['cwd'], env=environment,
                               stdout=stdout, stderr=stderr, check=False)
ended = datetime.datetime.now(datetime.timezone.utc).isoformat()
raw = {}
for name in ('stdout.txt', 'stderr.txt'):
    blob = (output / name).read_bytes()
    raw[name] = {'path': str(output / name), 'bytes': len(blob),
                 'sha256': hashlib.sha256(blob).hexdigest()}
result = {**invocation, 'ended_utc': ended, 'actual_exit_code': completed.returncode,
          'expected_exit_code': command['expected_exit'], 'raw_outputs': raw}
serialized = (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode()
with (output / 'result.json').open('xb') as stream:
    stream.write(serialized)
command.update(actual_exit_code=completed.returncode, ended_utc=ended,
               status='SPENT_COMPLETED' if completed.returncode == 0 else 'SPENT_FAILED_PRESERVED',
               actual_result=str(output / 'result.json'),
               actual_result_sha256=hashlib.sha256(serialized).hexdigest())
ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'command': key, 'actual_exit_code': completed.returncode,
                  'result': str(output / 'result.json'),
                  'sha256': hashlib.sha256(serialized).hexdigest()}, ensure_ascii=False))
