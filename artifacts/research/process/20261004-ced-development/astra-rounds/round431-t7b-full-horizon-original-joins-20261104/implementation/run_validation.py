"""Two R431 declared CPU stages, using the unchanged R413 bounded supervisor."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
ROUND = Path(__file__).resolve().parents[1]
BASE = ROUND.parent
NEW = (
    "src/cloud_edge_robot_arm/vision/native_completion_horizon.py",
    "src/cloud_edge_robot_arm/research/native_completion_horizon_originals.py",
    "tests/test_native_completion_horizon_v1.py",
    "tests/test_native_completion_horizon_originals_v1.py",
)


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def run(stage):
    if stage not in {"red", "green"}:
        raise ValueError("only the two frozen stages are declared")
    plan = json.loads((ROUND / "plan.json").read_text())
    directory = ROUND / "validation" / stage
    directory.mkdir(parents=True, exist_ok=False)
    original = BASE / "round425-t7b-completion-kernel-20261104"
    spec = json.loads((original / "validation/green/spec.json").read_text())
    old_directory = spec["directory"]
    env = {
        key: value.replace(old_directory, str(directory))
        for key, value in spec["env"].items()
        if not key.startswith("R424_")
    }
    env.pop("SIMULATION_RUNTIME_DB", None)
    for key in (
        "TMPDIR",
        "XDG_CACHE_HOME",
        "BIGSMALL_R158_T2_RESOURCE_DIR",
        "BIGSMALL_R175_RESOURCE_DIR",
        "BIGSMALL_R223_RESOURCE_ROOT",
        "BIGSMALL_R223_CASE_ROOT",
        "DASHBOARD_ARTIFACT_ROOT",
    ):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    basetemp = Path(f"/tmp/bigsmall-r431-{stage}")
    if basetemp.exists():
        raise ValueError("new stage basetemp already exists; preserve it")
    argv = list(plan["verification"][f"{stage}_argv"])
    argv[0] = str(ROOT / ".venv/bin/python")
    argv[4:4] = [
        "-p",
        "no:cacheprovider",
        "-p",
        "r413_events",
        "-p",
        "r235_startup_prerequisite",
        "--tb=short",
        f"--basetemp={basetemp}",
        f"--junitxml={directory / 'junit.xml'}",
    ]
    baseline = json.loads(
        (
            BASE / "round429-t7b-full-horizon-evidence-20261104/intake/runtime-source-baseline.json"
        ).read_text()
    )
    mutable = set(plan["allowed_source_modifications"])
    assert not mutable & {row["path"] for row in baseline["files"]}
    pins = baseline["files"] + [row for row in plan["input_pins"] if row["path"] not in mutable]
    required_new = NEW
    for name in (
        *required_new,
        str(Path(__file__).relative_to(ROOT)),
        str((ROUND / "plan.md").relative_to(ROOT)),
        str((ROUND / "plan.json").relative_to(ROOT)),
    ):
        raw = (ROOT / name).read_bytes()
        pins.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    phase = [row for row in pins if row["path"] in mutable]
    save(
        directory / "preflight/phase-source-pins.json",
        {
            "files": phase,
            "authorization": "R431 input preimages preserved; current phase pins appended, baseline unchanged",
        },
    )
    by_path = {}
    for row in pins:
        if row["path"] in by_path and row != by_path[row["path"]]:
            raise ValueError("inconsistent frozen input pin")
        by_path[row["path"]] = row
    save(directory / "preflight/runtime-source-pins.json", {"files": list(by_path.values())})
    nodes = [arg for arg in argv if arg.startswith("tests/")]
    spec = dict(
        id=f"r431-{stage}",
        directory=str(directory),
        cwd=str(ROOT),
        argv=argv,
        env=env,
        nodes=nodes,
        ports=[],
        timeout_s=600,
        attempt=1,
        scope="R431_CPU_RATIONAL_FULL_HORIZON_ONLY",
    )
    save(directory / "spec.json", spec)
    supervisor_path = BASE / "round413-full-long-validation-20261103/bounded_stage.py"
    module_spec = importlib.util.spec_from_file_location("r431_bounded", supervisor_path)
    supervisor = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(supervisor)
    supervisor.ROUND = directory
    supervisor.run(directory / "spec.json")


if __name__ == "__main__":
    run(sys.argv[1])
