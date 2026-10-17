"""Single approved Round75 command; preserve exclusive original process evidence."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path('artifacts/research/process/20261004-ced-development/astra-rounds/round75-oc2-residual-type-20261007')
plan = json.loads((root / 'plan.json').read_text())
out = root / 'implementation'
key = sys.argv[1]
argv = plan['verification'][key]['argv']
nonsecret = plan['verification']['env']
env = dict(os.environ)
env.update(nonsecret)
now = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
receipt = {'argv': argv, 'cwd': str(Path.cwd()), 'env': nonsecret, 'author': '/root/sol_t12_p1', 'requested_model': 'gpt-6.1-sol', 'round': 75, 'runs': 1, 'started_at_utc': now()}
with (out / (key + '.command-start.json')).open('x') as stream:
    json.dump(receipt, stream, indent=2)
start = time.monotonic()
with (out / (key + '.stdout.txt')).open('xb') as stdout, (out / (key + '.stderr.txt')).open('xb') as stderr:
    process = subprocess.run(argv, env=env, stdout=stdout, stderr=stderr)
receipt.update(exit_code=process.returncode, ended_at_utc=now(), wall_s=time.monotonic()-start)
with (out / (key + '.command-result.json')).open('x') as stream:
    json.dump(receipt, stream, indent=2)
print(json.dumps(receipt))
print((out / (key + '.stdout.txt')).read_text()[-4500:])
print((out / (key + '.stderr.txt')).read_text()[-2000:])
sys.exit(process.returncode)
