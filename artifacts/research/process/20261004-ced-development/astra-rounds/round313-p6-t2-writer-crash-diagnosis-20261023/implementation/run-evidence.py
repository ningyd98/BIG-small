"""R313 finite selected-command evidence runner; stdlib parent only."""
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
PLAN_SHA = "b651e87fce6370fed2e501a188be34e76e4f2bf002da84d1f0d5062308c5bbc0"
HELPER = D.parent / "round296-p6-t2-rpc-timeout-passive-evidence-completion-20261017/implementation/run-evidence.py"
HELPER_SHA = "1371a63dc6faf3c784eea25a71a07b2a42320bdca0951f3bbb5ac7038fc19fe3"
KEYS = ("writer_memory_diagnostic",)


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
    temp = path.with_name(path.name + ".r313-next")
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
                     "provenance": "Genuine new R313 run only; old missing bytes not recovered"})
    return rows


def main():
    require(len(sys.argv) == 2 and sys.argv[1] in KEYS, "one exact R313 command key")
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
    require(gate["round"] == "R313" and gate["commands"] == plan["commands"], "literal command table differs")
    require(gate["sources"]["runner"] == pin(__file__), "runner not bound")
    require(gate["sources"]["sampler"] == pin(D / "implementation/r313_writer_stack.py"), "sampler not bound")
    root = json.loads((D / "root-command-ledger.json").read_bytes())
    author_path = D / "implementation/command-ledger.json"
    before_author = full(author_path)
    author = json.loads(base64.b64decode(before_author["base64"]))
    require(set(root["commands"]) == set(author["commands"]) == set(KEYS), "exact one-key ledgers")
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
    spec = importlib.util.spec_from_file_location("r313_frozen_helpers", HELPER)
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
        (out / "resources").mkdir()
        (out / "sampler").mkdir()
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
    result = {"round": "R313", "command_id": key, "child_exit": process.returncode if process else None,
              "pid": process.pid if process else None, "elapsed_seconds": elapsed,
              "timed_out": timed_out, "output_limited": output_limited, "cleanup": cleanup,
              "errors": errors, "unit_only": key.startswith("observer_"),
              "formal_accepted": False, "whole_T2_accepted": False,
              "environment_difference": "Explicit plugins only; PYTEST_DISABLE_PLUGIN_AUTOLOAD=1"}
    # Every capture block is independent of JUnit and of every other block.
    def capture(stage, operation):
        try:
            operation()
        except BaseException as error:
            errors.append({"stage": stage, "type": type(error).__name__, "message": str(error),
                           "traceback": traceback.format_exc()})

    def capture_streams():
        streams = {name: pin(out / name) for name in ("stdout.txt", "stderr.txt")}
        result["raw_streams"] = streams
        result["raw_threshold_bytes_each"] = threshold
        result["raw_overshoot_bytes"] = {name: max(0, p["bytes"] - threshold) for name, p in streams.items()}
        result["output_limited"] = output_limited or any(result["raw_overshoot_bytes"].values())
        require(not result["output_limited"], "actual raw stream threshold exceeded")

    def capture_source():
        result["source_after"] = write(out / "source-after.json", snapshot(gate))

    def capture_junit():
        result["junit"] = helper.junit_observation(out / "junit.xml", command["node"])
        # Missing JUnit is an explicit diagnostic observation, never a test pass.

    index = []

    def capture_index():
        basetemp = out / "persistent-basetemp"
        try:
            state = basetemp.lstat()
        except FileNotFoundError:
            result["persistent_basetemp"] = {"path": str(basetemp), "exists": False,
                "observation": "absent after actual child"}
        else:
            result["persistent_basetemp"] = {"path": str(basetemp), "exists": True,
                "is_symlink": stat.S_ISLNK(state.st_mode)}
            index.extend(helper.strict_index(basetemp))
        result["persistent_index"] = write(out / "persistent-file-database-index.json",
            {"root": result["persistent_basetemp"], "files": index})

    def capture_databases():
        require("persistent_index" in result, "database capture requires actual index")
        result["new_databases"] = archives(helper, index, out)
        result["database_archive_index"] = write(out / "database-archives.json", result["new_databases"])

    def capture_resources():
        directory = out / "resources"
        paths = sorted(directory.iterdir())
        summary = helper.diagnostic_resources(directory, key, command["child_argv"], process.pid if process else None)
        result["resource_summary"] = write(out / "resource-summary.json", summary)
        result["resource_observation"] = {"known_sidecar_count": len(paths),
            "object_resource_completion": None, "complete_sidecar_set": summary["complete_sidecar_set"],
            "all_records_valid": summary["all_records_valid"], "counts_are_complete_denominator": False}
        result["resource_counts"] = summary["counts"] if paths else None
        require(summary["all_records_valid"], "actual resource sidecar invalid")

    def capture_cases():
        cases = []
        for item in index:
            path = Path(item["path"])
            if stat.S_ISREG(item["mode"]) and path.name in helper.CASE_NAMES:
                cases.append({"pin": pin(path), "data": json.loads(path.read_bytes())})
        result["cases"] = write(out / "cases.json", {"round": "R313", "node": command["node"], "files": cases})

    def capture_prerequisite():
        result["prerequisite"] = helper.prerequisite(out / "prerequisite.json",
            {"module": helper.MODULE_PIN}, process.pid if process else None)
        require(result["prerequisite"]["accepted"], "actual startup prerequisite did not pass")

    def capture_sampler():
        directory = out / "sampler"
        paths = sorted(directory.iterdir())
        require(all(p.name in {"start.json", "frames.jsonl", "end.json"} for p in paths),
                "unexpected sampler file")
        pins = [pin(p) for p in paths]
        total = sum(p["bytes"] for p in pins)
        metadata = sum(p["bytes"] for p in pins if not p["path"].endswith("/frames.jsonl"))
        payload = pin(directory / "frames.jsonl")
        require(total <= 524288 and metadata <= 131072 and payload["bytes"] <= 393216,
                "sampler encoded limits exceeded")
        start_record = json.loads(helper.stable_bytes(directory / "start.json"))
        require(start_record["round"] == "R313" and start_record["pid"] == (process.pid if process else None)
                and start_record["attempted"] is True
                and start_record["interval_seconds"] == 2 and start_record["max_samples"] == 96
                and start_record["record_cap"] == 4096 and start_record["total_cap"] == 524288
                and start_record["payload_cap"] == 393216 and start_record["metadata_cap"] == 131072
                and start_record["product_imports"] is False
                and start_record["profile_or_trace_installed"] is False, "sampler start identity differs")
        raw = helper.stable_bytes(directory / "frames.jsonl")
        lines = raw.splitlines(keepends=True)
        require(0 < len(lines) <= 96 and all(len(line) <= 4096 and line.endswith(b"\n") for line in lines),
                "sampler actual record bound/framing differs")
        records = [json.loads(line) for line in lines]
        previous = None
        coordinates = None
        for ordinal, record in enumerate(records, 1):
            require(record["seq"] == ordinal and record["pid"] == start_record["pid"]
                    and record["main_ident"] == start_record["main_ident"], "sampler record ownership/sequence differs")
            pair = (record["sampler_ident"], record["sampler_native_id"])
            require(all(type(value) is int for value in pair), "actual sampler thread coordinates required")
            coordinates = pair if coordinates is None else coordinates
            require(pair == coordinates, "more than one observer thread identity")
            require(type(record["threads"]) is list and len(record["threads"]) <= 16,
                    "sampler thread cap differs")
            for thread in record["threads"]:
                require(thread["ident"] != pair[0] and type(thread["ident"]) is int,
                        "sampler own stack or invalid ident")
                limit = 128 if thread["main"] else 4
                require(0 <= thread["walk_depth"] <= limit and type(thread["walk_truncated"]) is bool,
                        "sampler walk bound differs")
                require(len(thread["frames"]) <= (16 if thread["main"] else 4)
                        and len(thread["closest_test_frames"]) <= (4 if thread["main"] else 0),
                        "sampler retained frame bound differs")
                for frame in thread["frames"] + thread["closest_test_frames"]:
                    require(set(frame) == {"file", "function", "line", "name_truncated"}
                            and type(frame["file"]) is str and type(frame["function"]) is str
                            and type(frame["line"]) is int and type(frame["name_truncated"]) is bool,
                            "sampler scalar-only frame schema differs")
            if previous is not None:
                require(record["monotonic_ns"] > previous["monotonic_ns"]
                        and record["process_time_ns"] >= previous["process_time_ns"]
                        and record["sampler_thread_time_ns"] >= previous["sampler_thread_time_ns"]
                        and record["maxrss"] >= previous["maxrss"]
                        and record["interval_ns"] == record["monotonic_ns"] - previous["monotonic_ns"]
                        and record["lag_ns"] == max(0, record["interval_ns"] - 2000000000),
                        "sampler actual timing/accounting differs")
            else:
                require(record["interval_ns"] is None and record["lag_ns"] is None,
                        "first sample has fabricated interval")
            previous = record
        end_path = directory / "end.json"
        end = json.loads(helper.stable_bytes(end_path)) if end_path.exists() else None
        result["sampler_observation"] = {"files": pins, "sample_count": len(records),
            "payload_bytes": len(raw), "metadata_bytes": metadata, "total_bytes": total,
            "start": start_record, "end": end, "normal_stop_join": None if end is None else {
                k: end[k] for k in ("join_attempted", "thread_alive", "thread_finished", "exception_type")},
            "missing_end_means_unknown": end is None}
        result["sampler_summary"] = write(out / "sampler-summary.json", result["sampler_observation"])
        if end is not None:
            require(end["pid"] == start_record["pid"] and end["samples"] == len(records)
                    and end["payload_bytes"] == len(raw) and end["started"] is True
                    and (end["ident"], end["native_id"]) == coordinates
                    and end["stop_set"] is True and end["join_attempted"] is True
                    and end["thread_alive"] is False and end["thread_finished"] is True
                    and end["exception_type"] is None and end["hooks_equal"] is True,
                    "sampler normal lifecycle/accounting incomplete")
        else:
            require(result["child_exit"] != 0, "normal successful child lacks sampler end")

    def capture_cleanup():
        require(cleanup["leader_reaped"] is True and cleanup["group_remaining"] is False
                and not cleanup["cleanup_errors"], "owned group cleanup incomplete")

    for stage, operation in (("raw_streams", capture_streams), ("source_after", capture_source),
            ("junit_availability", capture_junit), ("basetemp_index", capture_index),
            ("database_archive", capture_databases), ("resources", capture_resources),
            ("cases", capture_cases), ("prerequisite", capture_prerequisite),
            ("sampler", capture_sampler), ("owned_group_cleanup", capture_cleanup)):
        capture(stage, operation)
    result["child_signal"] = -result["child_exit"] if type(result["child_exit"]) is int and result["child_exit"] < 0 else None
    result["diagnostic_budget_stop"] = timed_out
    result["unexpected_outer_timeout"] = False  # A killed parent cannot produce this completed result.
    result["unexpected_outer_timeout_observation"] = "completed parent only; actual outer tool return also required"
    result["capture_errors"] = errors
    result["diagnostic_evidence_integrity"] = not errors
    result["capture_integrity_complete"] = result["diagnostic_evidence_integrity"]
    result["child_matched_expected_exit"] = None
    result["behavior_candidate_pass"] = False
    result["ROOT_acceptance_required"] = True
    result["unobserved"] = {"OS_handles": None, "external_models": None, "GPU_native": None, "native_tool_exit": None}
    write(out / "result.json", result)
    message = json.dumps({k: result[k] for k in ("command_id", "child_exit", "elapsed_seconds",
                         "capture_integrity_complete", "behavior_candidate_pass", "errors")}, ensure_ascii=False)
    print(message.encode("utf-8")[:5900].decode("utf-8", errors="ignore"))
    return 0 if result["capture_integrity_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
