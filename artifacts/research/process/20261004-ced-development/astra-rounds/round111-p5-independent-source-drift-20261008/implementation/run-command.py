from pathlib import Path
from datetime import UTC, datetime
import hashlib
import json
import os
import subprocess
import sys

name, *argv = sys.argv[1:]
root = Path.cwd()
base = root / "artifacts/research/process/20261004-ced-development/astra-rounds/round111-p5-independent-source-drift-20261008/implementation"
output = base / name
output.mkdir(exist_ok=False)
start = {"name": name, "argv": argv, "cwd": str(root), "start_utc": datetime.now(UTC).isoformat(), "env": {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "src:."}}
(output / "command-start.json").write_text(json.dumps(start, indent=2) + "\n")
env = dict(os.environ, **start["env"])
with (output / "stdout.txt").open("xb") as stdout, (output / "stderr.txt").open("xb") as stderr:
    child = subprocess.run(argv, cwd=root, env=env, stdout=stdout, stderr=stderr)
result = {**start, "end_utc": datetime.now(UTC).isoformat(), "exit_code": child.returncode}
for filename in ("stdout.txt", "stderr.txt"):
    data = (output / filename).read_bytes()
    result[filename] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
(output / "command-result.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
sys.exit(child.returncode)
