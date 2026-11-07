"""Run one preregistered R439 stage through the unchanged R413 supervisor."""

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
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def pin(name):
    raw = (ROOT / name).read_bytes()
    return dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def run(stage):
    plan = json.loads((ROUND / "plan.json").read_text())
    commands = dict(plan["verification"])
    overlay_path = BASE / "round440-collection-asset-registration-20261107/plan.json"
    overlay = json.loads(overlay_path.read_text())
    commands.update(overlay["verification_overlay"])
    static = commands.pop("static")
    for name, argv in zip(("ruff", "format", "mypy"), static["argvs"], strict=True):
        commands[name] = dict(argv=argv, timeout_s=static["timeout_s_each"], max_runs=1)
    if stage not in commands:
        raise ValueError("undeclared stage")
    command_path = ROUND / "implementation/commands-r440.json"
    if not command_path.exists():
        save(command_path, commands)
    if json.loads(command_path.read_text()) != commands:
        raise ValueError("declared commands changed")
    directory = ROUND / "validation" / stage
    directory.mkdir(parents=True, exist_ok=False)
    template = json.loads((BASE / "round425-t7b-completion-kernel-20261104/validation/green/spec.json").read_text())
    env = {key: value.replace(template["directory"], str(directory))
           for key, value in template["env"].items()
           if not key.startswith("R424_") and key != "SIMULATION_RUNTIME_DB"}
    for key in ("TMPDIR", "XDG_CACHE_HOME", "BIGSMALL_R158_T2_RESOURCE_DIR",
                "BIGSMALL_R175_RESOURCE_DIR", "BIGSMALL_R223_RESOURCE_ROOT",
                "BIGSMALL_R223_CASE_ROOT", "DASHBOARD_ARTIFACT_ROOT"):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    argv = list(commands[stage]["argv"])
    argv[0] = str(ROOT / argv[0])
    if argv[1:3] == ["-m", "pytest"]:
        basetemp = Path(f"/tmp/bigsmall-r439-{stage}")
        if basetemp.exists():
            raise ValueError("preserve previous stage directory")
        argv[4:4] = ["-p", "no:cacheprovider", "-p", "r413_events", "-p", "r235_startup_prerequisite",
                     "--tb=short", f"--basetemp={basetemp}", f"--junitxml={directory / 'junit.xml'}"]
    baseline = json.loads((ROUND / "implementation/baseline.json").read_text())["files"]
    originals = {row["path"]: row for row in baseline + plan["input_pins"]}
    allowed = set(plan["allowed_source_edits"] + plan["allowed_new_products"] + plan["allowed_new_tests"])
    drift = [name for name, row in originals.items() if pin(name) != row and name not in allowed]
    if drift:
        raise ValueError(f"unplanned source drift: {drift}")
    current = {name: pin(name) for name in originals}
    for name in allowed:
        if (ROOT / name).exists():
            current[name] = pin(name)
    for path in (ROUND / "plan.md", ROUND / "plan.json", overlay_path,
                 overlay_path.with_suffix(".md"), Path(__file__), command_path,
                 BASE / "round441-teacher-collection-admission-20261107/plan.json",
                 BASE / "round441-teacher-collection-admission-20261107/plan.md",
                 BASE / "round442-collection-raw-identity-20261107/plan.json",
                 BASE / "round442-collection-raw-identity-20261107/plan.md",
                 BASE / "round442-collection-raw-identity-20261107/addendum.json",
                 BASE / "round442-collection-raw-identity-20261107/addendum.md",
                 BASE / "round443-collection-protocol-roundtrip-20261107/plan.json",
                 BASE / "round443-collection-protocol-roundtrip-20261107/plan.md",
                 BASE / "round444-collection-source-closure-20261107/plan.json",
                 BASE / "round444-collection-source-closure-20261107/plan.md",
                 BASE / "round445-release-reference-frame-20261107/plan.json",
                 BASE / "round445-release-reference-frame-20261107/plan.md",
                 BASE / "round446-original-registration-frame-order-20261107/plan.md",
                 BASE / "round446-original-registration-frame-order-20261107/plan.json",
                 BASE / "round446-original-registration-frame-order-20261107/addendum.md",
                 BASE / "round446-original-registration-frame-order-20261107/addendum.json",
                 BASE / "round446-original-registration-frame-order-20261107/applicability.md",
                 BASE / "round446-original-registration-frame-order-20261107/applicability.json"):
        name = str(path.relative_to(ROOT))
        current[name] = pin(name)
    save(directory / "preflight/runtime-source-pins.json", dict(files=list(current.values())))
    save(directory / "preflight/generation.json", dict(original_pin_count=len(originals),
         changed=[name for name, row in originals.items() if current[name] != row],
         unplanned_drift=drift))
    save(directory / "spec.json", dict(id=f"r439-{stage}", directory=str(directory), cwd=str(ROOT),
         argv=argv, env=env, nodes=[arg for arg in argv if arg.startswith("tests/")], ports=[],
         timeout_s=commands[stage]["timeout_s"], attempt=1, scope="R439_TEACHER_COLLECTION_ONLY"))
    supervisor_path = BASE / "round413-full-long-validation-20261103/bounded_stage.py"
    spec = importlib.util.spec_from_file_location("r439_bounded", supervisor_path)
    supervisor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(supervisor)
    supervisor.ROUND = directory
    supervisor.run(directory / "spec.json")


if __name__ == "__main__":
    run(sys.argv[1])
