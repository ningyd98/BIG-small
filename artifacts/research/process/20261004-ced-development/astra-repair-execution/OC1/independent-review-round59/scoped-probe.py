"""Independent OC1 public-API CPU probe; raw inputs, no factory/verdict mocks."""
from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
import os
import pickle
import re
import sys
import threading
import uuid
from dataclasses import asdict, replace
from pathlib import Path

from cloud_edge_robot_arm.research.operational_time_v1 import (
    OperationalBracket,
    OperationalTimeError,
    _StartupIdentity,
    _open_clock_for_test,
    _parse_namespace_offsets,
    _parse_process_start_ticks,
    open_operational_clock,
)

ROOT = Path.cwd()
BASE = ROOT / "artifacts/research/process/20261004-ced-development"
OC1 = BASE / "astra-repair-execution/OC1"
OUT = OC1 / "independent-review-round59"
PINNED = {
    "src/cloud_edge_robot_arm/research/operational_time_v1.py":
        "b1fa45a96837072d7bcf8cec57d1a7ae01dceeabec0131503b6aee5ab27dd90b",
    "tests/test_operational_time_v1.py":
        "ff226e9a616462c67d74d29931f8f9a7d21548f4f13f93ced64901b263229c0f",
}


def digest(path):
    value = path.read_bytes()
    return {"sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)}


def load_json(path):
    return json.loads(path.read_text())


def snapshot():
    return {path: digest(ROOT / path) for path in PINNED}


BEFORE = snapshot()
for path, expected in PINNED.items():
    assert BEFORE[path]["sha256"] == expected

identity = _StartupIdentity(
    boot_id="independent-raw-fixture",
    pid=os.getpid(),
    process_start_ticks=1,
    thread_id=threading.get_ident(),
    native_thread_id=threading.get_native_id(),
    namespace_device=1,
    namespace_inode=2,
    namespace_offsets=(("monotonic", 0, 0), ("boottime", 0, 0)),
    os_name="Linux",
    os_release="CPU-fixture",
    os_version="CPU-fixture",
    machine="CPU-fixture",
    python_version="CPU-fixture",
)


class RawSource:
    resolution_seconds = 1e-9

    def __init__(self, values):
        self.values = iter([0, *values])
        self.inputs = [0, *values]
        self.readings = []
        self.current_identity = identity

    def identity(self):
        return self.current_identity

    def read_ns(self):
        value = next(self.values)
        self.readings.append(value)
        return value


def clock(values):
    source = RawSource(values)
    owner = _open_clock_for_test(source)
    return owner, source


def event(owner):
    token = owner.begin_event("independent-CPU-event")
    owner.mark_event(token)
    return token, owner.end_event(token)


def error_chain(error):
    result = []
    while error is not None:
        result.append({"type": type(error).__name__, "message": str(error)})
        error = error.__cause__
    return result


def reject(operation):
    try:
        operation()
    except OperationalTimeError as error:
        return error_chain(error)
    raise AssertionError("public API unexpectedly granted capability")


scenarios = []


def add(name, source, result):
    scenarios.append({
        "name": name,
        "status": "PASS",
        "raw_counter_inputs_ns": source.inputs,
        "raw_counter_reads_ns": source.readings,
        "result": result,
    })


owner, source = clock([100, 150, 180, 200])
token = owner.begin_event("independent-overlap")
owner.mark_event(token)
current = owner.read_current(after=token)
origin = owner.end_event(token)
age = owner.age_bounds(origin, current)
assert asdict(age) == {"lower_ns": 0, "upper_ns": 80}
assert owner.within_age(origin, current, max_age_ns=80)
add("legal_MARK_current_END_overlap", source, {
    "event": [origin.lower_ns, origin.upper_ns],
    "current": [current.lower_ns, current.upper_ns],
    "age": asdict(age),
    "api_order": ["begin_event", "mark_event", "read_current", "end_event", "age_bounds"],
})

for base in (100, 2**60):
    for name, lower_delta, upper_delta, expected in (
        ("TTL_equal", 4_999_999_999, 5_000_000_000, True),
        ("TTL_plus_1ns", 5_000_000_000, 5_000_000_001, False),
        ("midpoint_would_misaccept", 4_999_998_900, 5_000_000_001, False),
    ):
        owner, source = clock([base, base + 100, base + lower_delta, base + upper_delta])
        token, origin = event(owner)
        current = owner.read_current(after=token)
        age = owner.age_bounds(origin, current)
        actual = owner.within_age(origin, current)
        assert actual is expected and age.upper_ns == upper_delta
        if name == "midpoint_would_misaccept":
            assert age.lower_ns + age.upper_ns < 2 * 5_000_000_000
        add(f"{name}_base_{base}", source, {
            "age": asdict(age), "expected_within_age": expected, "actual_within_age": actual,
            "max_age_ns": 5_000_000_000,
        })

for base in (100, 2**60):
    deadline_ns = base + 5_000_000_000
    for delta, expected in ((-1, True), (0, False), (1, False)):
        upper = deadline_ns + delta
        owner, source = clock([base, base + 100, upper - 1, upper])
        token, origin = event(owner)
        deadline = owner.start_deadline(
            task_key="original-attempt", origin=origin, budget_ns=5_000_000_000
        )
        current = owner.read_current(after=token)
        actual = owner.before_deadline(deadline, current)
        assert deadline.deadline_ns == deadline_ns and actual is expected
        add(f"deadline_delta_{delta}_base_{base}", source, {
            "deadline_ns": deadline.deadline_ns, "current_upper_ns": current.upper_ns,
            "expected_before_deadline": expected, "actual_before_deadline": actual,
        })

owner, source = clock([
    100, 200, 4_900_000_099, 4_900_000_100,
    5_050_000_100, 5_050_000_200, 5_100_000_099, 5_100_000_100,
])
token, origin = event(owner)
deadline = owner.start_deadline(task_key="fixed-key", origin=origin, budget_ns=5_000_000_000)
assert owner.start_deadline(
    task_key="fixed-key", origin=origin, budget_ns=5_000_000_000
) is deadline
early = owner.before_deadline(deadline, owner.read_current(after=token))
_, new_origin = event(owner)
changed_origin = reject(lambda: owner.start_deadline(
    task_key="fixed-key", origin=new_origin, budget_ns=5_000_000_000
))
changed_budget = reject(lambda: owner.start_deadline(
    task_key="fixed-key", origin=origin, budget_ns=5_000_000_001
))
late = owner.before_deadline(deadline, owner.read_current(after=token))
assert early is True and late is False and deadline.deadline_ns == 5_000_000_100
add("fixed_key_never_refreshes", source, {
    "same_key_returns_exact_original": True, "early": early, "late": late,
    "deadline_ns": deadline.deadline_ns,
    "changed_origin_error": changed_origin, "changed_budget_error": changed_budget,
})

owner, source = clock([100, 200, 300, 400])
token, origin = event(owner)
current = owner.read_current(after=token)
deadline = owner.start_deadline(task_key="copy-check", origin=origin, budget_ns=500)
foreign, foreign_source = clock([100, 200, 300, 400])
foreign_token, foreign_origin = event(foreign)
foreign_current = foreign.read_current(after=foreign_token)
assert replace(owner.domain, startup_nonce=foreign.domain.startup_nonce) == foreign.domain
foreign_errors = [
    reject(lambda: owner.age_bounds(foreign_origin, current)),
    reject(lambda: owner.age_bounds(origin, foreign_current)),
    reject(lambda: owner.mark_event(foreign_token)),
]
reconstructed = replace(origin)
assert reconstructed is not origin
reconstruction_error = reject(lambda: owner.age_bounds(reconstructed, current))
copy_errors = {}
for handle_name, handle in (
    ("owner", owner), ("token", token), ("event", origin),
    ("current", current), ("deadline", deadline),
):
    for operation in (copy.copy, copy.deepcopy, pickle.dumps):
        copy_errors[f"{handle_name}.{operation.__name__}"] = reject(
            lambda operation=operation, handle=handle: operation(handle)
        )
add("foreign_reconstructed_copy_deepcopy_pickle_rejected", source, {
    "equal_descriptor_except_unique_startup_nonce": True,
    "foreign_raw_counter_inputs_ns": foreign_source.inputs,
    "foreign_raw_counter_reads_ns": foreign_source.readings,
    "foreign_errors": foreign_errors, "reconstruction_error": reconstruction_error,
    "copy_errors": copy_errors,
})

owner, source = clock([100, 200, 300, 400])
token = owner.begin_event("missing-pair")
current_before_mark = reject(lambda: owner.read_current(after=token))
end_before_mark = reject(lambda: owner.end_event(token))
owner.mark_event(token)
current = owner.read_current(after=token)
fabricated = OperationalBracket(owner.domain, token.event_identity, 100, 100)
incomplete_receipt = reject(lambda: owner.age_bounds(fabricated, current))
origin = owner.end_event(token)
assert owner.age_bounds(origin, current).upper_ns == 200
add("missing_MARK_END_pair_rejected_then_complete_overlap_valid", source, {
    "current_before_MARK_error": current_before_mark,
    "END_before_MARK_error": end_before_mark,
    "fabricated_incomplete_receipt_error": incomplete_receipt,
    "complete_age": asdict(owner.age_bounds(origin, current)),
})

owner, source = clock([100, 200, 300, 299])
token, origin = event(owner)
decrease = reject(lambda: owner.read_current(after=token))
assert decrease[-1]["message"] == "operational counter decreased"
closed = reject(lambda: owner.begin_event("after-decrease"))
assert closed[0]["message"] == "operational owner is not live"
add("decreasing_clock_revokes_with_actual_cause", source, {
    "decrease_error": decrease, "later_closed_error": closed,
})

owner, source = clock([100, 200, 300, 400, 500, 600])
_, origin = event(owner)
other_token, other_origin = event(owner)
current = owner.read_current(after=other_token)
wrong_link = reject(lambda: owner.age_bounds(origin, current))
assert wrong_link[0]["message"] == "receipt pair lacks event-before-current causality"
assert owner.age_bounds(other_origin, current).upper_ns == 300
add("wrong_direct_causal_link_rejected", source, {"wrong_link_error": wrong_link})

owner, source = clock([100, 200, 300, 400])
token, origin = event(owner)
current = owner.read_current(after=token)
source.current_identity = replace(
    identity, namespace_offsets=(("monotonic", 0, 0), ("boottime", 1, 0))
)
drift = reject(lambda: owner.age_bounds(origin, current))
source.current_identity = identity
revoked = reject(lambda: owner.age_bounds(origin, current))
assert drift[-1]["message"] == "process, boot, thread or time namespace changed"
assert revoked[0]["message"] == "operational owner is not live"
add("namespace_offset_drift_permanently_revokes", source, {
    "identity_before": asdict(identity),
    "identity_during_drift": asdict(replace(
        identity, namespace_offsets=(("monotonic", 0, 0), ("boottime", 1, 0))
    )),
    "drift_error": drift, "restored_identity_still_closed_error": revoked,
})

assert not inspect.signature(open_operational_clock).parameters
source_flag_errors = {}
for name in ("clock", "ns", "domain", "source", "pid", "source_flags", "accuracy", "_source"):
    try:
        open_operational_clock(**{name: 0})
    except TypeError as error:
        source_flag_errors[name] = error_chain(error)
    else:
        raise AssertionError("zero-parameter factory accepted caller source")

# Recompute narrowly permitted AST differences without running old test/source bytes.
def tree(path):
    return ast.parse(path.read_text())


def function(module, name):
    return next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == name)


