"""R216 one-shot view and comparison of the existing R214 receipt."""
from pathlib import Path
import hashlib
import json
import shlex
import signal

signal.alarm(120)
PINS = json.loads(r'''[{"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round216-p6-t2-root-receipt-schema-reader-20261015/original-root-read-failure.json","bytes":5216,"sha256":"5ef1e698242362592dc39efbecabf6b31daf1e2e4672c7ffb2c6901cbce2447b"},{"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round214-p6-t2-writer-reference-verified-paths-20261015/actual-tool-return.json","bytes":36047,"sha256":"af57bb73ba36d04305bce9183869a007fedf434820641ce1bc8686a745722f8b"},{"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round214-p6-t2-writer-reference-verified-paths-20261015/step-report.json","bytes":2601,"sha256":"cf74a1589028997127b7f5edb40f90d06015755df7f364a33c968dac811610d7"},{"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round214-p6-t2-writer-reference-verified-paths-20261015/plan.json","bytes":21073,"sha256":"af610131aa0f8221350c17031a5f2ebb3b9b3c2ed9e050fb5340787adcbef656"},{"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round215-p6-t2-writer-reference-line-count-erratum-20261015/plan.json","bytes":6333,"sha256":"2321cf6dde428c0cade12813a3caadb26c7f5769a5315fcb09184957d1fbf4de"},{"path":"/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_recovery_lifecycle_module.py","bytes":59993,"sha256":"f76858e388dba3ab4dab0c186d1763d3fa271990bbcf4cd3614d2b5a57998854"},{"path":"/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_phase6_2_replan_resume.py","bytes":22957,"sha256":"2a0a384a8bc63d9f40f2db80acd04097e89ce682f660e719ab5665cff814e7c1"},{"path":"/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_visual_evidence_contract.py","bytes":9994,"sha256":"770b9fcef2836615a1d61f939ccef90f34bb60c5dfaa050186845f507738564a"},{"path":"/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_rgbd_observations.py","bytes":8520,"sha256":"333b1837cff77bdfce9344cf40f7617064570e1e3c08c881d6942316e9a250fe"}]''')
HERE = Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round216-p6-t2-root-receipt-schema-reader-20261015")
RESULT = HERE / "implementation/verification-result.json"
checks = []
observed_pins = []
source_display = []
step_text = ""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check(name, passed, actual, expected):
    checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})


