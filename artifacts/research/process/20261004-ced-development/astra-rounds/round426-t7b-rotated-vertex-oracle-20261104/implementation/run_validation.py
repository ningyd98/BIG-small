"""Fresh R426 stage from the frozen R425 spec and unchanged R413 supervisor."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
ROUND = Path(__file__).resolve().parents[1]
BASE = ROUND.parent
PRIOR = BASE / "round425-t7b-completion-kernel-20261104"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def run():
    plan = json.loads((ROUND / "plan.json").read_text())
    directory = ROUND / "validation/green"
    directory.mkdir(parents=True, exist_ok=False)
    old = PRIOR / "validation/green"
    spec = json.loads((old / "spec.json").read_text())
    spec["env"] = {key: value.replace(str(old), str(directory)) for key, value in spec["env"].items()}
    for key in (
        "TMPDIR", "XDG_CACHE_HOME", "BIGSMALL_R158_T2_RESOURCE_DIR",
        "BIGSMALL_R175_RESOURCE_DIR", "BIGSMALL_R223_RESOURCE_ROOT", "BIGSMALL_R223_CASE_ROOT",
        "DASHBOARD_ARTIFACT_ROOT",
    ):
        Path(spec["env"][key]).mkdir(parents=True, exist_ok=True)
    basetemp = Path("/tmp/bigsmall-r426-green")
    if basetemp.exists():
        raise ValueError("fresh basetemp required; existing files preserved")
    argv = plan["verification"]["green_argv"]
    argv[0] = str(ROOT / ".venv/bin/python")
    argv[4:4] = ["-p", "no:cacheprovider", "-p", "r413_events", "-p", "r235_startup_prerequisite",
                "--tb=short", f"--basetemp={basetemp}"]
    spec.update(id="r426-green", directory=str(directory), argv=argv, scope="R426_CPU_ORACLE_CORRECTION")
    pins = json.loads((old / "preflight/runtime-source-pins.json").read_text())["files"]
    by_path = {pin["path"]: pin for pin in pins}
    changed = "tests/test_native_completion_v2.py"
    for pin in plan["input_pins"]:
        if pin["path"] != changed:
            by_path[pin["path"]] = pin
    for name in (changed, str(Path(__file__).relative_to(ROOT)),
                 str((ROUND / "plan.md").relative_to(ROOT)), str((ROUND / "plan.json").relative_to(ROOT))):
        raw = (ROOT / name).read_bytes()
        by_path[name] = {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    save(directory / "preflight/runtime-source-pins.json", {"files": list(by_path.values())})
    save(directory / "spec.json", spec)
    path = BASE / "round413-full-long-validation-20261103/bounded_stage.py"
    module_spec = importlib.util.spec_from_file_location("r426_bounded", path)
    supervisor = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(supervisor)
    supervisor.ROUND = directory
    supervisor.run(directory / "spec.json")


if __name__ == "__main__":
    run()
