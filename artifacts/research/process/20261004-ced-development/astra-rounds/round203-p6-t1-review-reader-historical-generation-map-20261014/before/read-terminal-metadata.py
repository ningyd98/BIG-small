"""R202 batch24: bounded stdlib evidence read; never executes product code."""
import base64
import hashlib
import json
import pathlib
import signal
import sys

signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("120 second read cap")))
signal.alarm(120)
ROOT = pathlib.Path("/home/ningyd/文档/ChatGPT/BIGsmall")
BASE = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds"
D196 = BASE / "round196-p6-t1-local-promotion-original-task-bindings-20261014"
D202 = BASE / "round202-p6-t1-review-final-batch-truncated-json-20261014"
TARGET = D202 / "review/terminal-metadata-check.json"
PIN_KEYS = ("path", "bytes", "sha256")
audit = {"schema_version": "bigsmall.r202-terminal-metadata-check.v1",
         "batch": 24, "records": [], "documents": {}, "checks": [],
         "errors": [], "independent_tool_stdout": None, "independent_tool_stderr": None}
cache = {}
archives = {}

def check(name, passed, actual=None, expected=None):
    item = {"name": name, "passed": bool(passed), "actual": actual, "expected": expected}
    audit["checks"].append(item)
    if not passed:
        audit["errors"].append(item)

def raw(path):
    path = pathlib.Path(path)
    key = str(path)
    if key not in cache:
        if path.is_symlink():
            raise ValueError("symlink input: " + key)
        cache[key] = path.read_bytes()
    return cache[key]

def pin(path):
    data = raw(path)
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

def verify(record, label, historical=False):
    expected = {key: record[key] for key in PIN_KEYS}
    actual = pin(expected["path"])
    match = actual == expected
    archive = None
    if not match and historical:
        archive = archives.get((expected["path"], expected["bytes"], expected["sha256"]))
        match = archive is not None
    audit["records"].append({"label": label, "expected": expected, "actual": actual,
                             "archive": archive, "matches": match})
    check(label, match)
    return match

def document(path, label):
    value = json.loads(raw(path))
    audit["documents"][label] = {"pin": pin(path), "value": value}
    return value

def walk(value, label):
    if isinstance(value, dict):
        if all(key in value for key in PIN_KEYS):
            yield label, value
        for key, child in value.items():
            if key != "base64":
                yield from walk(child, label + "." + key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, label + "[" + str(index) + "]")