def unique_mapping(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key: " + key)
        value[key] = item
    return value


def parse(text):
    return json.loads(text, object_pairs_hook=unique_mapping)


try:
    blobs = []
    pin_results = []
    for item in PINS:
        blob = Path(item["path"]).read_bytes()
        current = {"path": item["path"], "bytes": len(blob), "sha256": sha(blob)}
        observed_pins.append(current)
        pin_results.append(current == item)
        blobs.append(blob)
    check("input_pins", all(pin_results) and len(pin_results) == 9, pin_results, [True] * 9)
    receipt, step, plan, erratum = [parse(blob.decode("utf-8")) for blob in blobs[1:5]]
    step_text = blobs[2].decode("utf-8")
    actual = receipt["actual_tool_return"]
    approved = plan["execution"]["new_metadata_read"]
    check("receipt_schema", receipt["schema_version"] == "bigsmall.r214.actual-tool-return.v1"
          and receipt["round"] == "R214" and "transport_command" in receipt
          and "actual_command" not in receipt,
          {"schema": receipt["schema_version"], "round": receipt["round"], "keys": sorted(receipt)},
          "R214 schema with observed transport_command")
    completion_ok = (
        type(actual["exit_code"]) is int and actual["exit_code"] == 0
        and actual["chunk_id"] == "87810e" and receipt["initial"] == actual
        and receipt["completion"] is None and type(receipt["attempt"]) is int
        and type(receipt["retry"]) is int and (receipt["attempt"], receipt["retry"]) == (1, 0)
        and receipt["product_execution"] is False
        and receipt["independent_stdout"] is None and receipt["independent_stderr"] is None)
    check("actual_completion", completion_ok,
          {"chunk": actual["chunk_id"], "exit": actual["exit_code"],
           "initial_equal": receipt["initial"] == actual, "attempt": receipt["attempt"],
           "retry": receipt["retry"], "completion": receipt["completion"]},
          "exit0/chunk87810e/initial equality/null completion/one attempt/no execution")
    expected_env = {"PATH": "/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin:/usr/bin:/bin",
                    "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
    expected_tokens = ["env", "-i"] + [key + "=" + value for key, value in approved["finite_env"].items()] + approved["argv"]
    transport_ok = (
        receipt["transport_command"] == approved["exact_transport_command"]
        and receipt["cwd"] == approved["cwd"] == "/home/ningyd/文档/ChatGPT/BIGsmall"
        and receipt["shell"] == "/bin/bash" and receipt["login"] is False
        and approved["finite_env"] == expected_env and len(approved["argv"]) == 3
        and approved["argv"][:2] == ["/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python", "-c"]
        and approved["argv"][2] == approved["source"]
        and shlex.split(receipt["transport_command"]) == expected_tokens)
    check("transport_exact", transport_ok,
          {"transport_sha256": sha(receipt["transport_command"].encode("utf-8")),
           "cwd": receipt["cwd"], "shell": receipt["shell"], "login": receipt["login"]},
          "exact approved transport/source/argv/env; never executed here")
    output = actual["output"]
    output_ok = (type(output) is str and "Warning: truncated output" not in output
                 and len(output.encode("utf-8")) == step["actual_combined_output_utf8_bytes"] == 15116
                 and len(output.encode("utf-8")) <= 36000)
    check("complete_output", output_ok,
          {"type": type(output).__name__, "utf8_bytes": len(output.encode("utf-8"))},
          "intact15116 bytes, <=36000")
    payload = parse(output)
    references = payload["references"]
    packet_ok = (
        set(payload) == {"reference_count", "line_count", "references", "product_execution"}
        and type(payload["reference_count"]) is int and payload["reference_count"] == 4
        and type(payload["line_count"]) is int and payload["line_count"] == 365
        and payload["product_execution"] is False and type(references) is list and len(references) == 4
        and all(type(item) is dict and set(item) == {"path", "bytes", "sha256", "sections"}
                and type(item["sections"]) is list
                and all(type(section) is dict and set(section) == {"start", "end", "text"}
                        for section in item["sections"]) for item in references))
    check("packet_schema", packet_ok,
          {"keys": sorted(payload), "references": len(references), "line_count": payload["line_count"]},
          "exact4 packet keys/four references/exact reference and section keys")
    reference_map = plan["reference_map"]
    identity_results = []
    range_results = []
    expected_step_map = []
    count_total = 0
    section_total = 0
    counts = []
    for index, (item, specification) in enumerate(zip(references, reference_map)):
        physical = observed_pins[index + 5]
        lines = blobs[index + 5].decode("utf-8").splitlines()
        identity = {key: item[key] for key in ["path", "bytes", "sha256"]}
        spec_identity = {key: specification[key] for key in ["path", "bytes", "sha256"]}
        identity_results.append(
            type(item["path"]) is str and type(item["bytes"]) is int
            and type(item["sha256"]) is str and identity == spec_identity == physical
            and len(lines) == specification["line_count"])
        sections = item["sections"]
        pairs = [[section["start"], section["end"]] for section in sections]
        range_results.append({"kind": "ranges", "passed": pairs == specification["ranges"]})
        source_display.append("TARGET " + item["path"])
        selected = 0
        for section in sections:
            start, end, text = section["start"], section["end"], section["text"]
            valid_indices = type(start) is int and type(end) is int and 1 <= start <= end <= len(lines)
            expected = chr(10).join(str(i + 1) + ":" + lines[i] for i in range(start - 1, end)) if valid_indices else ""
            text_ok = type(text) is str and valid_indices and text == expected and text.encode("utf-8") == expected.encode("utf-8")
            range_results.append({"kind": "exact_UTF8_text", "path": item["path"],
                                  "start": start, "end": end, "passed": text_ok,
                                  "expected_sha256": sha(expected.encode("utf-8")),
                                  "actual_sha256": sha(text.encode("utf-8"))})
            section_total += 1
            selected += end - start + 1
            counts.append(end - start + 1)
            source_display.extend(["RANGE " + str(start) + " " + str(end), text])
        count_total += selected
        expected_step_map.append({**identity, "ranges": specification["ranges"], "selected_lines": selected})
    check("reference_identity", len(reference_map) == len(references) == 4 and all(identity_results),
          identity_results, [True] * 4)
    check("ranges_and_text", all(item["passed"] for item in range_results)
          and section_total == 7 and count_total == 365,
          {"sections": section_total, "lines": count_total, "details": range_results},
          "seven exact pinned range/text byte comparisons;365 lines")
    check("erratum", counts == [41, 81, 93, 91, 9, 33, 17]
          and sum(counts) == erratum["arithmetic"]["total"] == 365
          and erratum["arithmetic"]["previous_incorrect_total"] == 465
          and approved["planned_selected_lines"] == 465,
          {"counts": counts, "effective": sum(counts), "historical": approved["planned_selected_lines"]},
          "R215365 statistical interpretation, originalR214465 retained")
    fields = ["attempt", "retry", "metadata_used", "metadata_remaining",
              "product_test_AST_import_probe_SQL_static_Git_commands"]
    budget = [step[field] for field in fields]
    step_ok = (
        step["schema_version"] == "bigsmall.r214.author-read-step.v1" and step["round"] == "R214"
        and step["actual_chunk"] == actual["chunk_id"] and type(step["actual_exit_code"]) is int
        and step["actual_exit_code"] == 0 and step["actual_tool_return"] == observed_pins[1]
        and type(step["actual_returned_reference_count"]) is int
        and step["actual_returned_reference_count"] == 4
        and type(step["actual_returned_selected_lines"]) is int
        and step["actual_returned_selected_lines"] == 365
        and step["validated_reference_map"] == expected_step_map
        and step["reader_guard_completion"] is True and all(type(value) is int for value in budget)
        and budget == [1, 0, 1, 0, 0] and step["source_changed"] is False
        and step["independent_stdout"] is None and step["independent_stderr"] is None)
    check("step_consistency", step_ok,
          {"reference_map_equal": step["validated_reference_map"] == expected_step_map,
           "budget": budget, "guard_completion": step["reader_guard_completion"],
           "source_changed": step["source_changed"]},
          "actual pin/ranges/365 lines/metadata1spent/no source or product execution")
except (OSError, UnicodeError, ValueError, KeyError, TypeError, IndexError) as error:
    check("METADATA_ERROR", False, {"type": type(error).__name__, "message": str(error)}, "exact valid metadata")

check("output_exclusive", not RESULT.exists(), {"result_exists": RESULT.exists()}, False)
forecast = [{"name": item["name"], "passed": item["passed"]} for item in checks]
forecast.append({"name": "display_bound", "passed": True})
summary = {"all_valid": len(forecast) == 12 and all(item["passed"] for item in forecast),
           "checks": forecast, "result_path": str(RESULT)}
display = chr(10).join(source_display + ["FULL_AUTHOR_STEP", step_text,
                                       "NAMED_SUMMARY " + json.dumps(summary, ensure_ascii=False)]) + chr(10)
display_size = len(display.encode("utf-8"))
check("display_bound", display_size <= 48000, display_size, "<=48000 UTF-8 bytes; no slicing")
valid = len(checks) == 12 and all(item["passed"] for item in checks)
result = {"schema_version": "bigsmall.r216.verification-result.v1", "all_valid": valid,
          "checks": checks, "input_pins": observed_pins, "display_utf8_bytes": display_size,
          "full_selected_source_lines": count_total if "count_total" in locals() else None,
          "original_R214_reader_replayed": False, "old_failed_ROOT_reader_replayed": False,
          "product_execution": False}
encoded = (json.dumps(result, ensure_ascii=False, indent=2) + chr(10)).encode("utf-8")
with RESULT.open("xb") as stream:
    stream.write(encoded)
if display_size <= 48000:
    print(display, end="")
else:
    print(json.dumps({"all_valid": False, "display_bound_failed": True, "result_path": str(RESULT)}))
signal.alarm(0)
raise SystemExit(0 if valid else 1)