src_path = Path(next(path for path in PINNED if path.startswith("src/")))
before_source = tree(OC1 / "static-fix/before" / src_path)
after_source = tree(ROOT / src_path)
before_typing = next(n for n in before_source.body if isinstance(n, ast.ImportFrom) and n.module == "typing")
after_typing = next(n for n in after_source.body if isinstance(n, ast.ImportFrom) and n.module == "typing")
assert [n.name for n in before_typing.names] == ["Protocol"]
assert [n.name for n in after_typing.names] == ["NoReturn", "Protocol", "SupportsIndex"]
after_typing.names = copy.deepcopy(before_typing.names)
before_live = next(n for n in before_source.body if isinstance(n, ast.ClassDef) and n.name == "_LiveHandle")
after_live = next(n for n in after_source.body if isinstance(n, ast.ClassDef) and n.name == "_LiveHandle")
before_reduce = next(n for n in before_live.body if isinstance(n, ast.FunctionDef) and n.name == "__reduce_ex__")
after_reduce = next(n for n in after_live.body if isinstance(n, ast.FunctionDef) and n.name == "__reduce_ex__")
assert ast.dump(before_reduce.args.args[1].annotation) == "Name(id='int', ctx=Load())"
assert ast.dump(after_reduce.args.args[1].annotation) == "Name(id='SupportsIndex', ctx=Load())"
assert ast.dump(before_reduce.returns) == "Name(id='object', ctx=Load())"
assert ast.dump(after_reduce.returns) == "Name(id='NoReturn', ctx=Load())"
after_reduce.args.args[1].annotation = copy.deepcopy(before_reduce.args.args[1].annotation)
after_reduce.returns = copy.deepcopy(before_reduce.returns)
assert ast.dump(before_source) == ast.dump(after_source)

