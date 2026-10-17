"""R298 finite source-finalization metadata proof; never imports or runs project code."""
from pathlib import Path
import base64
import difflib
import hashlib
import json
import os
import signal
import stat
import time

D = Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round298-p6-t2-plugin-finalization-eof-byte-generation-20261017")
PLAN_SHA = "1589f6c4a28aba533517f55b04cbbabbd56a08ea52ec30ecb232b7fdfa62f472"
FACTS = {}
DEADLINE = None


def tick():
    if DEADLINE is not None and time.monotonic() >= DEADLINE:
        raise TimeoutError("R298 total120s metadata deadline")


def alarm(signum, frame):
    raise TimeoutError("R298 SIGALRM120 metadata deadline")


def condition(name, observed, expected=True):
    tick()
    if type(observed) is not bool or type(expected) is not bool:
        raise TypeError("named condition requires exact native bool")
    FACTS[name] = {"observed": observed, "required": expected, "accepted": observed is expected}
    if observed is not expected:
        raise ValueError("R298 named condition failed: " + name)


def identity(value):
    if type(value) is not dict:
        raise TypeError("exact pin object required")
    result = {key: value[key] for key in ("path", "bytes", "sha256")}
    condition("pin_types:" + str(result["path"]),
              type(result["path"]) is str and Path(result["path"]).is_absolute()
              and type(result["bytes"]) is int and result["bytes"] >= 0
              and type(result["sha256"]) is str and len(result["sha256"]) == 64)
    return result


def raw_read(path):
    tick()
    path = Path(path)
    before = path.lstat()
    condition("regular:" + str(path), stat.S_ISREG(before.st_mode))
    raw = path.read_bytes()
    after = path.lstat()
    coords = lambda info: (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                           info.st_mtime_ns, info.st_ctime_ns)
    condition("stable_read:" + str(path), coords(before) == coords(after) and len(raw) == before.st_size)
    tick()
    return raw


def bytes_pin(path, raw):
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def checked(value, label):
    item = identity(value)
    raw = raw_read(item["path"])
    condition(label, bytes_pin(item["path"], raw) == item)
    return raw


def obj(raw, label):
    value = json.loads(raw.decode("utf-8"))
    condition(label, type(value) is dict)
    return value


def absent(path, label):
    path = Path(path)
    condition(label, not path.exists() and not path.is_symlink())


def complete_before(row, label, current):
    original, archive = identity(row["original"]), identity(row["archive"])
    raw = checked(archive, label + ":archive_pin")
    decoded = base64.b64decode(row["base64"], validate=True)
    condition(label + ":base64", raw == decoded)
    condition(label + ":original_identity", bytes_pin(original["path"], raw) == original)
    condition(label + ":archive_mode", Path(archive["path"]).lstat().st_mode == row["mode"])
    if current:
        condition(label + ":current_bytes", checked(original, label + ":current_pin") == raw)
        condition(label + ":current_mode", Path(original["path"]).lstat().st_mode == row["mode"])
    return raw


def describe(raw, start, end):
    portion = raw[start:end]
    return {"start_byte": start, "end_byte": end, "bytes": len(portion),
            "sha256": hashlib.sha256(portion).hexdigest()}


