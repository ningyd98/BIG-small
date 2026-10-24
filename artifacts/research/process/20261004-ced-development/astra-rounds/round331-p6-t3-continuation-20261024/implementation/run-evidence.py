"""R331 exact nine-node evidence runner; R319 process/evidence mechanisms retained."""
from __future__ import annotations
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import traceback

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D = Path(__file__).resolve().parent.parent
PLAN_SHA = "0c9b1abad450d8dd164f2b070d281f238bc008f31a301d531df000981cc7d5fd"
HELPER = D / "implementation/resource-evidence-helpers.py"
KEYS = ("t3_red", "t3_green")
RAW_THRESHOLD = 33554432  # Retained R319 threshold; never truncate original streams.


def require(ok, message):
    if not ok:
        raise ValueError(message)


def pin(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "regular file required: " + str(path))
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def check(record):
    require(pin(record["path"]) == {k: record[k] for k in ("path", "bytes", "sha256")},
            "source/evidence pin changed: " + record["path"])


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()


def write(path, value):
    path = Path(path)
    raw = value if isinstance(value, bytes) else encoded(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())
    require(path.read_bytes() == raw, "exclusive write readback differs")
    return pin(path)


def full(path):
    path = Path(path)
    raw = path.read_bytes()
    return {**pin(path), "mode": stat.S_IMODE(path.stat().st_mode),
            "base64": base64.b64encode(raw).decode("ascii")}


def cas(path, before, after, receipt):
    check(before)
    require(stat.S_IMODE(path.stat().st_mode) == before["mode"], "ledger mode changed")
    require(path.read_bytes() == base64.b64decode(before["base64"]), "ledger CAS bytes changed")
    write(receipt.with_name(receipt.stem + "-before.json"), before)
    temp = path.with_name(path.name + ".r331-next")
    write(temp, after)
    os.chmod(temp, before["mode"])
    check(before)
    os.replace(temp, path)
    require(path.read_bytes() == encoded(after), "ledger CAS after differs")
    return write(receipt, {"before": before, "after": full(path)})


def snapshot(gate):
    rows = [pin(row["path"]) for row in gate["pins"]]
    require(rows == gate["pins"], "source generation drift")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    require(head == gate["HEAD"], "HEAD changed")
    return {"pins": rows, "HEAD": head}


def archives(helper, index, out):
    rows = []
    for item in index:
        original = Path(item["path"])
        if not stat.S_ISREG(item["mode"]) or original.suffix not in {".db", ".sqlite", ".sqlite3"}:
            continue
        check(item)
        dst = out / "retained-databases" / (str(len(rows)) + original.suffix)
        archive = write(dst, helper.stable_bytes(original))
        require((archive["sha256"], archive["bytes"]) == (item["sha256"], item["bytes"]),
                "DB archive differs")
        sides = []
        for suffix in ("-wal", "-shm", "-journal"):
            side = Path(str(original) + suffix)
            if side.exists() or side.is_symlink():
                original_pin = pin(side)
                saved = write(Path(str(dst) + suffix), helper.stable_bytes(side))
                require(saved["sha256"] == original_pin["sha256"], "sidecar copy differs")
                sides.append({"path": str(side), "exists": True, "pin": original_pin, "archive": saved})
            else:
                sides.append({"path": str(side), "exists": False, "pin": None, "archive": None})
        rows.append({"pin": pin(original), "archive": archive, "sidecars": sides,
                     "provenance": "Genuine new R331 run only; old missing bytes not recovered"})
    return rows