test_path = Path("tests/test_operational_time_v1.py")
before_test = tree(OC1 / "static-fix/before" / test_path)
static_after_test = tree(OC1 / "static-fix/after" / test_path)
for module in (before_test, static_after_test):
    target = next(n for n in module.body if isinstance(n, ast.ImportFrom) and
                  n.module == "cloud_edge_robot_arm.research.operational_time_v1")
    target.names.sort(key=lambda alias: alias.name)
assert ast.dump(before_test) == ast.dump(static_after_test)

before_output = tree(OC1 / "test-output-fix/before" / test_path)
after_output = tree(ROOT / test_path)
bf = function(before_output, "test_real_linux_startup_factory_cpu_only")
af = function(after_output, "test_real_linux_startup_factory_cpu_only")
assert not bf.args.args and len(af.args.args) == 1
assert af.args.args[0].arg == "tmp_path"
assert ast.dump(af.args.args[0].annotation) == "Name(id='Path', ctx=Load())"
assert ast.dump(af.body[0].value) == (
    "BinOp(left=Name(id='tmp_path', ctx=Load()), op=Div(), "
    "right=Constant(value='real-startup-cpu.json'))"
)
assert sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and
           n.func.attr == "write_text" and isinstance(n.func.value, ast.Name) and
           n.func.value.id == "artifact" for n in ast.walk(af)) == 2
