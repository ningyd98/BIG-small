"""Execute one immutable R457 CPU validation stage with a fresh directory."""
import hashlib
import importlib.util
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
ROUND = Path(__file__).resolve().parents[1]


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def pin(name):
    data = (ROOT / name).read_bytes()
    return {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def run(stage):
    plan_path = ROUND / "plan.json"
    if hashlib.sha256(plan_path.read_bytes()).hexdigest() != "bc611e12528c0dc818fb98489dc6b4faf3108988bcb7d3c76a81d356f29876ec":
        raise ValueError("R457 plan changed")
    plan = json.loads(plan_path.read_text())
    stages = plan["verification_specs"]
    if stage not in stages:
        raise ValueError("undeclared stage")
    for name, spec in stages.items():
        if json.loads((ROUND / "spec-templates" / f"{name}.json").read_text()) != spec:
            raise ValueError("frozen specification changed")
    for name in list(stages)[:list(stages).index(stage)]:
        result = json.loads((ROUND / "validation" / name / "result.json").read_text())
        if result["returncode"] != (1 if name == "sol-red" else 0) or result["remaining_live"] or result["source_drift"] or not result["reaped"]:
            raise ValueError("previous stage did not pass")
        if name == "sol-red":
            cases = ET.parse(ROUND / "validation" / name / "junit.xml").findall(".//testcase")
            if len(cases) != 8 or any(c.find("failure") is None or "R457 Sol request policy missing" not in c.find("failure").text for c in cases):
                raise ValueError("RED differs from declared missing policy")
    rows = json.loads((ROUND / plan["input_pins"]).read_text())
    permitted = set(plan["allowed_edits"] + plan["allowed_new_tests"])
    drift = [row["path"] for row in rows if pin(row["path"]) != {k: row[k] for k in ("path", "bytes", "sha256")} and (stage == "sol-red" or row["path"] not in permitted)]
    if drift:
        raise ValueError(f"unplanned input drift: {drift}")
    spec = stages[stage]
    directory = Path(spec["directory"])
    directory.mkdir(parents=True, exist_ok=False)
    for arg in spec["argv"]:
        if arg.startswith("--basetemp=") and Path(arg.split("=", 1)[1]).exists():
            raise ValueError("preserve previous basetemp")
    for key in ("TMPDIR", "XDG_CACHE_HOME", "BIGSMALL_R158_T2_RESOURCE_DIR", "BIGSMALL_R175_RESOURCE_DIR", "BIGSMALL_R223_RESOURCE_ROOT", "BIGSMALL_R223_CASE_ROOT", "DASHBOARD_ARTIFACT_ROOT"):
        Path(spec["env"][key]).mkdir(parents=True, exist_ok=True)
    names = {row["path"] for row in rows} | permitted
    names.update(str(path.relative_to(ROOT)) for path in (plan_path, ROUND / "plan.md", Path(__file__)))
    save(directory / "preflight/runtime-source-pins.json", {"files": [pin(name) for name in sorted(names)]})
    save(directory / "spec.json", spec)
    definition = importlib.util.spec_from_file_location("r457_supervisor", ROUND.parent / "round413-full-long-validation-20261103/bounded_stage.py")
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    module.ROUND = directory
    module.run(directory / "spec.json")
    result = json.loads((directory / "result.json").read_text())
    print(json.dumps({k: result.get(k) for k in ("state", "returncode", "reaped", "remaining_live", "source_drift")}))


if __name__ == "__main__":
    run(sys.argv[1])
