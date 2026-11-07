"""One R443 canonical-protocol CPU validation, preserving the R439 failure."""
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
    if stage != "t2-repair-green":
        raise ValueError("undeclared stage")
    spec = plan["verification"]["spec_template"]
    directory = Path(spec["directory"])
    directory.mkdir(parents=True, exist_ok=False)
    if Path("/tmp/bigsmall-r443-t2-repair-green").exists():
        raise ValueError("preserve old basetemp")
    for key in ("TMPDIR", "XDG_CACHE_HOME", "BIGSMALL_R158_T2_RESOURCE_DIR", "BIGSMALL_R175_RESOURCE_DIR",
                "BIGSMALL_R223_RESOURCE_ROOT", "BIGSMALL_R223_CASE_ROOT", "DASHBOARD_ARTIFACT_ROOT"):
        Path(spec["env"][key]).mkdir(parents=True, exist_ok=True)
    source = BASE / "round439-full-execution-independent-calibration-20261107"
    original = json.loads((source / "plan.json").read_text())
    baseline = json.loads((source / "implementation/baseline.json").read_text())["files"]
    allowed = set(original["allowed_source_edits"] + original["allowed_new_products"] + original["allowed_new_tests"])
    current = {row["path"]: pin(row["path"]) for row in baseline}
    drift = [row["path"] for row in baseline if current[row["path"]] != row and row["path"] not in allowed]
    if drift:
        raise ValueError(drift)
    for name in allowed:
        if (ROOT / name).exists():
            current[name] = pin(name)
    for path in (ROUND / "plan.json", ROUND / "plan.md", Path(__file__)):
        name = str(path.relative_to(ROOT))
        current[name] = pin(name)
    save(ROUND / "implementation/commands.json", {stage: spec})
    save(directory / "preflight/runtime-source-pins.json", dict(files=list(current.values())))
    save(directory / "preflight/generation.json", dict(unplanned_drift=drift))
    save(directory / "spec.json", spec)
    module_spec = importlib.util.spec_from_file_location("bounded_r443", BASE / "round413-full-long-validation-20261103/bounded_stage.py")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    module.ROUND = directory
    module.run(directory / "spec.json")


if __name__ == "__main__":
    run(sys.argv[1])
