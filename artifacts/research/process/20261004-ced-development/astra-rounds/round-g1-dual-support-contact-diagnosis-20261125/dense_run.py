"""Launch isolated fresh readers and require byte-identical products before publication."""

import json
import os
import subprocess
import sys
from pathlib import Path


def run(private):
    worker = Path(__file__).with_name("dense_readback.py")
    private.mkdir(parents=True, exist_ok=False)
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
    }
    children = []
    for name in ("one", "two"):
        stream = (private / (name + "-stdout.txt")).open("x")
        process = subprocess.Popen(
            [sys.executable, str(worker), str(private / name)],
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
        children.append((name, process, stream))
    checks = []
    for name, process, stream in children:
        rc = process.wait()
        stream.close()
        checks.append({"pid": process.pid, "exit_code": rc, "lane": name})
    with (private / "cold-reader-receipts.json").open("x") as f:
        json.dump(checks, f, sort_keys=True, indent=2)
    if any(r["exit_code"] for r in checks) or len({r["pid"] for r in checks}) != 2:
        raise ValueError("two independent readers did not finish")
    if (private / "one/seal.json").read_bytes() != (private / "two/seal.json").read_bytes():
        raise ValueError("signed reader byte outputs differ")


if __name__ == "__main__":
    run(Path(sys.argv[1]))