af.args = copy.deepcopy(bf.args)
af.body[0] = copy.deepcopy(bf.body[0])
assert ast.dump(before_output) == ast.dump(after_output)

plans = {}
for name in ("round57-operational-oc1", "round58-oc1-static", "round59-oc1-test-output"):
    folder = BASE / "astra-rounds" / name
    plan = load_json(folder / "plan.json")
    assert digest(folder / "plan.md")["sha256"] == plan["plan_markdown_sha256"]
    plans[name] = {"md": digest(folder / "plan.md"), "json": digest(folder / "plan.json")}

plan59 = load_json(BASE / "astra-rounds/round59-oc1-test-output/plan.json")
protected_expected = {
    **plan59["protected_implementation_files"], **plan59["protected_static_fix_files"]
}
protected_before = load_json(OC1 / "test-output-fix/protected-before.json")
root_pins = load_json(OUT / "pins-before-after.json")
assert len(protected_expected) == len(protected_before) == root_pins["protected_count"] == 70
assert len({item["path"] for item in protected_before}) == 70
for item in protected_before:
    assert {"sha256": item["sha256"], "bytes": item["bytes"]} == protected_expected[item["path"]]
assert root_pins["protected_files"] == protected_before
protected_actual = {path: digest(ROOT / path) for path in protected_expected}
assert protected_actual == protected_expected
assert root_pins["all_protected_originals_unchanged"] is True
assert root_pins["source_and_test_unchanged_during_run"] is True

