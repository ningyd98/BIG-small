"""Execute one approved R76 command; never retry, overwrite receipts or hide RED."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

r = Path('artifacts/research/process/20261004-ced-development/astra-rounds/round76-rw1-lifecycle-evidence-20261007')
p = json.loads((r / 'plan.json').read_text())
o = Path(p['scope']['new_evidence_exclusive_root'])
key = sys.argv[1]
argv = p['verification'][key]
nonsecret = p['verification']['env']
env = dict(os.environ)
env.update(nonsecret)
now = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
receipt = {'argv': argv, 'cwd': str(Path.cwd()), 'env': nonsecret, 'author': '/root/sol_t12_p1', 'requested_model': 'gpt-6.1-sol', 'round': 76, 'runs': 1, 'started_at_utc': now()}
with (o / (key + '.command-start.json')).open('x') as stream:
    json.dump(receipt, stream, indent=2)
start = time.monotonic()
with (o / (key + '.stdout.txt')).open('xb') as stdout, (o / (key + '.stderr.txt')).open('xb') as stderr:
    process = subprocess.run(argv, env=env, stdout=stdout, stderr=stderr)
receipt.update(exit_code=process.returncode, ended_at_utc=now(), wall_s=time.monotonic()-start)
with (o / (key + '.command-result.json')).open('x') as stream:
    json.dump(receipt, stream, indent=2)
print(json.dumps(receipt))
print((o / (key + '.stdout.txt')).read_text()[-9000:])
print((o / (key + '.stderr.txt')).read_text()[-2000:])
sys.exit(process.returncode)
