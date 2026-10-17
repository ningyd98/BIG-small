from pathlib import Path
from datetime import datetime, UTC
import hashlib
import json
import os
import subprocess
import sys
base = Path(__file__).resolve().parent
key = sys.argv[1]
ledger_path = base / "command-ledger.json"
ledger = json.loads(ledger_path.read_text())
command = ledger["commands"][key]
assert command["used"] == 0 and command["remaining"] == 1
out = Path(command["evidence_dir"])
out.mkdir(parents=True, exist_ok=False)
command.update(used=1, remaining=0, status="SPENT_BEFORE_INVOCATION", started_utc=datetime.now(UTC).isoformat())
ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
(out / "invocation.json").write_text(json.dumps(command, ensure_ascii=False, indent=2) + "\n")
env = os.environ.copy()
env.update(command["env"])
with (out / "stdout.txt").open("wb") as stdout, (out / "stderr.txt").open("wb") as stderr:
    result = subprocess.run(command["argv"], cwd=command["cwd"], env=env, stdout=stdout, stderr=stderr)
command.update(status="COMPLETED", exit_code=result.returncode, ended_utc=datetime.now(UTC).isoformat())
command["raw_outputs"] = {name:{"bytes":(out/name).stat().st_size,"sha256":hashlib.sha256((out/name).read_bytes()).hexdigest()} for name in ("stdout.txt","stderr.txt")}
ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
(out / "result.json").write_text(json.dumps(command, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"command":key,"exit":result.returncode,"evidence":str(out)}))
