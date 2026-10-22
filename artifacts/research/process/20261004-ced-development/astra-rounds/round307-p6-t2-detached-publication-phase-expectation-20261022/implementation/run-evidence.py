"""R307 finite selected-command evidence runner; stdlib parent only."""
from __future__ import annotations
import base64
import copy
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
PLAN_SHA = "5b93a067f41b198d0732ad54a21954f77d9122655fb7956e90cdc1ca188d2488"
HELPER = D.parent / "round296-p6-t2-rpc-timeout-passive-evidence-completion-20261017/implementation/run-evidence.py"
HELPER_SHA = "1371a63dc6faf3c784eea25a71a07b2a42320bdca0951f3bbb5ac7038fc19fe3"
KEYS = ("observer_detached_summary", "dual_behavior")


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
    temp = path.with_name(path.name + ".r307-next")
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
                     "provenance": "Genuine new R307 run only; old missing bytes not recovered"})
    return rows


def main():
    require(len(sys.argv) == 2 and sys.argv[1] in KEYS, "one exact R307 command key")
    key = sys.argv[1]
    plan_pin = pin(D / "plan.json")
    require(plan_pin["sha256"] == PLAN_SHA, "actual Astra plan changed")
    plan = json.loads((D / "plan.json").read_bytes())
    command = plan["commands"][key]
    gate_path = D / ("red-source-gate.json" if key == "observer_red" else "source-gate.json")
    accepted_path = D / ("root-red-source-acceptance.json" if key == "observer_red" else "root-source-acceptance.json")
    gate = json.loads(gate_path.read_bytes())
    accepted = json.loads(accepted_path.read_bytes())
    require(accepted["reviewed"] is True and accepted["source_gate"] == pin(gate_path),
            "ROOT acceptance does not bind gate")
    require(gate["round"] == "R307" and gate["commands"] == plan["commands"], "literal command table differs")
    require(gate["sources"]["runner"] == pin(__file__), "runner not bound")
    root = json.loads((D / "root-command-ledger.json").read_bytes())
    author_path = D / "implementation/command-ledger.json"
    before_author = full(author_path)
    author = json.loads(base64.b64decode(before_author["base64"]))
    require(set(root["commands"]) == set(author["commands"]) == set(KEYS), "exact two-key ledgers")
    reserved = root["commands"][key]
    require(reserved["state"] == "RESERVED" and reserved["used"] == 1 and reserved["remaining"] == 0,
            "ROOT did not reserve selected command")
    require(reserved["source_gate"] == pin(gate_path) and reserved["acceptance"] == pin(accepted_path),
            "reservation source identity differs")
    require(author["commands"][key]["state"] == "HELD" and author["commands"][key]["used"] == 0
            and author["commands"][key]["remaining"] == 1, "AUTHOR command already consumed")
    out = Path(command["output"])
    out.mkdir(parents=True, exist_ok=False)
    write(out / "invocation.json", {"command_id": key, **command, "source_gate": pin(gate_path),
                                  "root_acceptance": pin(accepted_path), "root_reservation": reserved,
                                  "executor_binding": gate["executor_binding"]})
    write(out / "source-before.json", snapshot(gate))
    require(pin(HELPER)["sha256"] == HELPER_SHA, "reviewed helper changed")
    spec = importlib.util.spec_from_file_location("r307_frozen_helpers", HELPER)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)  # main guard remains false; stdlib definitions only.
    write(out / "helper-provenance.json", {"source": pin(HELPER),
          "unchanged_functions": ["_t2_cleanup", "diagnostic_resources", "_t2_index",
             "strict_index", "junit_observation", "prerequisite", "behavior_resources_complete"],
          "product_imported_in_parent": False})
    author["commands"][key].update(state="CONSUMED_BEFORE_START", used=1, remaining=0,
                                  reservation_id=reserved["reservation_id"])
    cas(author_path, before_author, author, out / "author-consumed.json")
    process = None
    cleanup = {"leader_reaped": None, "group_remaining": None, "cleanup_errors": []}
    errors = []
    timed_out = output_limited = False
    start = time.monotonic()
    deadline = start + command["limits"]["child_seconds"]
    threshold = command["limits"]["raw_stream_threshold_bytes_each"]
    try:
        if key == "dual_behavior":
            (out / "passive").mkdir()
        if key == "dual_behavior":
            (out / "resources").mkdir()
        with (out / "stdout.txt").open("xb") as stdout, (out / "stderr.txt").open("xb") as stderr:
            process = subprocess.Popen(command["child_argv"], cwd=ROOT, env=command["child_env"],
                                       stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       shell=False, start_new_session=True)
            write(out / "actual-child-start.json", {"pid": process.pid, "monotonic_start": start,
                  "deadline": deadline, "argv": command["child_argv"], "env": command["child_env"]})
            while process.poll() is None:
                timed_out = time.monotonic() >= deadline
                output_limited = any((out / name).stat().st_size > threshold for name in ("stdout.txt", "stderr.txt"))
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
    elapsed = time.monotonic() - start
    result = {"round": "R307", "command_id": key, "child_exit": process.returncode if process else None,
              "pid": process.pid if process else None, "elapsed_seconds": elapsed,
              "timed_out": timed_out, "output_limited": output_limited, "cleanup": cleanup,
              "errors": errors, "unit_only": key.startswith("observer_"),
              "formal_accepted": False, "whole_T2_accepted": False,
              "environment_difference": "Explicit plugins only; PYTEST_DISABLE_PLUGIN_AUTOLOAD=1"}
    try:
        streams = {name: pin(out / name) for name in ("stdout.txt", "stderr.txt")}
        result["raw_streams"] = streams
        result["raw_threshold_bytes_each"] = threshold
        result["raw_overshoot_bytes"] = {name: max(0, p["bytes"] - threshold) for name, p in streams.items()}
        result["output_limited"] = output_limited or any(result["raw_overshoot_bytes"].values())
        write(out / "source-after.json", snapshot(gate))
        junit = helper.junit_observation(out / "junit.xml", command["node"])
        result["junit"] = junit
        require(junit["available"], "actual JUnit unavailable")
        basetemp = out / "persistent-basetemp"
        try:
            basetemp_state = basetemp.lstat()
        except FileNotFoundError:
            if not result["unit_only"]:
                raise
            index = []
            result["persistent_basetemp"] = {"path": str(basetemp), "exists": False,
                "is_symlink": False, "observation": "unit_basetemp_absent_after_child"}
        else:
            index = helper.strict_index(basetemp)
            result["persistent_basetemp"] = {"path": str(basetemp), "exists": True,
                "is_symlink": stat.S_ISLNK(basetemp_state.st_mode),
                "observation": "existing_path_strictly_indexed"}
        dbs = archives(helper, index, out)
        result["new_databases"] = dbs
        result["persistent_index"] = write(out / "persistent-file-database-index.json",
                                           {"root": result["persistent_basetemp"], "files": index, "databases": dbs})
        if not result["unit_only"]:
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
            result["cases"] = write(out / "cases.json", {"round": "R307", "node": command["node"], "files": cases})
            pre = helper.prerequisite(out / "prerequisite.json", {"module": helper.MODULE_PIN}, process.pid)
            result["prerequisite"] = pre
            require(pre["accepted"], "startup prerequisite did not pass")
            if key == "dual_behavior":
                passive = json.loads((out / "passive/summary.json").read_bytes())
                events = json.loads((out / "passive/events.json").read_bytes())
                result["passive"] = {"summary": pin(out / "passive/summary.json"),
                                     "events": pin(out / "passive/events.json"), "data": passive}
                require(passive["dropped_events"] == 0 and not passive["observer_errors"]
                        and passive["incomplete"] is False, "passive observer incomplete")
                require(isinstance(events["records"], list)
                        and len(events["records"]) == passive["events_count"]
                        and passive["hooks_equal"] is True and not passive["new_threads_still_live"]
                        and passive["accounting"]["verified"] is True
                        and not passive["cap_hit"], "passive lifecycle/accounting evidence differs")
        require(cleanup["leader_reaped"] is True and cleanup["group_remaining"] is False
                and not cleanup["cleanup_errors"], "owned group cleanup incomplete")
    except BaseException as error:
        errors.append({"stage": "capture", "type": type(error).__name__, "message": str(error),
                       "traceback": traceback.format_exc()})
    result["capture_integrity_complete"] = not errors and not result["timed_out"] and not result["output_limited"]
    result["child_matched_expected_exit"] = result["child_exit"] == command["expected_exit"]
    result["behavior_candidate_pass"] = bool(result["capture_integrity_complete"] and result["child_exit"] == 0
        and not result["unit_only"] and result.get("behavior_resources_complete") is True
        and result.get("junit", {}).get("failures") == 0 and result["junit"].get("errors") == 0
        and result["junit"].get("skips") == 0)
    result["ROOT_acceptance_required"] = True
    result["unobserved"] = {"OS_handles": None, "external_models": None, "GPU_native": None, "native_tool_exit": None}
    write(out / "result.json", result)
    message = json.dumps({k: result[k] for k in ("command_id", "child_exit", "elapsed_seconds",
                         "capture_integrity_complete", "behavior_candidate_pass", "errors")}, ensure_ascii=False)
    print(message.encode("utf-8")[:5900].decode("utf-8", errors="ignore"))
    return 0 if result["capture_integrity_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
