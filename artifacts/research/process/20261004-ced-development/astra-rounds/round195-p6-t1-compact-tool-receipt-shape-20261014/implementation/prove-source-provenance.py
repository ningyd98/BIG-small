"""R195 single stdlib source/provenance proof; never imports or runs the settler."""
from pathlib import Path
import base64
import difflib
import hashlib
import json
import os
import signal
import sys
import time
import traceback

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D = Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round195-p6-t1-compact-tool-receipt-shape-20261014")
P = D.parent / "round192-p6-t1-original-green38-unexpected-outcome-20261014"
OLD_SHA = "034b1db438d6a7fb4c6090f76e277be06e1edc7b5e47a09f97e9e9835fa1b20f"
NEW_SHA = "c624570a37964d7bfddb980f3d8764ed73e432150ae62fc0af6883e2dcc7e42d"
REQUIRED = {"JUnit", "accepted_command_outcome", "child_exit", "cleanup", "timed_out", "wrapper_exit"}
OPTIONAL = {"command", "failures", "process_pid"}


def pin(path):
    path = Path(path)
    assert path.is_absolute() and not path.is_symlink()
    assert all(not parent.is_symlink() for parent in path.parents)
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def check(record):
    assert pin(record["path"]) == {key: record[key] for key in ("path", "bytes", "sha256")}


