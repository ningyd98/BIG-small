"""Execute exactly one Round74 approved command with exclusive complete receipts."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path('artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007')
plan = json.loads((root / 'plan.json').read_text())
out = root / 'implementation'
key = sys.argv[1]
argv = list(plan['verification'][key]['argv'])
if key == 'R03_regression':
    argv.append('--junitxml=' + str(out / 'R03_regression.junit.xml'))
nonsecret = plan['verification']['env']
env = dict(os.environ)
env.update(nonsecret)
now = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
receipt = {'argv': argv, 'cwd': str(Path.cwd()), 'env': nonsecret, 'author': '/root/sol_t12_p1', 'runs': 1, 'started_at_utc': now(), 'round': 74}
with (out / (key + '.command-start.json')).open('x') as stream:
    json.dump(receipt, stream, indent=2)
start = time.monotonic()
with (out / (key + '.stdout.txt')).open('xb') as stdout, (out / (key + '.stderr.txt')).open('xb') as stderr:
    process = subprocess.run(argv, env=env, stdout=stdout, stderr=stderr)
receipt.update(exit_code=process.returncode, ended_at_utc=now(), wall_s=time.monotonic()-start)
with (out / (key + '.command-result.json')).open('x') as stream:
    json.dump(receipt, stream, indent=2)
print(json.dumps(receipt))
print((out / (key + '.stdout.txt')).read_text()[-5000:])
print((out / (key + '.stderr.txt')).read_text()[-2000:])
sys.exit(process.returncode)
