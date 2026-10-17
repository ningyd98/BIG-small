"""One allowlisted command, persistent original receipts, fail closed."""
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

out = Path(__file__).resolve().parent
plan = json.loads((out.parent / "plan.json").read_text())
order = ["scope_proof", "ruff_check", "format_check", "mypy", "GREEN"]
if len(sys.argv) != 2 or sys.argv[1] not in order:
    raise SystemExit("exactly one allowlisted command required")
name = sys.argv[1]
position = order.index(name)
if position:
    previous = json.loads((out / (order[position - 1] + ".command-result.json")).read_text())
    if previous["exit_code"] != 0:
        raise SystemExit("previous child result failed; no next command")
if position:
    proof = json.loads((out / "local-import-proof.json").read_text())
    if proof["status"] != "PASS" or not proof["reused_R94_proof_verified"]:
        raise SystemExit("proof acceptance missing")
argv = next(row["argv"] for row in plan["commands"] if row["name"] == name)
env_changes = {"PYTHONPATH": "src:.", "MYPYPATH": "src", "PYTHONDONTWRITEBYTECODE": "1"}
env = os.environ.copy(); env.update(env_changes)
start = datetime.now(UTC).isoformat(); stamp = time.monotonic()
with (out / (name + ".command-start.json")).open("x") as file:
    json.dump({"argv": argv, "cwd": str(Path.cwd()), "environment": env_changes, "start_utc": start}, file, indent=2)
with (out / (name + ".stdout.txt")).open("xb") as stdout, (out / (name + ".stderr.txt")).open("xb") as stderr:
    try:
        child = subprocess.run(argv, env=env, stdout=stdout, stderr=stderr)
        code = child.returncode
        launch_error = None
    except Exception as error:
        code = 1
        launch_error = {"type": type(error).__name__, "message": str(error)}
        stderr.write((json.dumps(launch_error) + "\n").encode())
receipt = {"start_utc": start, "end_utc": datetime.now(UTC).isoformat(), "wall_seconds": time.monotonic() - stamp,
           "exit_code": code, "launch_error": launch_error}
with (out / (name + ".command-result.json")).open("x") as file:
    json.dump(receipt, file, indent=2)
print(json.dumps(receipt)); print((out / (name + ".stdout.txt")).read_text()[-16000:]); print((out / (name + ".stderr.txt")).read_text()[-6000:])
sys.exit(code)