command = load_json(OUT / "full60-command.json")
stdout = (OUT / "full60.stdout.txt").read_text()
assert command["exit_code"] == 0
assert command["stdout"] == stdout and command["stderr"] == ""
assert re.search(r"^60 passed in 0\.11s$", stdout, re.MULTILINE)
assert command["source_sha256"] == PINNED[str(src_path)]
assert command["test_sha256"] == PINNED[str(test_path)]
assert command["env_flags"] == {"PYTHONPATH": "src:.", "PYTHONDONTWRITEBYTECODE": "1"}
assert command["command"] == [
    ".venv/bin/python", "-m", "pytest", "-q", "-p", "no:cacheprovider",
    "--basetemp=" + command["basetemp"], str(test_path),
]
receipt_copy = load_json(OUT / "receipt-copy.json")
receipt_path = OUT / "real-startup-cpu.json"
receipt_original = Path(receipt_copy["source"])
receipt = load_json(receipt_path)
old_receipt = load_json(OC1 / "implementation/logs/real-startup-cpu.json")
assert receipt_original.read_bytes() == receipt_path.read_bytes()
assert digest(receipt_path) == {"sha256": receipt_copy["sha256"], "bytes": receipt_copy["bytes"]}
assert receipt_original.is_relative_to(Path(command["basetemp"]))
unique_tmp_receipts = {path.resolve() for path in Path(command["basetemp"]).rglob("real-startup-cpu.json")}
assert unique_tmp_receipts == {receipt_original.resolve()}
assert set(receipt) == set(old_receipt) and set(receipt["domain"]) == set(old_receipt["domain"])
assert receipt["status"] == "PASS_REAL_LINUX_STARTUP_CPU_ONLY"
assert receipt["scope"] == receipt["domain"]["scope"] == "SOFTWARE_ONLY"
d = receipt["domain"]
assert d["schema"] == "simulation.operational-time.v1"
assert d["api"] == "Linux time.clock_gettime_ns(time.CLOCK_BOOTTIME)"
assert d["utc_accuracy"] is d["si_accuracy"] is None
assert d["accuracy_status"] == "UNVERIFIED" and d["future_horizon"] == "UNKNOWN"
assert d["native_authority"] == d["worker_authority"] == d["lease_authority"] == "UNAVAILABLE"
assert d["restart_suspend_hostpause"] == receipt["restart_suspend_hostpause"] == "NOT_TESTED_OC3_GATE"
assert receipt["formal_accepted"] is False
assert receipt["real_counter_reads"] == 5
assert receipt["physics_provider_renderer_camera_decoder_hardware_actual"] == 0
uuid.UUID(d["boot_id"])
for key in ("pid", "process_start_ticks", "owner_thread_id", "owner_native_thread_id", "namespace_inode"):
    assert type(d[key]) is int and d[key] > 0
for pair in ("event", "current", "age"):
    assert set(receipt[pair]) == {"lower_ns", "upper_ns"}
    assert all(type(value) is int and value >= 0 for value in receipt[pair].values())
    assert receipt[pair]["lower_ns"] <= receipt[pair]["upper_ns"]
e, n, a = receipt["event"], receipt["current"], receipt["age"]
assert a == {"lower_ns": max(0, n["lower_ns"] - e["upper_ns"]),
             "upper_ns": n["upper_ns"] - e["lower_ns"]}
