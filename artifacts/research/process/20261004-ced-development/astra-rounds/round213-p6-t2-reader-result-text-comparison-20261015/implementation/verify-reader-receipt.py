"""R213 one-shot metadata validation of an existing R211 receipt."""
from pathlib import Path
import hashlib
import json
import shlex
import signal
import sys

signal.alarm(120)
ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
ROUNDS = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds"
HERE = ROUNDS / "round213-p6-t2-reader-result-text-comparison-20261015"
OLD = ROUNDS / "round211-p6-t2-writer-fixture-path-reader-20261015"
INPUTS = [
    (HERE / "original-root-gate-failure.json", 1804, "3f10671dcb11c67ccc3f88140f61ab8dc0f454c5091addeabb6a13fe2f21bff7", "pin_original_failure"),
    (OLD / "plan.json", 9531, "80d1ee56db430a2e51bd84882e2a543b897b739c5a2af3592ff1bfc2c80270a5", "pin_R211_plan"),
    (OLD / "actual-tool-return.json", 11223, "216dcee632a3e295fdb421ee26681296b9168ec3c76d780685c29219480d3119", "pin_actual_receipt"),
    (OLD / "step-report.json", 1206, "ccef85ed1ff281e48d050009221835d893ebc873a68f7fa146e31209d01fdd56", "pin_author_step"),
    (ROOT / "tests/test_visual_verification_repository.py", 29485, "c892ad672b82ce5d57b25beee008ea913e446a73d45d46da5b48b1f7dbc1ab74", "pin_target"),
]
checks = []
pins = []


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check(name, condition, actual, expected):
    checks.append({"name": name, "passed": bool(condition), "actual": actual, "expected": expected})


