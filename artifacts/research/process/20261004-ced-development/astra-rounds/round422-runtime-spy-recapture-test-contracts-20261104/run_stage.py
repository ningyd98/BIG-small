"""Run exactly one Astra-listed R422 stage with the frozen owned supervisor."""

from datetime import UTC, datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
ROUND = Path(__file__).resolve().parent
R413 = ROUND.parent / "round413-full-long-validation-20261103"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main():
    assert len(sys.argv) == 2, "one plan-listed stage ID required"
    manifest = json.loads((ROUND / "preflight/target-manifest.json").read_text())
    for item in manifest["frozen_drivers"]:
        raw = (ROOT / item["path"]).read_bytes()
        assert len(raw) == item["bytes"] and hashlib.sha256(raw).hexdigest() == item["sha256"]
    selected = [job for job in manifest["jobs"] if job["id"] == sys.argv[1]]
    assert len(selected) == 1, "unknown stage ID"
    job = selected[0]
    directory = ROUND / "validation" / job["id"]
    directory.mkdir(parents=True, exist_ok=False)
    basetemp = Path("/tmp") / ("bigsmall-r422-" + job["id"])
    assert not basetemp.exists() and not basetemp.is_symlink(), "existing basetemp; do not reuse"
    baseline = json.loads((ROUND / "preflight/runtime-source-baseline.json").read_text())["files"]
    pins = []
    for item in baseline:
        path = ROOT / item["path"]
        assert path.is_file() and not path.is_symlink()
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if item["path"] not in manifest["allowed_existing_test_changes"]:
            assert len(raw) == item["bytes"] and digest == item["sha256"], item["path"]
        pins.append({**item, "bytes": len(raw), "sha256": digest})
    new = ROOT / manifest["new_test"]
    raw = new.read_bytes()
    pins.append({"path": str(new.relative_to(ROOT)), "bytes": len(raw),
                 "sha256": hashlib.sha256(raw).hexdigest()})
    save(directory / "preflight/runtime-source-pins.json", {"files": pins})
    prior = json.loads((ROOT / job["source_spec"]).read_text())
    old = prior["directory"]
    first_node = prior["nodes"][0]
    assert first_node.startswith("tests/") and prior["argv"].count(first_node) == 1
    argv = prior["argv"][:prior["argv"].index(first_node)]
    argv = [arg.replace(old, str(directory)) for arg in argv]
    argv = ["--basetemp=" + str(basetemp) if arg.startswith("--basetemp=") else arg
            for arg in argv]
    assert argv[:3] == [str(ROOT / ".venv/bin/python"), "-m", "pytest"]
    argv.append(job["nodeid"])
    environment = {key: value.replace(old, str(directory)) for key, value in prior["env"].items()
                   if key != "SIMULATION_RUNTIME_DB"}
    environment["REAL_MOTION_DISPATCH_ENABLED"] = "false"
    for relative in prior["resource_dirs"]:
        (directory / relative).mkdir(parents=True, exist_ok=True)
    spec = {"id": job["id"], "directory": str(directory), "cwd": str(ROOT), "argv": argv,
            "env": environment, "nodes": [job["nodeid"]], "timeout_s": job["cap_seconds"],
            "ports": [], "created_utc": datetime.now(UTC).isoformat(),
            "source_spec": job["source_spec"], "plan_phase": job["phase"],
            "round_binding": "Imported frozen R413 supervisor reads only this stage's fresh pins."}
    spec_path = directory / "spec.json"
    save(spec_path, spec)
    module_spec = importlib.util.spec_from_file_location("r422_owned_supervisor", R413 / "bounded_stage.py")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    module.ROUND = directory
    module.run(spec_path)


if __name__ == "__main__":
    main()
