"""R139 exact single-use subprocess capture; updates only the author ledger."""

import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

BASE = Path(__file__).resolve().parent.parent
ledger_path = BASE / 'command-ledger.json'
key = sys.argv[1]
ledger = json.loads(ledger_path.read_text())
plan = json.loads((BASE / 'plan.json').read_text())
assert hashlib.sha256((BASE / 'plan.json').read_bytes()).hexdigest() == ledger['source_plan_sha256']
assert key in plan['new_command_order']
command = ledger['commands'][key]
assert command['used'] == 0 and command['remaining'] == 1
for previous in plan['new_command_order'][:plan['new_command_order'].index(key)]:
    assert ledger['commands'][previous]['actual_exit_code'] == 0
if key == 'delta_proof':
    assert ledger['delta_gate'] == 'ROOT_TEXT_REVIEW_APPROVED'
    assert hashlib.sha256((BASE / 'implementation/delta-proof.py').read_bytes()).hexdigest() == ledger['reviewed_delta_script_sha256']
for field in ('argv', 'cwd', 'env', 'evidence_dir', 'expected_exit'):
    assert command[field] == plan['new_commands'][key][field]
output = Path(command['evidence_dir'])
assert not output.exists()
output.mkdir()
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
invocation = {'argv': command['argv'], 'cwd': command['cwd'],
              'env_overrides': command['env'], 'started_utc': started,
              'capture': 'Independent binary subprocess stdout and stderr; actual return code'}
command.update(used=1, remaining=0, status='SPENT_BEFORE_INVOCATION', started_utc=started)
ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n')
(output / 'invocation.json').write_text(json.dumps(invocation, ensure_ascii=False, indent=2) + '\n')
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
result_blob = (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode()
with (output / 'result.json').open('xb') as stream:
    stream.write(result_blob)
command.update(actual_exit_code=completed.returncode, ended_utc=ended,
               status='SPENT_COMPLETED' if completed.returncode == 0 else 'SPENT_FAILED_PRESERVED',
               actual_result=str(output / 'result.json'),
               actual_result_sha256=hashlib.sha256(result_blob).hexdigest())
ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'command': key, 'actual_exit_code': completed.returncode,
                  'result': str(output / 'result.json'),
                  'sha256': hashlib.sha256(result_blob).hexdigest()}, ensure_ascii=False))
