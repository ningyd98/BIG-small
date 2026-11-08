"""R465 derivative of the pinned R461 runner, using the unchanged R413 supervisor."""

import hashlib
import importlib.util
import json
import os
import resource
import shutil
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
ROUND = Path(__file__).resolve().parents[1]
PLAN_SHA = "0337781ac796562e4c8ed3dbf166c043ffbdd7f31e185a13c9a6db6c44adeacd"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def pin(name):
    raw = (ROOT / name).read_bytes()
    return dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def phase_sources(stage):
    name = "red-source-ready" if stage == "reader-red" else "source-ready"
    path = ROUND / "implementation" / f"{name}.json"
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != path.with_suffix(".sha256").read_text().strip():
        raise ValueError("fixed phase source manifest hash changed")
    manifest = json.loads(raw)
    for row in manifest["files"]:
        if pin(row["path"]) != row:
            raise ValueError(f"fixed source drift: {row['path']}")
    files = manifest["files"] + [pin(str(path.relative_to(ROOT))), pin(str(path.with_suffix(".sha256").relative_to(ROOT)))]
    return manifest, files


def events_for(directory):
    return [json.loads(line) for line in (directory / "pytest-events.jsonl").read_text().splitlines()]


def assess_red(directory, manifest):
    events = events_for(directory)
    calls = [e for e in events if e["event"] == "report" and e["when"] == "call"]
    collection = [e for e in events if e["event"] == "collection_finished"]
    node = "tests/test_sol_evidence_reader.py::test_recorded_generation_gate_rejects_effective_field_drift"
    other_errors = [e for e in events if e["event"] == "report" and e["when"] != "call" and e["outcome"] != "passed"]
    detail = calls[0].get("longrepr") or "" if calls else ""
    accepted = (len(calls) == 1 and calls[0]["nodeid"] == node and calls[0]["outcome"] == "failed"
        and "DID NOT RAISE" in detail and "<class 'ValueError'>" in detail
        and f"test_sol_evidence_reader.py:{manifest['trigger_line']}" in detail
        and len(collection) == 1 and collection[0]["collection_errors"] == 0
        and collection[0]["nodeids"] == [node] and not other_errors)
    return {"expected_red": accepted, "node": node, "trigger_line": manifest["trigger_line"],
        "trigger": "first PLANNER frozen int1 / wire True", "other_errors": other_errors,
        "not_reached": ["float alias", "SUPERVISOR aliases", "nominal aliases", "CED aliases"]}


def healthy(directory, red=False):
    result = json.loads((directory / "result.json").read_text())
    budget = json.loads((directory / "resource-budget.json").read_text())
    ok = (result["state"] == "FINISHED" and result["returncode"] == (1 if red else 0)
        and result["reaped"] and all(not result[k] for k in ("source_drift", "remaining_live", "errors", "cancellations"))
        and budget["accepted"])
    if red:
        ok = ok and json.loads((directory / "expected-red-assessment.json").read_text())["expected_red"]
    if not ok:
        raise ValueError("stage did not meet frozen gates; stop and request actual Astra")


def basetemp(spec):
    return next((Path(a.split("=", 1)[1]) for a in spec["argv"] if a.startswith("--basetemp=")), None)


def usage():
    value = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {"user_s": value.ru_utime, "system_s": value.ru_stime, "maxrss_kib": value.ru_maxrss}


def disk_inventory(roots):
    rows, seen = [], set()
    for root in roots:
        if not root.exists():
            continue
        for directory, folders, files in os.walk(root, followlinks=False):
            folders[:] = [name for name in folders if not (Path(directory) / name).is_symlink()]
            for name in files:
                path = Path(directory) / name
                if path.is_symlink() or not path.is_file():
                    continue
                stat = path.stat()
                identity = stat.st_dev, stat.st_ino
                if identity in seen:
                    continue
                seen.add(identity)
                rows.append({"path": str(path), "bytes": stat.st_size})
    return rows