assert d["startup_counter_ns"] <= e["lower_ns"] <= e["upper_ns"] <= n["lower_ns"] <= n["upper_ns"]
namespace = os.stat("/proc/thread-self/ns/time")
host = {
    "inspection_pid": os.getpid(),
    "inspection_process_start_ticks": _parse_process_start_ticks(
        Path("/proc/self/stat").read_text(), expected_pid=os.getpid()
    ),
    "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
    "namespace_device": namespace.st_dev,
    "namespace_inode": namespace.st_ino,
    "namespace_offsets": _parse_namespace_offsets(Path("/proc/self/timens_offsets").read_text()),
    "os_uname": list(os.uname()),
    "python_version": sys.version,
    "test_pid_and_start_ticks_checked_contemporaneously_by_reviewed_test_assertions": True,
    "inspection_is_not_a_recheck_of_exited_pytest_process": True,
    "real_BOOTTIME_reader_calls_by_this_script": 0,
}
assert host["boot_id"] == d["boot_id"]
assert (host["namespace_device"], host["namespace_inode"]) == (d["namespace_device"], d["namespace_inode"])
assert [list(row) for row in host["namespace_offsets"]] == d["namespace_offsets"]

AFTER = snapshot()
assert AFTER == BEFORE
assert {path: digest(ROOT / path) for path in protected_expected} == protected_expected
result = {
    "schema_version": "ced.oc1.independent-public-api-probe.round59.v1",
    "status": "PASS_SCOPED_PUBLIC_API_CPU_PROBE",
    "probe_runs": 1,
    "scenarios": scenarios,
    "scenario_count": len(scenarios),
    "fixture_identity": asdict(identity),
    "factory_signature_empty": True,
    "factory_caller_kwargs_rejected_before_body": source_flag_errors,
    "real_factory_runs_by_this_script": 0,
    "real_counter_reads_by_this_script": 0,
    "public_API_verdicts_mocked": False,
    "private_seam_controls": ["raw_counter_ns", "startup_identity"],
    "source_before": BEFORE,
    "source_after": AFTER,
    "source_pins_unchanged": True,
    "plans_verified": plans,
    "AST_recomputed": {
        "round58_source_only_exact_typing_and_reduce_ex_annotations": True,
        "round58_test_only_target_ImportFrom_order": True,
        "round59_only_tmp_path_parameter_and_artifact_assignment": True,
        "round59_shared_artifact_write_calls": 2,
    },
    "protected_count": 70,
    "protected_current_equals_round59_plan_and_root_before_after": True,
    "protected_current": protected_actual,
    "protection_scope": "Only 41 OC1 implementation and 29 OC1 static-fix artifact files; not all repository sources or old actual raw bytes.",
    "full60_shared_root_run": {"exit_code": 0, "passed": 60, "failed": 0, "skipped": 0,
                              "reported_seconds": "0.11", "rerun_by_this_script": False},
    "receipt": {"schema_matches_original": True, "copied_exact_bytes": True,
                "unique_real_tmp_file": True, "math_verified": True,
                "pin": digest(receipt_path), "host_identity_corroboration": host},
    "actual_calls": {"network": 0, "model": 0, "physics": 0, "renderer": 0, "camera": 0,
                     "decoder": 0, "hardware": 0, "provider": 0, "suspend": 0,
                     "fork": 0, "host_clock_adjustment": 0},
    "unique_pytest_denominator": 60,
    "probe_scenarios_are_not_additional_pytest_or_calibration_groups": True,
    "formal_accepted": False,
    "scope": "SOFTWARE_ONLY",
}
destination = OUT / "scoped-probe.json"
with destination.open("x", encoding="utf-8") as file:
    file.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": result["status"], "scenarios": len(scenarios),
                  "protected_files_verified": 70, "real_factory_runs": 0,
                  "source_pins_unchanged": True}))