def archives_from(value, label):
    if isinstance(value, dict):
        original = value.get("original")
        archive = value.get("archive")
        if isinstance(original, dict) and isinstance(archive, dict) and all(k in original and k in archive for k in PIN_KEYS):
            verify(archive, label + ".archive")
            check(label + ".archive_bytes", (original["bytes"], original["sha256"]) ==
                  (archive["bytes"], archive["sha256"]))
            archives[tuple(original[k] for k in PIN_KEYS)] = archive
        if all(k in value for k in ("base64", "bytes", "sha256")):
            data = base64.b64decode(value["base64"], validate=True)
            check(label + ".base64", len(data) == value["bytes"] and
                  hashlib.sha256(data).hexdigest() == value["sha256"])
        for key, child in value.items():
            if key != "base64":
                archives_from(child, label + "." + key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            archives_from(child, label + "[" + str(index) + "]")

try:
    if TARGET.exists():
        raise FileExistsError(str(TARGET))
    plan = document(D202 / "plan.json", "R202_plan")
    gate = document(D196 / "review/access-gate.json", "access_gate")
    inputs = gate.get("inputs")
    check("exact_313_inputs", isinstance(inputs, list) and len(inputs) == 313,
          len(inputs) if isinstance(inputs, list) else None, 313)
    if isinstance(inputs, list):
        for index, record in enumerate(inputs):
            verify(record, "current_input_" + str(index))
    oldplan = document(D196 / "plan.json", "R196_plan")
    before = document(D196 / "implementation/before/manifest.json", "before_manifest")
    archives_from(before, "before_manifest")
    archives_from(gate, "access_gate")
    authority = document(D196 / "implementation/root-final-software-evidence-acceptance-review-pending.json", "acceptance")
    check("acceptance_fixed_pin", pin(D196 / "implementation/root-final-software-evidence-acceptance-review-pending.json")["sha256"] ==
          "c2650ff5e327a401374be5273c947b0f40e842df812ab51100a46dea38724d71")
    for label, record in walk(authority, "acceptance"):
        verify(record, label, historical=True)
    directory = D196 / "implementation/root_settlement"
    expected_pins = {
        "result.json": (78614, "1559376bee1c46fc06b59e1146b7b9495ca2652d9efd8a7622e35d7ad1680eb6"),
        "settlement.json": (96101, "f0450796d91eefb20ba82f09a3db519ccb858fb0025906339c00dbb3bc69a04e"),
        "tool-return.json": (84240, "8c3d87760e8d61f20509265ce121209277ac6754f8f8857cdf6387c3872e2883")}
    docs = {}
    for name, (size, digest) in expected_pins.items():
        verify({"path": str(directory / name), "bytes": size, "sha256": digest}, name)
        docs[name] = document(directory / name, name)
    result, settlement, receipt = (docs[n] for n in expected_pins)
    check("root_result_terminal", result.get("exit_code") == 0 and result.get("failures") == [] and
          result.get("test_execution") is False and result.get("product_commands") == 0)
    check("settlement_terminal", settlement.get("status") == "SOFTWARE_EVIDENCE_ACCEPTED_REVIEW_PENDING" and settlement.get("failures") == [])
    check("receipt_full_summary", receipt.get("actual_summary") == result)
    actual = receipt.get("completion") or receipt.get("initial")
    check("actual_numeric_exit", isinstance(actual, dict) and type(actual.get("exit_code")) is int and actual.get("exit_code") == 0)
    check("receipt_no_retry", receipt.get("attempt") == 1 and receipt.get("retry") == 0)
    for label, record in walk(receipt.get("outer_streams"), "root_streams"):
        verify(record, label)
    for label, record in walk(settlement, "settlement"):
        verify(record, label, historical=True)
    observations = settlement.get("observations", {})
    for name, expected in (("new_RED8", {"tests": 8, "passes": 1, "failures": 7, "errors": 0, "skips": 0}),
                           ("new_GREEN63", {"tests": 63, "passes": 63, "failures": 0, "errors": 0, "skips": 0})):
        value = observations.get(name, {})
        check(name + "_JUnit", value.get("JUnit") == expected, value.get("JUnit"), expected)
        resources = value.get("resources", {})
        target = 32 if name == "new_RED8" else 252
        counts = resources.get("counts", {})
        check(name + "_actual_close_totals", counts.get("initialized") == target and
              counts.get("initialized_successfully_closed") == target and counts.get("close_errors") == 0,
              counts, {"initialized": target, "initialized_successfully_closed": target, "close_errors": 0})
    ruff = observations.get("new_ruff", {})
    check("ruff_exits", ruff.get("child_exit") == 0 and ruff.get("wrapper_exit") == 0)
    roles = document(D196 / "root-command-ledger.json", "root_roles")
    command_names = {"prepare_red", "red8", "prepare_green", "ruff", "green63", "root_settlement"}
    def role_sets(value):
        if isinstance(value, dict):
            if command_names <= set(value):
                yield value
            for child in value.values():
                yield from role_sets(child)
        elif isinstance(value, list):
            for child in value:
                yield from role_sets(child)
    matches = list(role_sets(roles))
    check("six_command_role_container_found", bool(matches))
    for index, values in enumerate(matches):
        for name in sorted(command_names):
            role = values[name]
            check("role_" + str(index) + "_" + name,
                  isinstance(role, dict) and role.get("used") == 1 and role.get("remaining") == 0 and role.get("attempts") == 1,
                  role)
    check("no_T1_promotion", result.get("T1_complete", False) is False and settlement.get("T1_complete", False) is False)
except Exception as error:
    audit["errors"].append({"exception_type": type(error).__name__, "message": str(error)})
audit["status"] = "PASS" if not audit["errors"] else "MISMATCH_STOP"
audit["read_only_product_scope"] = True
data = (json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
summary = {"status": audit["status"], "output": {"path": str(TARGET), "bytes": len(data),
           "sha256": hashlib.sha256(data).hexdigest()}, "checks": len(audit["checks"]),
           "records": len(audit["records"]), "errors": len(audit["errors"]),
           "error_names": [str(e.get("name", e.get("exception_type", "unknown")))[:80] for e in audit["errors"][:20]]}
text = json.dumps(summary, ensure_ascii=False, sort_keys=True) + "\n"
if len(text.encode()) > 6000:
    raise ValueError("summary exceeded 6000 bytes")
with TARGET.open("xb") as stream:
    stream.write(data)
sys.stdout.write(text)
signal.alarm(0)
sys.exit(0 if not audit["errors"] else 1)