def run(stage):
    plan_path = ROUND / "plan.json"
    if hashlib.sha256(plan_path.read_bytes()).hexdigest() != PLAN_SHA:
        raise ValueError("frozen plan changed")
    plan = json.loads(plan_path.read_text())
    stages = plan["verification_specs"]
    if stage not in stages:
        raise ValueError("undeclared stage")
    for name, spec in stages.items():
        if json.loads((ROUND / "spec-templates" / f"{name}.json").read_text()) != spec:
            raise ValueError("frozen stage spec changed")
    for previous in list(stages)[:list(stages).index(stage)]:
        healthy(ROUND / "validation" / previous, red=previous == "reader-red")
    manifest, files = phase_sources(stage)
    spec = stages[stage]
    directory = Path(spec["directory"])
    temporary = basetemp(spec)
    if temporary is not None and temporary.exists():
        raise ValueError("preserve prior basetemp")
    directory.mkdir(parents=True, exist_ok=False)
    for key in ("TMPDIR", "XDG_CACHE_HOME", "BIGSMALL_R158_T2_RESOURCE_DIR", "BIGSMALL_R175_RESOURCE_DIR", "BIGSMALL_R223_RESOURCE_ROOT", "BIGSMALL_R223_CASE_ROOT", "DASHBOARD_ARTIFACT_ROOT"):
        Path(spec["env"][key]).mkdir(parents=True, exist_ok=True)
    before = usage()
    if any(before.values()):
        raise ValueError("fresh runner already has child usage")
    disk_roots = [directory] + ([temporary.parent] if temporary is not None else [])
    free = [{"path": str(path), "free_bytes": shutil.disk_usage(path).free} for path in disk_roots]
    if any(row["free_bytes"] < 2 * 1024**3 for row in free):
        raise ValueError("disk prerequisite below stage budget")
    save(directory / "preflight/resource.json", {"before_children": before, "disk_free": free})
    save(directory / "preflight/runtime-source-pins.json", {"files": files})
    save(directory / "spec.json", spec)
    definition = importlib.util.spec_from_file_location("r465_supervisor", ROUND.parent / "round413-full-long-validation-20261103/bounded_stage.py")
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    module.ROUND = directory

    def deadline(signum, frame):
        raise TimeoutError("R465 outer deadline reached")

    started = time.monotonic()
    old_alarm = signal.signal(signal.SIGALRM, deadline)
    signal.alarm(spec["timeout_s"] + 30)
    try:
        module.run(directory / "spec.json")
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_alarm)
    elapsed = time.monotonic() - started
    after = usage()
    roots = [directory] + ([temporary] if temporary is not None else [])
    inventory = disk_inventory(roots)
    save(directory / "resource-file-inventory.json", {"files": inventory, "roots": [str(p) for p in roots], "symlinks": "not followed"})
    measured = sum(row["bytes"] for row in disk_inventory(roots))
    accepted = (after["maxrss_kib"] * 1024 <= 4 * 1024**3 and measured + 65536 <= 2 * 1024**3 and elapsed <= spec["timeout_s"] + 30)
    save(directory / "resource-budget.json", {"accepted": accepted, "before_children": before, "after_children": after,
        "waited_child_max_rss_bytes": after["maxrss_kib"] * 1024,
        "rss_scope": "Linux waited-child maximum, not aggregate concurrent tree peak",
        "regular_file_logical_bytes": measured, "report_reserved_bytes": 65536,
        "file_count_before_inventory_report": len(inventory), "outer_elapsed_s": elapsed,
        "measured_utc": datetime.now(UTC).isoformat(), "enforcement": "retrospective resource audit; unchanged R413 owns child timeout/cleanup"})
    if stage == "reader-red":
        save(directory / "expected-red-assessment.json", assess_red(directory, manifest))
    healthy(directory, red=stage == "reader-red")
    if stage == "reader-green":
        events = events_for(directory)
        collections = [e for e in events if e["event"] == "collection_finished"]
        calls = [e for e in events if e["event"] == "report" and e["when"] == "call"]
        if (len(collections) != 1 or collections[0]["nodeids"] != plan["new_test_nodes"]
            or collections[0]["collection_errors"] or len(calls) != 6 or any(e["outcome"] != "passed" for e in calls)
            or any(e["outcome"] != "passed" for e in events if e["event"] == "report")):
            raise ValueError("six-node GREEN coverage incomplete")
        save(directory / "green-coverage.json", {"six_node_coverage": True, "nodes": plan["new_test_nodes"]})
    result = json.loads((directory / "result.json").read_text())
    print(json.dumps({k: result[k] for k in ("state", "returncode", "reaped", "source_drift", "remaining_live")}))


if __name__ == "__main__":
    run(sys.argv[1])