def main():
    require(len(sys.argv) == 2 and sys.argv[1] in KEYS, "one exact R331 command key")
    key = sys.argv[1]
    require(pin(D / "plan.json")["sha256"] == PLAN_SHA, "actual Astra plan changed")
    plan = json.loads((D / "plan.json").read_bytes())
    command = plan["commands"][key]
    gate_path = D / ("red-source-gate.json" if key == "t3_red" else "source-gate.json")
    accepted_path = D / ("root-red-source-acceptance.json" if key == "t3_red" else "root-source-acceptance.json")
    gate = json.loads(gate_path.read_bytes())
    accepted = json.loads(accepted_path.read_bytes())
    require(accepted["reviewed"] is True and accepted["source_gate"] == pin(gate_path),
            "ROOT acceptance does not bind gate")
    require(gate["round"] == "R331" and gate["commands"] == plan["commands"], "literal command table differs")
    require(gate["sources"]["runner"] == pin(__file__) and gate["sources"]["helper"] == pin(HELPER),
            "runner/helper not bound")
    root = json.loads((D / "root-command-ledger.json").read_bytes())
    author_path = D / "implementation/author-command-ledger.json"
    before_author = full(author_path)
    author = json.loads(base64.b64decode(before_author["base64"]))
    require(set(root["commands"]) == set(author["commands"]) == set(KEYS), "exact two-key ledgers")
    reserved = root["commands"][key]
    require(reserved["state"] == "RESERVED" and reserved["used"] == 1 and reserved["remaining"] == 0,
            "ROOT did not reserve selected command")
    require(reserved["source_gate"] == pin(gate_path) and reserved["acceptance"] == pin(accepted_path),
            "reservation source identity differs")
    require(author["commands"][key]["state"] == "HELD_PENDING_ROOT_SOURCE_GATE"
            and author["commands"][key]["used"] == 0 and author["commands"][key]["remaining"] == 1,
            "AUTHOR command already consumed")
    out = Path(command["output"])
    out.mkdir(parents=True, exist_ok=False)
    write(out / "invocation.json", {"command_id": key, **command, "source_gate": pin(gate_path),
          "root_acceptance": pin(accepted_path), "root_reservation": reserved,
          "executor_binding": gate["executor_binding"]})
    write(out / "source-before.json", snapshot(gate))
    spec = importlib.util.spec_from_file_location("r331_frozen_helpers", HELPER)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)  # Local reviewed stdlib definitions only.
    write(out / "helper-provenance.json", {"source": pin(HELPER),
          "inheritance": pin(D / "implementation/inherited-functions.json"),
          "product_imported_in_parent": False})
    author["commands"][key].update(state="CONSUMED_BEFORE_START", used=1, remaining=0,
                                  reservation_id=reserved["reservation_id"])
    cas(author_path, before_author, author, out / "author-consumed.json")
    process = None
    cleanup = {"leader_reaped": None, "group_remaining": None, "cleanup_errors": []}
    errors = []
    timed_out = output_limited = False
    start = time.monotonic()
    deadline = start + command["child_seconds"]
    try:
        (out / "resources").mkdir()
        with (out / "stdout.txt").open("xb") as stdout, (out / "stderr.txt").open("xb") as stderr:
            process = subprocess.Popen(command["child_argv"], cwd=ROOT, env=command["child_env"],
                                       stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       shell=False, start_new_session=True)
            write(out / "actual-child-start.json", {"pid": process.pid, "monotonic_start": start,
                  "deadline": deadline, "argv": command["child_argv"], "env": command["child_env"]})
            while process.poll() is None:
                timed_out = time.monotonic() >= deadline
                output_limited = any((out / name).stat().st_size > RAW_THRESHOLD
                                     for name in ("stdout.txt", "stderr.txt"))
                if timed_out or output_limited:
                    break
                time.sleep(0.1)
    except BaseException as error:
        errors.append({"stage": "child", "type": type(error).__name__, "message": str(error),
                       "traceback": traceback.format_exc()})
    finally:
        if process is not None:
            cleanup = helper._t2_cleanup(process)
        current = full(author_path)
        spent = json.loads(base64.b64decode(current["base64"]))
        require(spent["commands"][key]["state"] == "CONSUMED_BEFORE_START", "AUTHOR state changed")
        spent["commands"][key]["state"] = "SPENT"
        cas(author_path, current, spent, out / "author-spent.json")
    result = {"round": "R331", "command_id": key, "child_exit": process.returncode if process else None,
              "pid": process.pid if process else None, "elapsed_seconds": time.monotonic() - start,
              "timed_out": timed_out, "output_limited": output_limited, "cleanup": cleanup,
              "errors": errors, "formal_accepted": False, "whole_B_accepted": False,
              "environment_difference": "Explicit plugins only; PYTEST_DISABLE_PLUGIN_AUTOLOAD=1"}
    try:
        streams = {name: pin(out / name) for name in ("stdout.txt", "stderr.txt")}
        result["raw_streams"] = streams
        result["raw_threshold_bytes_each"] = RAW_THRESHOLD
        result["raw_overshoot_bytes"] = {name: max(0, p["bytes"] - RAW_THRESHOLD) for name, p in streams.items()}
        result["output_limited"] = output_limited or any(result["raw_overshoot_bytes"].values())
        write(out / "source-after.json", snapshot(gate))
        junit = helper.junit_observation(out / "junit.xml", command["nodes"])
        result["junit"] = junit
        require(junit["available"] and junit["tests"] == 9 and junit["errors"] == 0
                and junit["skips"] == 0, "exact nine non-error/non-skip JUnit cases required")
        basetemp = out / "persistent-basetemp"
        index = helper.strict_index(basetemp)
        dbs = archives(helper, index, out)
        result["new_databases"] = dbs
        result["persistent_index"] = write(out / "persistent-file-database-index.json",
                                           {"root": str(basetemp), "files": index, "databases": dbs})
        summary = helper.diagnostic_resources(out / "resources", key, command["child_argv"], process.pid)
        result["resource_summary"] = write(out / "resource-summary.json", summary)
        result["resource_counts"] = summary["counts"]
        require(summary["complete_sidecar_set"] and summary["all_records_valid"],
                "resource capture invalid/incomplete")
        facts = {}
        result["behavior_resources_complete"] = helper.behavior_resources_complete(summary, facts=facts)
        result["completion_facts"] = facts
        cases = []
        for item in index:
            path = Path(item["path"])
            if stat.S_ISREG(item["mode"]) and path.name in helper.CASE_NAMES:
                cases.append({"pin": pin(path), "data": json.loads(path.read_bytes())})
        if key == "t3_green":
            require(len(cases) == 9 and [r["data"]["nodeid"] for r in sorted(
                cases, key=lambda r: command["nodes"].index(r["data"]["nodeid"]))] == command["nodes"],
                    "nine genuine T3 behavior case files required")
        result["cases"] = write(out / "cases.json", {"round": "R331", "nodes": command["nodes"], "files": cases})
        pre = helper.prerequisite(out / "prerequisite.json", {"module": helper.MODULE_PIN}, process.pid)
        result["prerequisite"] = pre
        require(pre["accepted"], "startup prerequisite did not pass")
        require(cleanup["leader_reaped"] is True and cleanup["group_remaining"] is False
                and not cleanup["cleanup_errors"], "owned group cleanup incomplete")
    except BaseException as error:
        errors.append({"stage": "capture", "type": type(error).__name__, "message": str(error),
                       "traceback": traceback.format_exc()})
    result["capture_integrity_complete"] = not errors and not result["timed_out"] and not result["output_limited"]
    result["child_matched_expected_exit"] = result["child_exit"] == command["expected_exit"]
    result["behavior_candidate_pass"] = bool(result["capture_integrity_complete"] and result["child_exit"] == 0
        and result.get("behavior_resources_complete") is True and result.get("junit", {}).get("failures") == 0)
    result["ROOT_acceptance_required"] = True
    result["unobserved"] = {"OS_handles": None, "external_models": None, "GPU_native": None, "native_tool_exit": None}
    write(out / "result.json", result)
    message = json.dumps({k: result[k] for k in ("command_id", "child_exit", "elapsed_seconds",
                         "capture_integrity_complete", "behavior_candidate_pass", "errors")}, ensure_ascii=False)
    print(message.encode("utf-8")[:5900].decode("utf-8", errors="ignore"))
    return 0 if result["capture_integrity_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