def unique_mapping(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def parse(text):
    return json.loads(text, object_pairs_hook=unique_mapping)


try:
    data = []
    for path, size, digest, name in INPUTS:
        raw = path.read_bytes()
        observed = {"path": str(path), "bytes": len(raw), "sha256": sha(raw)}
        pins.append(observed)
        check(name, len(raw) == size and sha(raw) == digest, observed, {"bytes": size, "sha256": digest})
        data.append(raw)
    plan, receipt, step = [parse(raw.decode("utf-8")) for raw in data[1:4]]
    approved = plan["execution"]["new_metadata_read"]
    actual = receipt["actual_tool_return"]
    check("receipt_numeric_exit_zero", type(actual["exit_code"]) is int and actual["exit_code"] == 0,
          actual["exit_code"], 0)
    check("receipt_initial_equals_actual", receipt["initial"] == actual, receipt["initial"] == actual, True)
    check("receipt_completion_is_null", receipt["completion"] is None, receipt["completion"], None)
    check("receipt_attempt_one_retry_zero",
          type(receipt["attempt"]) is int and type(receipt["retry"]) is int
          and (receipt["attempt"], receipt["retry"]) == (1, 0),
          [receipt["attempt"], receipt["retry"]], [1, 0])
    check("receipt_product_false", receipt["product_execution"] is False, receipt["product_execution"], False)
    check("actual_command_equals_approved_exact_transport",
          receipt["actual_command"] == approved["exact_transport_command"],
          sha(receipt["actual_command"].encode()), sha(approved["exact_transport_command"].encode()))
    check("approved_argv_source_equals_source", approved["argv"][2] == approved["source"],
          sha(approved["argv"][2].encode()), sha(approved["source"].encode()))
    expected_transport = ["env", "-i"] + [key + "=" + value for key, value in approved["finite_env"].items()] + approved["argv"]
    check("transport_argv_env_equals_declared_via_shlex_split",
          shlex.split(approved["exact_transport_command"]) == expected_transport,
          shlex.split(approved["exact_transport_command"]) == expected_transport, True)
    check("receipt_cwd_matches_approved", receipt["cwd"] == approved["cwd"], receipt["cwd"], approved["cwd"])
    output = actual["output"]
    payload = parse(output)
    check("output_JSON_single_complete_mapping",
          type(output) is str and "Warning: truncated output" not in output and type(payload) is dict,
          {"output_type": type(output).__name__, "payload_type": type(payload).__name__}, "complete single mapping")
    keys = {"path", "bytes", "sha256", "start_line", "end_line", "text", "product_execution"}
    check("payload_exact7keys", set(payload) == keys, sorted(payload), sorted(keys))
    check("payload_target_path_bytes_sha",
          type(payload["path"]) is str and type(payload["bytes"]) is int and type(payload["sha256"]) is str
          and (payload["path"], payload["bytes"], payload["sha256"]) == (str(INPUTS[4][0]), INPUTS[4][1], INPUTS[4][2]),
          {key: payload[key] for key in ["path", "bytes", "sha256"]}, pins[4])
    check("range_exact1_110_and_product_false",
          type(payload["start_line"]) is int and type(payload["end_line"]) is int
          and (payload["start_line"], payload["end_line"]) == (1, 110) and payload["product_execution"] is False,
          [payload["start_line"], payload["end_line"], payload["product_execution"]], [1, 110, False])
    lines = data[4].decode("utf-8").splitlines()
    check("target732lines", len(lines) == 732, len(lines), 732)
    expected = chr(10).join(str(index + 1) + ":" + line for index, line in enumerate(lines[:110]))
    text = payload["text"]
    check("decoded_text_exact_UTF8_numbered_lines_joined_by_chr10",
          type(text) is str and text == expected and text.encode("utf-8") == expected.encode("utf-8"),
          {"characters": len(text), "utf8_sha256": sha(text.encode("utf-8")), "LF_count": text.count(chr(10))},
          {"characters": len(expected), "utf8_sha256": sha(expected.encode("utf-8")), "LF_count": 109})
    check("raw_output_UTF8_bytes_at_most24000", len(output.encode("utf-8")) <= 24000,
          len(output.encode("utf-8")), "<=24000")
    expected_pin = {key: pins[2][key] for key in ["path", "bytes", "sha256"]}
    check("author_step_actual_chunk_exit_and_receipt_pin_match",
          actual["chunk_id"] == "f34a43" and step["actual_chunk"] == actual["chunk_id"]
          and type(step["actual_exit_code"]) is int and step["actual_exit_code"] == 0
          and step["actual_tool_return"] == expected_pin,
          {"chunk": step["actual_chunk"], "exit": step["actual_exit_code"], "pin": step["actual_tool_return"]},
          {"chunk": "f34a43", "exit": 0, "pin": expected_pin})
    budget = step["budget"]
    values = [budget[key] for key in ["new_metadata_read_used", "remaining", "parent_T2_commands_consumed", "retry"]]
    check("author_step_metadata_used1_remaining0_parent0",
          all(type(value) is int for value in values) and values == [1, 0, 0, 0], values, [1, 0, 0, 0])
except (OSError, UnicodeError, ValueError, KeyError, TypeError, IndexError) as error:
    check("METADATA_PARSING_OR_SHAPE_ERROR", False,
          {"type": type(error).__name__, "message": str(error)}, "valid exact metadata")

passed = len(checks) == 23 and all(item["passed"] for item in checks)
result = {"schema_version": "bigsmall.r213.validation-result.v1",
          "status": "PASSED" if passed else "FAILED", "checks": checks, "input_pins": pins,
          "expected_checks": 23, "actual_checks": len(checks), "product_execution": False,
          "old_reader_replayed": False, "old_checker_replayed": False}
result_path = HERE / "implementation/validation-result.json"
encoded = (json.dumps(result, ensure_ascii=False, indent=2) + chr(10)).encode("utf-8")
with result_path.open("xb") as stream:
    stream.write(encoded)
summary = {"status": result["status"], "checks": len(checks),
           "passed": sum(item["passed"] for item in checks),
           "result": {"path": str(result_path), "bytes": len(encoded), "sha256": sha(encoded)}}
rendered = json.dumps(summary, ensure_ascii=False)
if len((rendered + chr(10)).encode("utf-8")) > 2000:
    raise ValueError("bounded summary exceeded")
print(rendered)
signal.alarm(0)
sys.exit(0 if passed else 1)
