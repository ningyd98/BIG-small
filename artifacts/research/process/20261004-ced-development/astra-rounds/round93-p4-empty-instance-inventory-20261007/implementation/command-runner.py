import json, os, subprocess, sys, time
from datetime import UTC, datetime
from pathlib import Path
round_root = Path(__file__).resolve().parent.parent
out = round_root / "implementation"
plan = json.loads((round_root / "plan.json").read_text())
name = sys.argv[1]
argv = plan["verification"]["commands"][name]["argv"] if name != "proof" else [".venv/bin/python", str(out / "scope-proof.py")]
env_changes = plan["verification"]["environment"]
env = os.environ.copy(); env.update(env_changes)
start = datetime.now(UTC).isoformat(); stamp = time.monotonic()
with (out / (name + ".command-start.json")).open("x") as file:
    json.dump({"argv": argv, "cwd": str(Path.cwd()), "environment": env_changes, "start_utc": start}, file, indent=2)
with (out / (name + ".stdout.txt")).open("xb") as stdout, (out / (name + ".stderr.txt")).open("xb") as stderr:
    result = subprocess.run(argv, env=env, stdout=stdout, stderr=stderr)
receipt = {"start_utc": start, "end_utc": datetime.now(UTC).isoformat(), "wall_seconds": time.monotonic() - stamp, "exit_code": result.returncode}
with (out / (name + ".command-result.json")).open("x") as file:
    json.dump(receipt, file, indent=2)
print(json.dumps(receipt)); print((out / (name + ".stdout.txt")).read_text()[-12000:]); print((out / (name + ".stderr.txt")).read_text()[-3000:])
sys.exit(result.returncode)
