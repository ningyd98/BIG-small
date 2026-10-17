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
    provenance = []
    selection = "current" if match else None
    if not match and historical:
        provenance = archives.get((expected["path"], expected["bytes"], expected["sha256"]), [])
        match = bool(provenance)
        selection = "physical_archive" if match else None
    audit["records"].append({"label": label, "expected": expected, "actual": actual,
                             "archive_provenance": provenance, "selection": selection,
                             "matches": match})
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

def exact_record(value, label):
    if not isinstance(value, dict) or not all(key in value for key in PIN_KEYS):
        raise ValueError("missing pin schema: " + label)
    record = {key: value[key] for key in PIN_KEYS}
    if (not isinstance(record["path"], str) or not pathlib.Path(record["path"]).is_absolute()
            or type(record["bytes"]) is not int or record["bytes"] < 0
            or not isinstance(record["sha256"], str) or len(record["sha256"]) != 64
            or any(char not in "0123456789abcdef" for char in record["sha256"])):
        raise ValueError("invalid exact pin schema: " + label)
    return record

def required_pin(record, label):
    expected = exact_record(record, label)
    path = pathlib.Path(expected["path"])
    if not path.is_file() or path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("physical regular non-symlink file required: " + label)
    if not verify(expected, label):
        raise ValueError("required physical pin mismatch: " + label)
    return expected

def register_pair(original, archive, label):
    original = exact_record(original, label + ".original")
    archive = required_pin(archive, label + ".archive")
    equivalent = (original["bytes"], original["sha256"]) == (archive["bytes"], archive["sha256"])
    check(label + ".same_bytes_and_sha", equivalent)
    if not equivalent:
        raise ValueError("original/archive mismatch: " + label)
    key = tuple(original[k] for k in PIN_KEYS)
    for prior in archives.get(key, []):
        if raw(prior["archive"]["path"]) != raw(archive["path"]):
            raise ValueError("duplicate original tuple has unequal physical bytes: " + label)
    provenance = {"source": label, "original": original, "archive": archive}
    archives.setdefault(key, []).append(provenance)
    audit.setdefault("archive_registrations", []).append(provenance)

def register_pairs(value, label):
    if not isinstance(value, list):
        raise ValueError("archive pair list required: " + label)
    for index, pair in enumerate(value):
        if not isinstance(pair, dict) or "original" not in pair or "archive" not in pair:
            raise ValueError("unknown archive pair schema: " + label)
        register_pair(pair["original"], pair["archive"], label + "[" + str(index) + "]")

def pinned_document(path, size, digest, label):
    required_pin({"path": str(path), "bytes": size, "sha256": digest}, label)
    return document(path, label)

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
    register_pairs(before.get("archives"), "before_manifest.archives")
    register_pairs(gate.get("metadata_history_added"), "access_gate.metadata_history_added")
    authority = pinned_document(
        D196 / "implementation/root-final-software-evidence-acceptance-review-pending.json",
        5196, "c2650ff5e327a401374be5273c947b0f40e842df812ab51100a46dea38724d71", "acceptance")
    register_pairs(authority.get("metadata_history_added"), "acceptance.metadata_history_added")
    directory = D196 / "implementation/root_settlement"
    expected_pins = {
        "result.json": (78614, "1559376bee1c46fc06b59e1146b7b9495ca2652d9efd8a7622e35d7ad1680eb6"),
        "settlement.json": (96101, "f0450796d91eefb20ba82f09a3db519ccb858fb0025906339c00dbb3bc69a04e"),
        "tool-return.json": (84240, "8c3d87760e8d61f20509265ce121209277ac6754f8f8857cdf6387c3872e2883")}
    docs = {}
    for name, (size, digest) in expected_pins.items():
        docs[name] = pinned_document(directory / name, size, digest, name)
    result, settlement, receipt = (docs[n] for n in expected_pins)
    invocation_record = exact_record(result.get("invocation"), "result.invocation")
    invocation_expected = {"path": str(directory / "invocation.json"), "bytes": 841449,
                           "sha256": "f9ad9bb36b16f91591dc42b0934d5b0bd960a2ad6496c39c232aceb383f7cd91"}
    check("exact_result_invocation", invocation_record == invocation_expected)
    if invocation_record != invocation_expected:
        raise ValueError("unexpected result-linked invocation")
    required_pin(invocation_record, "invocation")
    invocation = document(invocation_record["path"], "root_invocation")
    bindings = {"activation": D196 / "root-activation.json",
                "author_ledger": D196 / "command-ledger.json",
                "gate": D196 / "script-gate.json",
                "root_ledger": D196 / "root-command-ledger.json"}
    before_metadata = invocation.get("before_metadata")
    if not isinstance(before_metadata, dict) or set(before_metadata) != set(bindings):
        raise ValueError("unknown invocation before_metadata schema")
    for name, original_path in bindings.items():
        record = before_metadata[name]
        physical = required_pin(record, "invocation.before_metadata." + name)
        if "base64" not in record:
            raise ValueError("missing physical archive base64: " + name)
        decoded = base64.b64decode(record["base64"], validate=True)
        if decoded != raw(physical["path"]):
            raise ValueError("physical archive/base64 bytes differ: " + name)
        original = dict(physical, path=str(original_path))
        register_pair(original, physical, "invocation.before_metadata." + name)
    archived_gate = pinned_document(directory / "gate-before.json", 576957,
        "cb7412e2963c98b8e51a6934e9ebe1e5b32df2a8a42056883e3a9a3130d9e302", "archived_gate")
    gate_original_key = (str(D196 / "script-gate.json"), 576957,
                        "cb7412e2963c98b8e51a6934e9ebe1e5b32df2a8a42056883e3a9a3130d9e302")
    authority_gate_pairs = [pair for pair in authority["metadata_history_added"]
                            if pair["original"]["path"] == str(D196 / "script-gate.json")]
    if (gate_original_key not in archives or not any(
            tuple(pair["original"][key] for key in PIN_KEYS) == gate_original_key
            for pair in authority_gate_pairs)):
        raise ValueError("archived gate must equal acceptance script-gate original generation")
    register_pairs(archived_gate.get("metadata_history"), "archived_gate.metadata_history")
    audit["archive_tuple_count"] = len(archives)
    audit["archive_relation_count"] = sum(len(values) for values in archives.values())
    for label, record in walk(authority, "acceptance"):
        verify(record, label, historical=True)
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