def main():
    global DEADLINE
    DEADLINE = time.monotonic() + 120
    prior_alarm = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, alarm)
    signal.alarm(120)
    try:
        plan_raw = raw_read(D / "plan.json")
        condition("R298_plan_exact_SHA", hashlib.sha256(plan_raw).hexdigest() == PLAN_SHA)
        plan = obj(plan_raw, "R298_plan_object")
        condition("R298_input_count11", type(plan["inputs"]) is list and len(plan["inputs"]) == 11)
        inputs = [identity(row) for row in plan["inputs"]]
        raw_inputs = [checked(row, "input:" + str(index)) for index, row in enumerate(inputs)]
        manifest_raw = checked(plan["before_manifest"], "R298_before_manifest_pin")
        manifest = obj(manifest_raw, "R298_before_object")
        condition("R298_five_physical_before", manifest["round"] == "R298"
                  and type(manifest["files"]) is list and len(manifest["files"]) == 5)
        for index, row in enumerate(manifest["files"]):
            complete_before(row, "R298_before:" + str(index), True)

        old_plan = obj(raw_inputs[0], "R297_original_plan_object")
        condition("R297_original_plan_identity", old_plan["round"] == "R297")
        before = obj(raw_inputs[2], "R297_before_object")
        condition("R297_four_physical_before", before["round"] == "R297"
                  and type(before["files"]) is list and len(before["files"]) == 4)
        target_pin, candidate_pin = identity(plan["scope"]["target"]), identity(plan["scope"]["approved_candidate"])
        rows = [row for row in before["files"] if row["original"]["path"] == target_pin["path"]]
        condition("original_bca_unique_before", len(rows) == 1)
        original = complete_before(rows[0], "original_bca", False)
        condition("original_bca_pin", bytes_pin(rows[0]["archive"]["path"], original) == inputs[3])
        for index, row in enumerate(before["files"]):
            complete_before(row, "R297_archived_generation:" + str(index), row["original"]["path"] != target_pin["path"])
        target = checked(target_pin, "actual08df_target_pin")
        candidate = checked(candidate_pin, "approved_e6_candidate_pin")
        expected = plan["scope"]["permitted_exact_relationship"]
        condition("target_length30428", len(target) == expected["target_bytes"] == 30428)
        condition("target_SHA08df", hashlib.sha256(target).hexdigest() == expected["target_sha256"])
        condition("target_lines607", len(target.splitlines()) == expected["target_lines"] == 607)
        condition("target_mode33204", Path(target_pin["path"]).lstat().st_mode == expected["mode"] == 33204)
        condition("candidate_length30429", len(candidate) == expected["candidate_bytes"] == 30429)
        condition("candidate_SHAe6", hashlib.sha256(candidate).hexdigest() == expected["candidate_sha256"])
        condition("candidate_lines608", len(candidate.splitlines()) == 608)
        condition("candidate_mode33204", Path(candidate_pin["path"]).lstat().st_mode == 33204)
        condition("original_R297_target_equals_candidate", target == candidate, False)
        condition("original_R297_expected_length_match", len(target) == old_plan["scope"]["expected_after"]["bytes"], False)
        condition("original_R297_expected_SHA_match",
                  hashlib.sha256(target).hexdigest() == old_plan["scope"]["expected_after"]["sha256"], False)
        condition("original_R297_expected_lines_match",
                  len(target.splitlines()) == old_plan["scope"]["expected_after"]["lines"], False)

        changes = old_plan["scope"]["exact_replacements"]
        condition("four_exact_change_ids", [row["id"] for row in changes] == ["A", "B", "C", "D"])
        reconstructed, offsets = original, []
        for row in changes:
            old, new = row["before"].encode("utf-8"), row["after"].encode("utf-8")
            condition("unique_original:" + row["id"], original.count(old) == 1)
            condition("unique_sequential:" + row["id"], reconstructed.count(old) == 1)
            offsets.append((original.index(old), row, old, new))
            reconstructed = reconstructed.replace(old, new, 1)
        condition("four_changes_reconstruct_actual_candidate_e6", reconstructed == candidate)
        condition("original_offset_order", [row[0] for row in offsets] == sorted(row[0] for row in offsets))
        condition("exact_e6_equals_actual08df_plus_one_LF", candidate == target + b"\n")
        condition("exact_candidate_last_byte_0a", candidate[30428:30429] == b"\x0a")
        condition("exact_target_tail_raise_LF", target.endswith(b"        raise\n"))
        condition("exact_candidate_tail_raise_two_LFs", candidate.endswith(b"        raise\n\n"))
        first_diff = next((index for index, pair in enumerate(zip(target, candidate)) if pair[0] != pair[1]),
                          min(len(target), len(candidate)))
        condition("first_difference30428", first_diff == 30428)
        outside, edits, oldpos, newpos = [], [], 0, 0
        for at, row, old, new in offsets:
            length = at - oldpos
            condition("unchanged_interval:" + row["id"],
                      original[oldpos:at] == candidate[newpos:newpos + length])
            outside.append({"before": describe(original, oldpos, at),
                            "approved_candidate": describe(candidate, newpos, newpos + length),
                            "whole_equal": True})
            newpos += length
            condition("approved_exact_edit:" + row["id"], candidate[newpos:newpos + len(new)] == new)
            edits.append({"id": row["id"], "kind": "R297_PLANNED_SOURCE_REPLACEMENT",
                          "before": describe(original, at, at + len(old)),
                          "approved_candidate": describe(candidate, newpos, newpos + len(new)),
                          "before_text": row["before"], "after_text": row["after"]})
            oldpos, newpos = at + len(old), newpos + len(new)
        condition("unchanged_final_interval_against_e6", original[oldpos:] == candidate[newpos:])
        outside.append({"before": describe(original, oldpos, len(original)),
                        "approved_candidate": describe(candidate, newpos, len(candidate)), "whole_equal": True})
        eof = {"id": "EOF", "kind": "R298_EXPLICIT_FINAL_0a_REMOVAL", "candidate_offset": 30428,
               "candidate_bytes_hex": "0a", "actual_target_offset": 30428, "actual_bytes_hex": "",
               "e6_equals_08df_plus_one_LF": True}
        native = obj(raw_inputs[6], "original_native_object")
        native_expected = "*** Begin Patch\n*** Update File: " + target_pin["path"] + "\n"
        for row in changes:
            native_expected += "@@\n" + "".join("-" + line + "\n" for line in row["before"].splitlines())
            native_expected += "".join("+" + line + "\n" for line in row["after"].splitlines())
        native_expected += "*** End Patch"
        condition("native_exact_four_hunk_arguments", native["arguments"] == native_expected)
        condition("native_actual_empty_object", type(native["actual_tool_return"]) is dict and native["actual_tool_return"] == {})
        condition("native_numeric_unknown", native["numeric_exit"] is None)
        condition("native_streams_unknown", native["independent_stdout"] is None and native["independent_stderr"] is None)
        failure = obj(raw_inputs[7], "original_failed_metadata_object")
        condition("original_failure_exit1", failure["actual_tool_return"]["exit_code"] == 1)
        condition("original_failure_chunk_e96552", failure["actual_tool_return"]["chunk_id"] == "e96552")
        invocation = failure["invocation"]
        condition("original_invocation_opaque_string", type(invocation) is dict and type(invocation["cmd"]) is str)
        opaque = invocation["cmd"].encode("utf-8")
        opaque_record = {"container": inputs[7], "selector": "/invocation/cmd",
                         "utf8_bytes": len(opaque), "sha256": hashlib.sha256(opaque).hexdigest(),
                         "invocation": invocation, "executed_or_modified": False}
        condition("opaque_original_invocation_retained", opaque.decode("utf-8") == invocation["cmd"])

        outputs = plan["recovery_metadata"]["outputs"]
        condition("four_output_plus_caller_actual_keys", set(outputs) == {"after", "diff", "proof", "report", "actual"})
        for key, path in outputs.items():
            condition("R298_only_output:" + key, Path(path).parent == D / "implementation")
            absent(path, "new_output_absent:" + key)
        for key in ("diff", "proof", "report"):
            absent(old_plan["outputs"][key], "R297_failed_output_still_absent:" + key)
        absent(old_plan["scope"]["after_archive"], "R297_failed_after_still_absent")
        # Recheck only the finite immutable inputs at the end of the pure-check phase.
        for index, row in enumerate(inputs):
            condition("final_fixed_bytes:" + str(index), checked(row, "final_input:" + str(index)) == raw_inputs[index])
        condition("all_named_checks_match_declared_truth", all(row["accepted"] for row in FACTS.values()))
        tick()

        # No output was opened before all checks above completed.
        def save(path, raw):
            tick()
            with Path(path).open("xb") as handle:
                if handle.write(raw) != len(raw):
                    raise OSError("partial R298 exclusive metadata write")
            tick()
            return bytes_pin(path, raw)

        def save_json(path, value):
            return save(path, (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8"))

        after_pin = save(outputs["after"], target)
        scope = {"round": "R298", "status": "SOURCE_EVIDENCE_ONLY",
                 "original_R297_expected_match": False, "R298_exact_generation_match": True,
                 "candidate": candidate_pin, "target": target_pin, "mode": 33204,
                 "before": rows[0], "after": after_pin, "after_base64": base64.b64encode(target).decode("ascii"),
                 "four_planned_edits": edits, "unchanged_outside_against_approved_candidate": outside,
                 "byte_deltas": edits + [eof], "first_difference_byte_offset": first_diff,
                 "native": inputs[6], "native_semantic_projection_matches_e6": True,
                 "intermediate_e6_target_independently_observed": False,
                 "original_failure": inputs[7], "original_failure_exit": 1,
                 "original_invocation_opaque": opaque_record, "checks": FACTS,
                 "runtime": 0, "behavior_verified": False}
        diff_raw = "".join(difflib.unified_diff(original.decode("utf-8").splitlines(keepends=True),
                          target.decode("utf-8").splitlines(keepends=True),
                          fromfile=rows[0]["archive"]["path"], tofile=target_pin["path"])).encode("utf-8")
        diff_pin = save(outputs["diff"], diff_raw)
        proof_pin = save_json(outputs["proof"], scope)
        report = {"round": "R298", "status": "SOURCE_FINALIZATION_RECOVERY_NOT_BEHAVIOR",
                  "plan": bytes_pin(D / "plan.json", plan_raw), "before_manifest": plan["before_manifest"],
                  "candidate": candidate_pin, "after": target_pin, "physical_after": after_pin,
                  "mode": 33204, "lines": 607, "native_receipt": inputs[6], "native": native,
                  "limited_diff": diff_pin, "scope_proof": proof_pin,
                  "original_R297_expected_match": False, "R298_exact_generation_match": True,
                  "generation": {"original_bca": rows[0]["original"], "complete_before": rows[0]["archive"],
                                 "approved_candidate_e6": candidate_pin, "actual_target08df": target_pin,
                                 "after": after_pin, "mode": 33204},
                  "recovery_provenance": {"R297_finalization_actual": failure["actual_tool_return"],
                                          "original_failure": inputs[7], "R297_remains_failed": True,
                                          "original_invocation_opaque": opaque_record,
                                          "source_native_replayed": False, "R297_outputs_created": False},
                  "runtime_invocations": 0, "roles_changed": False, "behavior_verified": False,
                  "T2_complete": False, "T12_complete": False}
        report_pin = save_json(outputs["report"], report)
        summary = {"round": "R298", "metadata_complete": True,
                   "original_R297_expected_match": False, "R298_exact_generation_match": True,
                   "outputs": {"after": after_pin, "diff": diff_pin, "proof": proof_pin, "report": report_pin},
                   "checks": len(FACTS), "runtime": 0}
        rendered = json.dumps(summary, ensure_ascii=False, allow_nan=False)
        if len((rendered + "\n").encode("utf-8")) > 6000:
            raise ValueError("R298 bounded stdout exceeded")
        print(rendered)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, prior_alarm)


if __name__ == "__main__":
    main()