def load(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    with Path(path).open("xb") as stream:
        stream.write((json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())
    return pin(path)


def alarm(signum, frame):
    raise TimeoutError("R195 source proof 120-second cap")


def mask_regions(raw):
    for start, end, label in (
        (b"\ndef actual_tool(", b"\ndef junit(", b"actual_tool"),
        (b"\ndef new_child(", b"\ndef new_preparation(", b"new_child"),
    ):
        assert raw.count(start) == raw.count(end) == 1
        left, right = raw.index(start), raw.index(end)
        assert left < right
        region = raw[left:right]
        assert raw.count(region) == 1
        raw = raw.replace(region, b"\nR195_REVIEWED_" + label + b"\n", 1)
    return raw


def main():
    started = time.monotonic()
    signal.signal(signal.SIGALRM, alarm)
    signal.alarm(120)
    plan = load(D / "plan.json")
    assert pin(D / "plan.json")["sha256"] == "16d4b73b4204c3f4659b25fb208632cf67a306c66a47c1ab2f563f2a5c9aede4"
    command = plan["verification"]["slot"]
    assert [sys.executable, str(Path(__file__).absolute())] == command["argv"] and len(sys.argv) == 1
    assert Path.cwd() == ROOT and dict(os.environ) == command["finite_env"]
    gate = load(D / "implementation/proof-gate.json")
    check(gate["script_pin"])
    ledger_path = D / "command-ledger.json"
    ledger_raw = ledger_path.read_bytes()
    ledger = json.loads(ledger_raw)
    slot = ledger["commands"]["R195_source_provenance_metadata"]
    assert (slot["used"], slot["remaining"], slot["state"]) == (1, 0, "RESERVED_BY_ROOT")
    slot.update(state="SPENT_BEFORE_ACTION", attempts=1, retry=0)
    assert ledger_path.read_bytes() == ledger_raw
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    failures, proof = [], None
    try:
        for record in gate["fixed_inputs"]:
            check(record)
        manifest = load(D / "implementation/before/archive-index.json")
        assert len(manifest["records"]) == 7
        archive_records = {item["original"]["path"]: item for item in manifest["records"]}
        for item in manifest["records"]:
            check(item["archive"])
            assert (item["archive"]["bytes"], item["archive"]["sha256"]) == (
                item["original"]["bytes"], item["original"]["sha256"])
        script = P / "implementation/root-settlement.py"
        archive = D / "implementation/before/root-settlement.py"
        before, after = archive.read_bytes(), script.read_bytes()
        assert len(before) == 29121 and hashlib.sha256(before).hexdigest() == OLD_SHA
        assert len(after) == 30835 and hashlib.sha256(after).hexdigest() == NEW_SHA
        assert mask_regions(before) == mask_regions(after)
        for record in plan["inputs"]:
            if record["path"] == str(script):
                assert record == archive_records[str(script)]["original"]
            else:
                check(record)
        summaries = []
        full_metadata = compact_child = 0
        for row in plan["observation"]["receipt_records"]:
            directory = D.parent / row["round"] / "implementation" / row["command"]
            tool, result = load(directory / "tool-return.json"), load(directory / "result.json")
            check(tool["result_pin"])
            assert tool["result_pin"] == pin(directory / "result.json")
            summary = tool["actual_summary"]
            assert isinstance(summary, dict)
            if "child_exit" in result:
                assert result["command"] in {"red", "ruff", "green", "green51"}
                if summary != result:
                    assert REQUIRED <= set(summary) <= REQUIRED | OPTIONAL
                    assert all(key in result and value == result[key] for key, value in summary.items())
                compact_child += 1
            else:
                assert result["command"] in {"prepare", "prepare_red", "prepare_green"}
                assert summary == result
                full_metadata += 1
            summaries.append({"result": pin(directory / "result.json"), "tool": pin(directory / "tool-return.json"),
                              "kind": "child" if "child_exit" in result else "metadata",
                              "keys": sorted(summary), "all_present_values_match": True})
        assert full_metadata == 5 and compact_child == 7 and len(summaries) == 12
        ruff = load(P / "implementation/ruff/result.json")
        history = {"path": str(script), "bytes": 29121, "sha256": OLD_SHA}
        assert [x for x in ruff["input_records"] if x["path"] == str(script)] == [history]
        for record in ruff["input_records"]:
            if record["path"] == str(script):
                assert record == history and pin(archive)["sha256"] == OLD_SHA
            else:
                check(record)
        snapshot = load(P / "implementation/prepare/candidate-snapshot.json")
        assert len(snapshot["sources"]) == 25 and len(snapshot["protected"]) == 211
        for record in snapshot["sources"]:
            raw = base64.b64decode(record["base64"], validate=True)
            assert len(raw) == record["bytes"] and hashlib.sha256(raw).hexdigest() == record["sha256"]
            assert Path(record["path"]).read_bytes() == raw
        for record in snapshot["protected"]:
            check(record)
        for name in ("command-ledger.json", "root-command-ledger.json"):
            roles = load(P / name)["commands"]
            assert all((roles[n]["used"], roles[n]["remaining"]) == (1, 0) for n in ("prepare", "ruff"))
            assert all((roles[n]["used"], roles[n]["remaining"], roles[n]["state"]) == (0, 1, "HELD_PENDING_ROOT_GATE")
                       for n in ("green51", "root_settlement"))
        assert not (P / "implementation/green51").exists() and not (P / "implementation/root_settlement").exists()
        for record in gate["fixed_inputs"]:
            check(record)
        diff_path = D / "implementation/limited.diff"
        with diff_path.open("xb") as stream:
            stream.write("".join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                         fromfile=str(archive), tofile=str(script))).encode())
        proof = write(D / "implementation/source-proof.json", {
            "round": "R195", "status": "SOURCE_PROVENANCE_ONLY", "old_source": pin(archive), "current_source": pin(script),
            "outside_two_functions_identical": True, "receipts": summaries, "full_metadata": full_metadata,
            "compact_child": compact_child, "Ruff_input_count": len(ruff["input_records"]),
            "Ruff_exact_historical_records": 1, "other_Ruff_records_current": True,
            "owned_source_count": 25, "protected_count": 211, "final_R192_slots_held": True,
            "settler_executed": False, "product_commands": 0, "limited_diff": pin(diff_path)})
    except BaseException as error:
        failures.append({"type": type(error).__name__, "message": str(error),
                         "traceback": "".join(traceback.format_exception(error))})
    result = {"round": "R195", "command": "R195_source_provenance_metadata", "attempt": 1, "retry": 0,
              "exit_code": 0 if not failures else 1, "elapsed_seconds": time.monotonic() - started,
              "proof": proof, "failures": failures, "product_commands": 0, "settler_executed": False,
              "T1_complete": False, "T12_complete": False}
    saved = write(D / "implementation/run/result.json", result)
    signal.alarm(0)
    print(json.dumps({"exit_code": result["exit_code"], "result": saved, "proof": proof}))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
