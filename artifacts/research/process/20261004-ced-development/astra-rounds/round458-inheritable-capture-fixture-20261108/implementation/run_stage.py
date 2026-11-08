"""Run one fresh R458 stage; the preserved R457 failure is not a passing prerequisite."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
ROUND = Path(__file__).resolve().parents[1]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def pin(name):
    raw = (ROOT / name).read_bytes()
    return dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def run(stage):
    plan_path = ROUND / "plan.json"
    if hashlib.sha256(plan_path.read_bytes()).hexdigest() != "794275c2cd06e7ba72980d498b3f374885ae358ff776bdde294ac149f31b3858":
        raise ValueError("frozen plan changed")
    plan = json.loads(plan_path.read_text())
    stages = plan["verification_specs"]
    if stage not in stages:
        raise ValueError("undeclared stage")
    for name, spec in stages.items():
        if json.loads((ROUND / "spec-templates" / f"{name}.json").read_text()) != spec:
            raise ValueError("frozen spec changed")
    for name in list(stages)[:list(stages).index(stage)]:
        result = json.loads((ROUND / "validation" / name / "result.json").read_text())
        if result["returncode"] != 0 or result["remaining_live"] or result["source_drift"] or not result["reaped"]:
            raise ValueError("previous stage did not pass")
    rows = json.loads((ROUND / plan["input_pins"]).read_text())
    permitted = set(plan["format_implementation_commands"][1][2:])
    drift = [row["path"] for row in rows if pin(row["path"]) != {k: row[k] for k in ("path", "bytes", "sha256")} and row["path"] not in permitted]
    if drift:
        raise ValueError(f"unplanned source drift: {drift}")
    directory = Path(stages[stage]["directory"])
    directory.mkdir(parents=True, exist_ok=False)
    spec = stages[stage]
    for arg in spec["argv"]:
        if arg.startswith("--basetemp=") and Path(arg.split("=", 1)[1]).exists():
            raise ValueError("preserve prior basetemp")
    for key in ("TMPDIR", "XDG_CACHE_HOME", "BIGSMALL_R158_T2_RESOURCE_DIR", "BIGSMALL_R175_RESOURCE_DIR", "BIGSMALL_R223_RESOURCE_ROOT", "BIGSMALL_R223_CASE_ROOT", "DASHBOARD_ARTIFACT_ROOT"):
        Path(spec["env"][key]).mkdir(parents=True, exist_ok=True)
    names = {row["path"] for row in rows} | permitted
    names.update(str(p.relative_to(ROOT)) for p in (plan_path, ROUND / "plan.md", Path(__file__)))
    save(directory / "preflight/runtime-source-pins.json", {"files": [pin(name) for name in sorted(names)]})
    save(directory / "spec.json", spec)
    definition = importlib.util.spec_from_file_location("r458_supervisor", ROUND.parent / "round413-full-long-validation-20261103/bounded_stage.py")
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    module.ROUND = directory
    module.run(directory / "spec.json")
    result = json.loads((directory / "result.json").read_text())
    print(json.dumps({k: result.get(k) for k in ("state", "returncode", "reaped", "source_drift", "remaining_live")}))


if __name__ == "__main__":
    run(sys.argv[1])
