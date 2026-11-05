"""Execute each preregistered R437 stage once through the unchanged supervisor."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
ROUND = Path(__file__).resolve().parents[1]
BASE = ROUND.parent


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write("\n")


def pin(name):
    raw = (ROOT / name).read_bytes()
    return {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def run(stage):
    if stage not in {"red", "green", "diagnostic"}:
        raise ValueError("undeclared stage")
    plan = json.loads((ROUND / "plan.json").read_text())
    directory = ROUND / "validation" / stage
    directory.mkdir(parents=True, exist_ok=False)
    original = BASE / "round425-t7b-completion-kernel-20261104/validation/green/spec.json"
    template = json.loads(original.read_text())
    env = {
        key: value.replace(template["directory"], str(directory))
        for key, value in template["env"].items()
        if not key.startswith("R424_") and key != "SIMULATION_RUNTIME_DB"
    }
    for key in (
        "TMPDIR", "XDG_CACHE_HOME", "BIGSMALL_R158_T2_RESOURCE_DIR", "BIGSMALL_R175_RESOURCE_DIR",
        "BIGSMALL_R223_RESOURCE_ROOT", "BIGSMALL_R223_CASE_ROOT", "DASHBOARD_ARTIFACT_ROOT",
    ):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    basetemp = Path(f"/tmp/bigsmall-r437-{stage}")
    if basetemp.exists():
        raise ValueError("preserve previous stage directory")
    argv = list(plan["verification"][f"{stage}_argv"])
    argv[0] = str(ROOT / ".venv/bin/python")
    argv[4:4] = [
        "-p", "no:cacheprovider", "-p", "r413_events", "-p", "r235_startup_prerequisite",
        "--tb=short", f"--basetemp={basetemp}", f"--junitxml={directory / 'junit.xml'}",
    ]
    baseline = json.loads((BASE / "round435-t7b-guarded-execution-20261105/implementation/baseline.json").read_text())["files"]
    originals = {row["path"]: row for row in baseline + plan["input_pins"]}
    permitted = set(plan["allowed_source_edits"] + plan["allowed_test_edits"])
    drift = [name for name, row in originals.items() if pin(name) != row and name not in permitted]
    if drift:
        raise ValueError(f"unplanned source drift: {drift}")
    current = {name: pin(name) for name in originals}
    for name in permitted:
        if (ROOT / name).exists():
            current[name] = pin(name)
    for path in (ROUND / "plan.md", ROUND / "plan.json", Path(__file__)):
        name = str(path.relative_to(ROOT))
        current[name] = pin(name)
    save(directory / "preflight/runtime-source-pins.json", {"files": list(current.values())})
    save(directory / "preflight/generation.json", {
        "baseline": "../round435-t7b-guarded-execution-20261105/implementation/baseline.json", "original_pin_count": len(originals),
        "changed": [name for name, row in originals.items() if current[name] != row],
        "unplanned_drift": drift,
    })
    spec = dict(
        id=f"r437-{stage}", directory=str(directory), cwd=str(ROOT), argv=argv, env=env,
        nodes=[arg for arg in argv if arg.startswith("tests/")], ports=[],
        timeout_s=plan["verification"]["timeouts_seconds"][stage], attempt=1,
        scope="R437_GUARDED_EXECUTION_DIAGNOSTIC_ONLY",
    )
    save(directory / "spec.json", spec)
    supervisor_path = BASE / "round413-full-long-validation-20261103/bounded_stage.py"
    module_spec = importlib.util.spec_from_file_location("r437_bounded", supervisor_path)
    supervisor = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(supervisor)
    supervisor.ROUND = directory
    supervisor.run(directory / "spec.json")


if __name__ == "__main__":
    run(sys.argv[1])
