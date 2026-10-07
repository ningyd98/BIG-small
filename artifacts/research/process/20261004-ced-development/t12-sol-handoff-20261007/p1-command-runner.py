"""Exclusive evidence wrapper; executes one selected already-authorized command."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

base = Path('artifacts/research/process/20261004-ced-development')
contracts = json.loads((base / 't12-sol-handoff-20261007/p1-command-contracts.json').read_text())
branch, key = sys.argv[1:]
if branch == 'oc2':
    spec = contracts['round67-oc2-green-partials']
    out = base / 'astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007'
    if key == 'format_write':
        argv = ['.venv/bin/python', '-m', 'ruff', 'format', *spec['scope']['repair_allowlist']]
    else:
        argv = list(spec['verification'][key]['argv'])
    if key in ('full_GREEN', 'R03_regression'):
        argv.append('--junitxml=' + str(out / (key + '.junit.xml')))
else:
    spec = contracts['round71-rw1-static-format']
    out = base / 'astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/round71-static'
    argv = spec['verification']['commands'][key]['argv']
nonsecret = spec['verification']['env']
env = dict(os.environ)
env.update(nonsecret)
now = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
record = {'argv': argv, 'cwd': str(Path.cwd()), 'env': nonsecret, 'author': '/root/sol_t12_p1', 'runs': 1, 'started_at_utc': now()}
with (out / (key + '.command-start.json')).open('x') as f:
    json.dump(record, f, indent=2)
start = time.monotonic()
with (out / (key + '.stdout.txt')).open('xb') as stdout, (out / (key + '.stderr.txt')).open('xb') as stderr:
    process = subprocess.run(argv, env=env, stdout=stdout, stderr=stderr)
record.update(exit_code=process.returncode, ended_at_utc=now(), wall_s=time.monotonic()-start)
with (out / (key + '.command-result.json')).open('x') as f:
    json.dump(record, f, indent=2)
print(json.dumps(record))
print((out / (key + '.stdout.txt')).read_text()[-4500:])
print((out / (key + '.stderr.txt')).read_text()[-1500:])
sys.exit(process.returncode)
