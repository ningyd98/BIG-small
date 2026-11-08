"""Run each frozen R461 CPU stage once; retain the explicitly expected RED evidence."""
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



def require_expected_red(directory, plan, write=False):
    result = json.loads((directory / "result.json").read_text())
    events = [json.loads(line) for line in (directory / "pytest-events.jsonl").read_text().splitlines()]
    expected = plan["new_test_nodes"]
    calls = [e for e in events if e["event"] == "report" and e["when"] == "call"]
    patterns = {
        expected[0]: ("KeyError", "temperature"),
        expected[1]: ("KeyError", "temperature"),
        expected[2]: ("ValueError", "Sol requires the official OpenAI Chat Completions route"),
        expected[3]: ("new narrowly scoped helper absent", "_recorded_chat_fields"),
        expected[4]: ("new narrowly scoped helper absent", "_offline_reader_adapter_kwargs"),
        expected[5]: ("actual wire does not bind the frozen frame/prompt/settings",),
    }
    matched = {e["nodeid"]: e["outcome"] == "failed" and all(p in (e.get("longrepr") or "") for p in patterns.get(e["nodeid"], ("undeclared node",))) for e in calls}
    report_errors = [e for e in events if e["event"] == "report" and e["when"] != "call" and e["outcome"] != "passed"]
    collection = [e for e in events if e["event"] == "collection_finished"]
    accepted = (result["returncode"] == 1 and result["state"] == "FINISHED"
        and result["reaped"] and not result["source_drift"] and not result["remaining_live"]
        and len(calls) == 6 and set(matched) == set(expected) and all(matched.values())
        and not report_errors and len(collection) == 1 and collection[0]["collection_errors"] == 0
        and collection[0]["nodeids"] == expected)
    assessment = {"expected_red": accepted, "matched": matched, "setup_teardown_errors": report_errors,
        "raw_returncode": result["returncode"], "scope": "SOFTWARE_ONLY_READER_TEST"}
    if write:
        save(directory / "expected-red-assessment.json", assessment)
    else:
        if json.loads((directory / "expected-red-assessment.json").read_text()) != assessment:
            raise ValueError("RED assessment drift")
    if not accepted:
        raise ValueError("unexpected RED failure; preserve results and request actual Astra plan")


def run(stage):
    plan_path = ROUND / "plan.json"
    if hashlib.sha256(plan_path.read_bytes()).hexdigest() != "35b79fbfe3d302941b3fa73ca90a0b592dff6a3fd2a997552cb590411fa23542":
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
        if name == "reader-red":
            require_expected_red(ROUND / "validation" / name, plan)
        elif result["returncode"] != 0 or result["remaining_live"] or result["source_drift"] or not result["reaped"] or result["state"] != "FINISHED":
            raise ValueError("previous stage did not pass")
    rows = json.loads((ROUND / plan["input_pins"]).read_text())
    permitted = set(plan["allowed_product_edits"])
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
    definition = importlib.util.spec_from_file_location("r461_supervisor", ROUND.parent / "round413-full-long-validation-20261103/bounded_stage.py")
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    module.ROUND = directory
    module.run(directory / "spec.json")
    result = json.loads((directory / "result.json").read_text())
    if stage == "reader-red":
        require_expected_red(directory, plan, write=True)
    print(json.dumps({k: result.get(k) for k in ("state", "returncode", "reaped", "source_drift", "remaining_live")}))


if __name__ == "__main__":
    run(sys.argv[1])
