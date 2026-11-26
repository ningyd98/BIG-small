"""Launch two independent cold readers with separately attested recovery entry code."""

import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(path for path in HERE.parents if (path / ".git").exists())
PLAN_PATH = HERE / "entry-plan.json"
PLAN = json.loads(PLAN_PATH.read_bytes())
PARENT = REPO / PLAN["private_parent"]
OUT = PARENT / "double-manifest-01"
TREE = REPO / PLAN["runtime_tree"]


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def main():
    for rel, expected in PLAN["registered_pins"].items():
        require(digest(REPO / rel) == expected, f"registered original changed: {rel}")
    require(not OUT.exists() and OUT.resolve() == OUT, "cold allocation already consumed")
    out = OUT / "registration.json"
    body = HERE / "entry_body.py"
    code = body.read_bytes()
    wrapper = HERE / "recover_score.py"
    lock = TREE / "runtime-build.json"
    source_map = json.loads(lock.read_bytes())["runtime_files_sha256"]
    require(digest(lock) == TREE.parent.name, "foreign frozen runtime")
    OUT.mkdir()
    with (OUT / "diagnostic.json").open("xb") as stream:
        stream.write((PARENT / "diagnostic.json").read_bytes())
    registry = {
        "repo": str(REPO),
        "runtime_tree": str(TREE),
        "runtime_sha256": digest(lock),
        "interpreter": sys.executable,
        "plan_sha256": digest(PLAN_PATH),
        "supervisor_path": str(HERE / "launch_recovery.py"),
        "supervisor_sha256": digest(HERE / "launch_recovery.py"),
        "inline_source_path": str(body),
        "inline_launch_sha256": sha256(code).hexdigest(),
        "wrapper_path": str(wrapper),
        "wrapper_sha256": digest(wrapper),
        "wrapper_module_name": PLAN["entry_module_name"],
        "frozen_scorer_sha256": source_map["scripts/graduation/g1_clearance_score.py"],
        "frozen_observer_sha256": source_map["scripts/graduation/g1_dual_observer.py"],
        "prior_failure_sha256": {f"reader-{i}": digest(PARENT / f"reader-{i}.log") for i in (1, 2)},
    }
    with out.open("x") as f:
        json.dump(registry, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    env = dict(
        os.environ,
        PYTHONPATH=f"{TREE}:{TREE / 'src'}",
        PYTHONNOUSERSITE="1",
        PYTHONDONTWRITEBYTECODE="1",
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
    )
    results = []
    audits = []
    for slot in ("reader-1", "reader-2"):
        with (OUT / f"{slot}.log").open("x") as log:
            status = subprocess.run(
                [sys.executable, "-B", "-c", code.decode(), str(out), digest(out), slot],
                cwd=TREE,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        require(status.returncode == 0, f"{slot} failed with {status.returncode}")
        result = OUT / slot / "result.json"
        audit = json.loads((OUT / slot / "external-source-audit.json").read_bytes())
        require(
            audit["result_sha256"] == digest(result) and audit["registry_sha256"] == digest(out),
            "cold result or external registry differed",
        )
        results.append(result)
        audits.append(audit)
    first, second = audits
    require(
        first["pid"] != second["pid"]
        and first["project_audit_sha256"] == second["project_audit_sha256"]
        and first["external_local_imports"] == second["external_local_imports"]
        and results[0].read_bytes() == results[1].read_bytes(),
        "independent score or either source manifest differs",
    )
    print(digest(results[0]))


if __name__ == "__main__":
    main()
