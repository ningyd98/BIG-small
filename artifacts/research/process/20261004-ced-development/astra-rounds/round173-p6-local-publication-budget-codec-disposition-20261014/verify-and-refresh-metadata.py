from pathlib import Path
import json
import hashlib
import base64
import difflib
import signal

def _r173_timeout(_signum, _frame):
    raise TimeoutError("R173 metadata action exceeded the authorized 120-second limit")

signal.signal(signal.SIGALRM, _r173_timeout)
signal.alarm(120)

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
PROCESS = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds"
ROUND = PROCESS / "round158-p6-stage-b-local-temporal-publication-20261013"
TASK = ROUND / "implementation/t1"
D166 = PROCESS / "round166-p6-t1-legacy-supervision-claim-timing-20261013"
D170 = PROCESS / "round170-p6-detached-real-broker-receipt-closure-20261013"
D172 = PROCESS / "round172-p6-t1-freeze-metadata-assertion-20261014"
D173 = PROCESS / "round173-p6-local-publication-budget-codec-disposition-20261014"
CHANGES = [
  {
    "path": "/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/repositories/event_autonomy/visual_owner.py",
    "before": "if TYPE_CHECKING:\n    from cloud_edge_robot_arm.edge.recovery.lifecycle import VerificationBudgetRecord\n",
    "after": "if TYPE_CHECKING:\n    from cloud_edge_robot_arm.edge.recovery.lifecycle import (\n        LocalRetryBudgetRecord,\n        LocalVerificationBudgetRecord,\n        VerificationBudgetRecord,\n    )\n"
  },
  {
    "path": "/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/repositories/event_autonomy/visual_owner.py",
    "before": "    @property\n    def verification_budget(self) -> VerificationBudgetRecord:\n        from cloud_edge_robot_arm.edge.recovery.lifecycle import VerificationBudgetRecord\n\n        return VerificationBudgetRecord.from_payload(self.object(\"verification_budget\"))\n\n    @property\n    def retry_budget(self) -> RecoveryBudget:\n        return self.model(\"retry_budget\", RecoveryBudget)\n",
    "after": "    @property\n    def verification_budget(self) -> VerificationBudgetRecord:\n        from cloud_edge_robot_arm.edge.recovery.lifecycle import VerificationBudgetRecord\n\n        payload = self.object(\"verification_budget\")\n        if payload.get(\"schema_version\") == \"recovery.verification-budget.local.v1\":\n            raise ValueError(\"local verification budget requires verification_budget_history\")\n        return VerificationBudgetRecord.from_payload(payload)\n\n    @property\n    def verification_budget_history(self) -> VerificationBudgetRecord | LocalVerificationBudgetRecord:\n        from cloud_edge_robot_arm.edge.recovery.lifecycle import (\n            LocalVerificationBudgetRecord,\n            VerificationBudgetRecord,\n        )\n\n        payload = self.object(\"verification_budget\")\n        tag = payload.get(\"schema_version\")\n        if tag == \"recovery.verification-budget.local.v1\":\n            return LocalVerificationBudgetRecord.from_payload(payload)\n        if tag == \"recovery.verification-budget.v1\":\n            return VerificationBudgetRecord.from_payload(payload)\n        raise ValueError(\"unsupported verification budget history schema\")\n\n    @property\n    def retry_budget(self) -> RecoveryBudget:\n        if self.object(\"retry_budget\").get(\"schema_version\") == \"recovery.retry-budget.local.v1\":\n            raise ValueError(\"local retry budget requires retry_budget_history\")\n        return self.model(\"retry_budget\", RecoveryBudget)\n\n    @property\n    def retry_budget_history(self) -> RecoveryBudget | LocalRetryBudgetRecord:\n        from cloud_edge_robot_arm.edge.recovery.lifecycle import LocalRetryBudgetRecord\n\n        payload = self.object(\"retry_budget\")\n        if \"schema_version\" in payload:\n            if payload[\"schema_version\"] == \"recovery.retry-budget.local.v1\":\n                return LocalRetryBudgetRecord.from_payload(payload)\n            raise ValueError(\"unsupported retry budget history schema\")\n        return self.model(\"retry_budget\", RecoveryBudget)\n"
  },
  {
    "path": "/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/edge/recovery/lifecycle.py",
    "before": "from cloud_edge_robot_arm.vision.local_temporal import (\n    LocalDomainEnvelope,\n    LocalVerificationBudgetState,\n)\n",
    "after": "from cloud_edge_robot_arm.vision.local_temporal import (\n    JSONValue,\n    LocalDomainEnvelope,\n    LocalVerificationBudgetState,\n)\n"
  },
  {
    "path": "/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/edge/recovery/lifecycle.py",
    "before": "    def content_hash(self) -> str:\n        return self.string(\"content_hash\")\n\n\n# Keep the ten roadmap fields positional; binding/CAS metadata is keyword-only.\n",
    "after": "    def content_hash(self) -> str:\n        return self.string(\"content_hash\")\n\n\nclass LocalRetryBudgetRecord(LocalDomainEnvelope):\n    \"\"\"Immutable retry history; decoding cannot create or replenish a live budget.\"\"\"\n\n    _tag = \"recovery.retry-budget.local.v1\"\n\n    @property\n    def budget_id(self) -> str:\n        return self.string(\"budget_id\")\n\n    @property\n    def task_id(self) -> str:\n        return self.string(\"task_id\")\n\n    @property\n    def per_step_retry_limit(self) -> int:\n        return self.counter(\"per_step_retry_limit\")\n\n    @property\n    def per_skill_retry_limit(self) -> int:\n        return self.counter(\"per_skill_retry_limit\")\n\n    @property\n    def task_total_retry_limit(self) -> int:\n        return self.counter(\"task_total_retry_limit\")\n\n    @property\n    def retry_count_used(self) -> int:\n        return self.counter(\"retry_count_used\")\n\n    @property\n    def task_retry_count(self) -> int:\n        return self.counter(\"task_retry_count\")\n\n    def _retry_counts(self, name: str) -> dict[str, int]:\n        result: dict[str, int] = {}\n        for key, value in self.object(name).items():\n            if type(value) is not int or value < 0:\n                raise ValueError(\"strict nonnegative retry history counter required\")\n            result[key] = value\n        return result\n\n    @property\n    def step_retry_counts(self) -> dict[str, int]:\n        return self._retry_counts(\"step_retry_counts\")\n\n    @property\n    def skill_retry_counts(self) -> dict[str, int]:\n        return self._retry_counts(\"skill_retry_counts\")\n\n    @property\n    def event_retry_counts(self) -> dict[str, int]:\n        return self._retry_counts(\"event_retry_counts\")\n\n    @property\n    def retry_cooldown_ms(self) -> int:\n        return self.counter(\"retry_cooldown_ms\")\n\n    @property\n    def retry_backoff_policy(self) -> str:\n        return self.string(\"retry_backoff_policy\")\n\n    @property\n    def effective_retry_limit(self) -> int:\n        return self.counter(\"effective_retry_limit\")\n\n    @property\n    def remaining_retries(self) -> int:\n        return self.counter(\"remaining_retries\")\n\n    @property\n    def scene_version(self) -> int:\n        return self.counter(\"scene_version\")\n\n    @property\n    def original_recovery_reference(self) -> dict[str, JSONValue]:\n        reference = self.local_time.to_payload()[\"recovery_reference\"]\n        if not isinstance(reference, dict):\n            raise ValueError(\"original recovery reference must be a JSON object\")\n        return dict(reference)\n\n\n# Keep the ten roadmap fields positional; binding/CAS metadata is keyword-only.\n"
  }
]
SETTLED_REPORT_PINS = [
  {
    "bytes": 2056972,
    "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/implementation/t1/semantic.json",
    "sha256": "2828bf09bff3aec246fdda2a5af56ca3565e4e7406235e0150a79f935ab8b3f3"
  },
  {
    "bytes": 953,
    "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/implementation/t1/semantic.md",
    "sha256": "41d689ced97368a38889cf7a7c2ec764fd5aa7844a1857908f83d9978f7280d2"
  },
  {
    "bytes": 74075,
    "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/implementation/t1/final-freeze.json",
    "sha256": "34d3da0b33a17750d8d5a85bdf12e401be3493e3e7bb5728d837ced2d2524333"
  },
  {
    "bytes": 957,
    "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/implementation/t1/final-freeze.md",
    "sha256": "237aee4a6377722e3d4c03b008acb78aaec7806cff224769cd5e4d18052ecb18"
  },
  {
    "bytes": 20572,
    "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/implementation/t1/change-report.json",
    "sha256": "252233cf1173d3d014c9783ae33e245712b5103120dfa95b6e40be63f378900b"
  },
  {
    "bytes": 958,
    "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/implementation/t1/change-report.md",
    "sha256": "09df1349195f6c6c13672e3ac60b7fe4af4c2ef5cab0ac1b18cac9608223948f"
  },
  {
    "bytes": 64519,
    "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/implementation/t1/fixture-map.json",
    "sha256": "89a703d52923d333a3c8b696b80358c532c0c0b50ac2f5683aa5ca65a9bb213c"
  },
  {
    "bytes": 956,
    "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/implementation/t1/fixture-map.md",
    "sha256": "3832ade25bc9b136e68ef805d736ec73958beae2ce2d37677424c32406eb32b7"
  },
  {
    "bytes": 2232,
    "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/implementation/t1/budget-report.json",
    "sha256": "541f22fb85fc98fa76284f5e7d04cb76c0ec5d9a777e80967ea716d2987d0bdc"
  },
  {
    "bytes": 958,
    "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/implementation/t1/budget-report.md",
    "sha256": "4fa4fc1449ed0700fadbc410ca704f202baa99925db74c75e31cbd8c5c282998"
  },
  {
    "bytes": 74908,
    "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/implementation/t1/step-report.json",
    "sha256": "260bbe397212ba1703e7ee453cc91a5b943ad79f1b5163b35a6d475e29625ca9"
  },
  {
    "bytes": 956,
    "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/implementation/t1/step-report.md",
    "sha256": "576d2269f3572b41ecbdd5b4086f973fabaa8817ccb00f68a7331b5c14cebfe7"
  },
  {
    "bytes": 142928,
    "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/implementation/t1/limited.diff",
    "sha256": "af8f7662f2a2e6a90939a0e670f99afd1745999f173463bde5b538aa856239e5"
  }
]
R172_STEP_SHA256 = "7d497a6c5e2803d1e536042c1aeb6e57e89ead4e1f189dddca95a91a73be41ca"

def sha(data):
    return hashlib.sha256(data).hexdigest()

def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()

def file_pin(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": sha(data)}


def canonical(raw):
    assert isinstance(raw, str) and raw.strip(), ("nonempty path", raw)
    relative = Path(raw)
    assert ".." not in relative.parts, ("parent traversal forbidden", raw)
    path = relative if relative.is_absolute() else ROOT / relative
    assert path.is_relative_to(ROOT), ("outside fixed repository root", raw)
    assert not path.is_symlink(), ("symlink forbidden", raw)
    for parent in path.parents:
        assert not parent.is_symlink(), ("symlink parent forbidden", raw)
        if parent == ROOT:
            break
    return str(path)

def coordinates(raw_paths):
    result = [canonical(raw) for raw in raw_paths]
    assert len(result) == len(set(result)), ("duplicate canonical paths", raw_paths)
    return result

def checked_pin(record):
    path = Path(canonical(record["path"]))
    receipt = file_pin(path)
    assert receipt["bytes"] == record["bytes"], ("pinned bytes", str(path))
    assert receipt["sha256"] == record["sha256"], ("pinned SHA256", str(path))
    return receipt

def parent_ledger_guard(path, role, command_ids):
    document = json.loads(path.read_bytes())
    if role == "author":
        assert document["schema_version"] == "bigsmall.r158-author-command-ledger.v1"
    commands = document["commands"]
    assert type(commands) is dict and len(commands) == 15 and set(commands) == set(command_ids)
    for name, entry in commands.items():
        for key in ("authorized", "used", "remaining"):
            assert type(entry[key]) is int
        assert entry["authorized"] == 1
        assert entry["cwd"] == str(ROOT)
        assert type(entry["argv"]) is list
        if name in ("mypy_baseline", "t1_red"):
            assert entry["used"] == 1 and entry["remaining"] == 0
            expected_state = "SPENT" if role == "author" else (
                "SPENT_ACTUAL_DIAGNOSTIC_CENSUS" if name == "mypy_baseline"
                else "SPENT_ACTUAL_UNEXPECTED_LEGACY_CONTROL_FAILURE"
            )
        else:
            assert entry["used"] == 0 and entry["remaining"] == 1
            expected_state = "HELD" if role == "author" else "HELD_PENDING_ROOT_GATE"
        assert entry["state"] == expected_state, ("role-specific state", role, name)
    assert sum(entry["used"] for entry in commands.values()) == 2
    assert sum(entry["remaining"] for entry in commands.values()) == 13
    return file_pin(path)


assert Path.cwd() == ROOT
plan_bytes = (D173 / "plan.json").read_bytes()
plan_md_bytes = (D173 / "plan.md").read_bytes()
assert sha(plan_bytes) == "2da2d8c705e7413230b366b0c94a60a50a4990ae561c469c80aa1c69fae6ba21"
assert sha(plan_md_bytes) == "752de1625414e0309daac089c84673d51b71075f1a658aa61452ef24539e6594"
plan = json.loads(plan_bytes)
activation_bytes = (D173 / "root-activation.json").read_bytes()
activation = json.loads(activation_bytes)
gate = activation["metadata_gate"]
assert gate["state"] == "RESERVED_BY_ROOT"
assert gate["authorized"] == gate["used"] == gate["max_attempts"] == 1
assert gate["remaining"] == 0 and gate["timeout_seconds"] == 120
source_path = canonical(plan["metadata_allowance"]["script"])
assert canonical(__file__) == source_path
assert gate["source_path"] == source_path and gate["cwd"] == str(ROOT)
assert gate["argv"] == [str(ROOT / ".venv/bin/python"), source_path]
assert sha(Path(source_path).read_bytes()) == gate["source_sha256"]

allowed = set(coordinates(plan["scope"]["product_owned"]))
assert len(allowed) == 2 and {canonical(item["path"]) for item in CHANGES} == allowed
assert len(plan["inputs"]) == 31
coordinates([item["path"] for item in plan["inputs"]])
static_inputs = [item for item in plan["inputs"] if canonical(item["path"]) not in allowed]
allowed_inputs = [item for item in plan["inputs"] if canonical(item["path"]) in allowed]
assert len(static_inputs) == 29 and len(allowed_inputs) == 2
static_receipts = [checked_pin(item) for item in static_inputs]
assert sha((D172 / "step-report.json").read_bytes()) == R172_STEP_SHA256
r172_result_bytes = (D172 / "result.json").read_bytes()
r172_result = json.loads(r172_result_bytes)
assert r172_result["exit_code"] == 0
assert r172_result["metadata_summary"]["artifact_pins"] == SETTLED_REPORT_PINS
r172_usage = r172_result["usage"]
assert r172_usage["new_metadata"] == {"used": 1, "remaining": 0, "retries": 0}
assert r172_usage["original_failed_freeze"] == {"used": 1, "remaining": 0, "retries": 0}

assert len(SETTLED_REPORT_PINS) == 13
report_paths = coordinates(plan["metadata_allowance"]["refreshed_T1_reports"])
assert len(report_paths) == 13
assert set(report_paths) == set(coordinates([item["path"] for item in SETTLED_REPORT_PINS]))
report_receipts = [checked_pin(item) for item in SETTLED_REPORT_PINS]
pre_refresh_bytes = {canonical(item["path"]): Path(canonical(item["path"])).read_bytes()
                     for item in SETTLED_REPORT_PINS}
old_semantic = json.loads(pre_refresh_bytes[str(TASK / "semantic.json")])
old_source_records = old_semantic["sources"]
assert len(old_source_records) == 24
old_source_paths = coordinates([item["path"] for item in old_source_records])
old_sources = {}
for item in old_source_records:
    raw = base64.b64decode(item["base64"], validate=True)
    assert len(raw) == item["bytes"] and sha(raw) == item["sha256"]
    old_sources[canonical(item["path"])] = raw
assert set(allowed) <= set(old_sources)
for item in allowed_inputs:
    raw = old_sources[canonical(item["path"])]
    assert len(raw) == item["bytes"] and sha(raw) == item["sha256"]
expected_after = {}
for path_string in allowed:
    text = old_sources[path_string].decode()
    for change in CHANGES:
        if canonical(change["path"]) == path_string:
            assert text.count(change["before"]) == 1, ("exact replacement before", path_string)
            text = text.replace(change["before"], change["after"], 1)
    expected_after[path_string] = text.encode()
    assert Path(path_string).read_bytes() == expected_after[path_string]
unchanged_other = []
for path_string, raw in old_sources.items():
    if path_string not in allowed:
        assert Path(path_string).read_bytes() == raw
        unchanged_other.append(path_string)
assert len(unchanged_other) == 22

parent_plan = json.loads((ROUND / "plan.json").read_bytes())
manifest = json.loads((ROUND / "input-pins.json").read_bytes())
before_path = TASK / "before.json"
before_bytes = before_path.read_bytes()
before = json.loads(before_bytes)
raw_owned = list(parent_plan["scope"]["owned_paths"])
raw_task_owned = list(parent_plan["tasks"][0]["owned_paths"])
raw_new_owned = list(parent_plan["scope"]["new_paths"])
owned = coordinates(raw_owned)
task_owned = coordinates(raw_task_owned)
new_owned = coordinates(raw_new_owned)
assert len(owned) == 24 and len(task_owned) == 9 and len(new_owned) == 1
assert set(owned) == set(old_sources)
assert allowed <= set(task_owned) <= set(owned)
before_paths = coordinates([item["path"] for item in before["sources"]])
assert len(before_paths) == 23
original = {canonical(item["path"]): item for item in before["sources"]}
assert set(owned) - set(original) == set(new_owned)
snapshots = []
source_index = []
complete_diff = []
unchanged_later = []
for path_string in owned:
    path = Path(path_string)
    current = path.read_bytes()
    old_record = original.get(path_string)
    if old_record is None:
        assert path_string in new_owned and path_string in task_owned
        old = b""
    else:
        old = base64.b64decode(old_record["base64"], validate=True)
        assert len(old) == old_record["bytes"] and sha(old) == old_record["sha256"]
    if path_string not in task_owned:
        assert current == old
        unchanged_later.append(path_string)
    snapshots.append({"path": path_string, "relative_path": str(path.relative_to(ROOT)),
        "bytes": len(current), "sha256": sha(current), "changed": current != old,
        "before_bytes": None if old_record is None else len(old),
        "before_sha256": None if old_record is None else sha(old),
        "T1_owned": path_string in task_owned, "raw_scope_path": raw_owned[owned.index(path_string)],
        "raw_before_path": None if old_record is None else old_record["path"],
        "base64": base64.b64encode(current).decode()})
    text = current.decode()
    definitions = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("def ") or stripped.startswith("class "):
            definitions.append({"line": number, "indent": len(line)-len(stripped),
                                "declaration": stripped})
    source_index.append({"path": path_string, "sha256": sha(current),
                        "lines": len(text.splitlines()), "text_declarations": definitions})
    if current != old:
        complete_diff.extend(difflib.unified_diff(old.decode().splitlines(keepends=True),
            text.splitlines(keepends=True), fromfile=path_string+" (original R158 before)",
            tofile=path_string+" (T1 candidate after R173)", n=3))
assert len(unchanged_later) == 15
assert {item["path"] for item in snapshots if item["changed"]} == set(task_owned)
source_pins = [{key:value for key,value in item.items() if key != "base64"} for item in snapshots]
assert len(manifest["protected"]) == 211
coordinates([item["path"] for item in manifest["protected"]])
protected = [checked_pin(item) for item in manifest["protected"]]

test_path = ROOT / "tests/test_operational_runtime_closure.py"
test_bytes = test_path.read_bytes()
assert test_bytes == old_sources[str(test_path)]
assert sha(test_bytes[:80556]) == "c1a68fe0b5ff88bdf604e4859a17da73f61f56b1fd934897f0e66a484d9ae861"
r170_receipt = json.loads((D170 / "implementation/metadata-verification.json").read_bytes())
test_r170_pin = next(item for item in r170_receipt["source_receipts"] if item["path"] == str(test_path))
assert sha(test_bytes) == test_r170_pin["after_sha256"]
frozen_before_test = (D170 / "implementation/before-test.py").read_bytes()
tests_start = b'@pytest.mark.parametrize("family", ["bootstrap", "supervision", "owner_grounding", "route_completion_budget"])'
assert frozen_before_test.count(tests_start) == test_bytes.count(tests_start) == 1
assert frozen_before_test[frozen_before_test.index(tests_start):] == test_bytes[test_bytes.index(tests_start):]
golden_path = D166 / "implementation/legacy_control/legacy-goldens.json"
golden_bytes = golden_path.read_bytes()
assert len(golden_bytes) == 121893 and sha(golden_bytes) == "10452e376a00b1672d540fc1332c6beeeaa42b6cff44f03f425531e26a5d0c38"
assert len(json.loads(golden_bytes)) == 16
provenance_path = D166 / "implementation/golden-provenance.json"
provenance = file_pin(provenance_path)
assert provenance["bytes"] == 4814 and provenance["sha256"] == "d83627d2cef79a2398e07b6c2e55892ea85379f08a4edfff5f3ae2adde4b1ea7"
runner_path = ROUND / "implementation/run-budgeted-command.py"
runner = file_pin(runner_path)
assert runner["bytes"] == 9998 and runner["sha256"] == "a455c05a8794b72e2fb24b72d09a8234b31e86d917512ac21c73d417256bd944"
original_absent_golden = ROUND / "implementation/t1_red/legacy-goldens.json"
assert not original_absent_golden.exists()
ledger_pins = [parent_ledger_guard(ROUND / "command-ledger.json", "author", parent_plan["commands"]),
               parent_ledger_guard(ROUND / "root-command-ledger.json", "root", parent_plan["commands"])]
assert ledger_pins == old_semantic["checks"]["ledger_pins"]
assert file_pin(before_path) == old_semantic["checks"]["original_23_before_preserved"]
assert provenance == old_semantic["checks"]["golden_provenance"]
assert runner == old_semantic["checks"]["runner"]

limited_parts = []
two_receipts = []
for path_string in sorted(allowed):
    before_raw = old_sources[path_string]
    after_raw = expected_after[path_string]
    limited_parts.extend(difflib.unified_diff(before_raw.decode().splitlines(keepends=True),
        after_raw.decode().splitlines(keepends=True), fromfile=path_string+" (settled R172 before)",
        tofile=path_string+" (R173 candidate)", n=3))
    two_receipts.append({"path":path_string,"before_bytes":len(before_raw),"before_sha256":sha(before_raw),
                        "after_bytes":len(after_raw),"after_sha256":sha(after_raw)})
limited_bytes = "".join(limited_parts).encode()
complete_diff_bytes = "".join(complete_diff).encode()
local_outputs = plan["metadata_allowance"]["outputs"]
coordinates(local_outputs)
implementation = D173 / "implementation"
before_sources_path = implementation / "before-sources.json"
before_reports_path = implementation / "before-t1-reports.json"
change_path = implementation / "change-report.json"
limited_path = implementation / "limited.diff"
verification_path = implementation / "metadata-verification.json"
local_write_paths = [before_sources_path,before_reports_path,change_path,limited_path,verification_path]
assert all(str(path) in local_outputs for path in local_write_paths)
assert all(not path.exists() for path in local_write_paths)
before_sources_doc = {"schema_version":"bigsmall.r173-before-sources.v1",
    "source":"settled R172 semantic.sources","source_report_pin":next(item for item in SETTLED_REPORT_PINS if item["path"] == str(TASK/"semantic.json")),
    "records":[item for item in old_source_records if canonical(item["path"]) in allowed]}
before_reports_doc = {"schema_version":"bigsmall.r173-before-t1-reports.v1","round":"R173",
    "records":[{**item,"base64":base64.b64encode(pre_refresh_bytes[canonical(item["path"])]).decode()}
               for item in SETTLED_REPORT_PINS]}
scope_receipt = {"source_receipts":two_receipts,"exact_changes":CHANGES,
    "other_owned_unchanged_count":22,"other_owned_unchanged":sorted(unchanged_other),
    "existing_lifecycle_definitions_byte_identical":True,
    "legacy_VisualOwnerPublicationRecord_byte_identical":True,
    "only_local_publication_budget_getters_and_history_getters_changed":True,
    "legacy_getter_return_types_preserved":True,
    "shared_R170_receipt_codec_unchanged":True,"all_seven_tests_and_entire_test_file_unchanged":True}
coverage = {"new_history_accessors_targeted_execution":False,
    "LocalRetryBudgetRecord_accessors_targeted_execution":False,
    "inherited_seven_node_GREEN_executed":False,
    "limit":"Existing seven bodies do not specifically execute the new history properties. Codec GREEN cannot establish targeted accessor coverage."}
acceptance = dict(old_semantic["acceptance"])
assert all(value is False for value in acceptance.values())
usage = dict(old_semantic["usage"])
assert usage["R158_used"] == 2 and usage["R158_remaining"] == 13
assert usage["t1_green_used"] == 0 and usage["t1_green_remaining"] == 1
assert usage["R172_metadata_used"] == 1 and usage["R172_metadata_remaining"] == 0
usage.update({"R173_metadata_used":1,"R173_metadata_remaining":0,"R173_new_product_verifications":0})
checks = dict(old_semantic["checks"])
checks.update({"owned_current_snapshot_count":24,"T1_allowed_paths":sorted(task_owned),
    "unchanged_later_owned_count":15,"unchanged_later_owned":unchanged_later,
    "protected_count":211,"protected_pins":protected,"original_23_before_preserved":file_pin(before_path),
    "A80556_sha256":sha(test_bytes[:80556]),"seven_T1_test_bodies_and_decorators_unchanged":True,
    "current_test_equals_accepted_R170_after_pin":True,"runner":runner,"ledger_pins":ledger_pins,
    "real_R166_golden":file_pin(golden_path),"golden_tag_count":16,"golden_provenance":provenance,
    "original_R158_golden_absent":True})
r173_record = {"finding":"CONFIRMED_T1_TYPED_HISTORY_INTERFACE_GAP_SOURCE_ONLY",
    "plan_json":file_pin(D173/"plan.json"),"before_sources_archive":str(before_sources_path),
    "before_reports_archive":str(before_reports_path),"limited_diff":{"path":str(limited_path),"bytes":len(limited_bytes),"sha256":sha(limited_bytes)},
    "scope":scope_receipt,"coverage":coverage,"status":"CANDIDATE_SOURCE_REPAIR_ONLY_PENDING_ROOT_GREEN_GATE"}
names = ["semantic","final-freeze","change-report","fixture-map","budget-report","step-report"]
documents = {name:json.loads(pre_refresh_bytes[str(TASK/(name+".json"))]) for name in names}
for document in documents.values():
    document["usage"] = usage
    document["acceptance"] = acceptance
    document["R173"] = r173_record
    if "checks" in document:
        document["checks"] = checks
    if "source_pins" in document:
        document["source_pins"] = source_pins
documents["semantic"]["sources"] = snapshots
documents["semantic"]["source_text_index"] = source_index
documents["semantic"]["previous_current_metadata_preserved"] = {
    "archive":str(before_reports_path),"records":SETTLED_REPORT_PINS}
documents["semantic"]["semantic_statements_status"] = "CANDIDATE_IMPLEMENTATION_CLAIMS_PENDING_ROOT_SOURCE_REVIEW_AND_ACTUAL_GREEN"
documents["semantic"]["semantic_contracts"]["typed_budget_history"] = plan["interface_contract"]
documents["change-report"]["changed_paths"] = [item["path"] for item in source_pins if item["changed"]]
documents["change-report"]["complete_candidate_diff"] = {"path":str(TASK/"limited.diff"),
    "bytes":len(complete_diff_bytes),"sha256":sha(complete_diff_bytes)}
documents["step-report"]["status"] = "CANDIDATE_FROZEN_AFTER_R173_PENDING_ROOT_GREEN_GATE"
documents["step-report"]["pending"] = ["ROOT fresh complete source/fixture/runner gate",
    "one original seven-node T1 GREEN","fresh independent T1 review with explicit accessor coverage boundary",
    "T2 and T3 implementation/verification"]
documents["step-report"]["actual_tool_evidence"] = None
refreshed = {}
for name, document in documents.items():
    refreshed[str(TASK/(name+".json"))] = encode(document)
    refreshed[str(TASK/(name+".md"))] = (
        "# R158 T1 "+name+" after R173\n\n"
        "Status: source candidate only; original T1 GREEN remains HELD.\n\n"
        "R173 adds typed local publication budget history and a distinct immutable local retry budget carrier. "
        "Legacy projections retain their old result types and explicitly reject exact local envelopes. "
        "No new accessor path has targeted execution evidence, and inherited codec GREEN cannot establish that coverage.\n\n"
        "The six expected missing-contract failures and separately accepted R166 control remain a two-run prerequisite. "
        "R170 is a text-scope receipt repair, R172 is settled metadata preparation; neither establishes product GREEN.\n\n"
        "24 current owned sources, 23 original before sources, 15 unchanged later paths, 211 protected inputs, "
        "A80556, the entire test file and seven bodies, the real 16-tag R166 golden and provenance, runner and parent 2/13 budgets are retained.\n\n"
        "R173 old two sources and thirteen pre-refresh reports are archived before overwrite in the same single action. "
        "R158 remains 2 spent / 13 HELD, original GREEN 0/1 HELD, no new product execution. "
        "T1/B9/T12/native/actual/formal acceptance remains false.\n").encode()
refreshed[str(TASK/"limited.diff")] = complete_diff_bytes
assert len(refreshed) == 13 and set(refreshed) == set(report_paths)
change_doc = {"schema_version":"bigsmall.r173-change-report.v1","round":"R173",
    "status":"CANDIDATE_SOURCE_REPAIR_ONLY","scope":scope_receipt,
    "limited_diff":{"path":str(limited_path),"bytes":len(limited_bytes),"sha256":sha(limited_bytes)},
    "coverage":coverage,"usage":usage,"acceptance":acceptance}
local_bytes = {str(before_sources_path):encode(before_sources_doc),
    str(before_reports_path):encode(before_reports_doc),str(change_path):encode(change_doc),
    str(limited_path):limited_bytes}

def immutable_recheck():
    for item in static_inputs:
        checked_pin(item)
    for item in protected:
        checked_pin(item)
    for item in source_pins:
        checked_pin(item)
    for item in ledger_pins:
        checked_pin(item)
    checked_pin(provenance)
    checked_pin(runner)
    assert before_path.read_bytes() == before_bytes
    assert (D173/"plan.json").read_bytes() == plan_bytes
    assert (D173/"plan.md").read_bytes() == plan_md_bytes
    assert (D173/"root-activation.json").read_bytes() == activation_bytes
    assert sha(Path(source_path).read_bytes()) == gate["source_sha256"]
    assert (D172/"result.json").read_bytes() == r172_result_bytes
    assert sha((D172/"step-report.json").read_bytes()) == R172_STEP_SHA256
    assert not original_absent_golden.exists()

# All strong input, exact edit, ownership, history and budget assertions precede writing.
immutable_recheck()
for item in SETTLED_REPORT_PINS:
    checked_pin(item)
assert all(not path.exists() for path in local_write_paths)
implementation.mkdir(parents=True,exist_ok=True)
for path_string in (str(before_sources_path),str(before_reports_path)):
    with Path(path_string).open("xb") as stream:
        stream.write(local_bytes[path_string])
    assert Path(path_string).read_bytes() == local_bytes[path_string]
for path_string in (str(change_path),str(limited_path)):
    with Path(path_string).open("xb") as stream:
        stream.write(local_bytes[path_string])
    assert Path(path_string).read_bytes() == local_bytes[path_string]
for path_string, raw in refreshed.items():
    assert Path(path_string).read_bytes() == pre_refresh_bytes[path_string]
    Path(path_string).write_bytes(raw)
    assert Path(path_string).read_bytes() == raw

for path_string, raw in local_bytes.items():
    assert Path(path_string).read_bytes() == raw
for path_string, raw in refreshed.items():
    assert Path(path_string).read_bytes() == raw
immutable_recheck()
archive_doc = json.loads(before_reports_path.read_bytes())
assert len(archive_doc["records"]) == 13
for item in archive_doc["records"]:
    raw = base64.b64decode(item["base64"],validate=True)
    assert raw == pre_refresh_bytes[canonical(item["path"])]
    assert len(raw) == item["bytes"] and sha(raw) == item["sha256"]
source_archive = json.loads(before_sources_path.read_bytes())
assert len(source_archive["records"]) == 2
for item in source_archive["records"]:
    raw = base64.b64decode(item["base64"],validate=True)
    assert raw == old_sources[canonical(item["path"])]
    assert len(raw) == item["bytes"] and sha(raw) == item["sha256"]
artifact_pins = [file_pin(Path(path)) for path in list(local_bytes)+list(refreshed)]
verification_doc = {"schema_version":"bigsmall.r173-metadata-verification.v1",
    "status":"CANDIDATE_SOURCE_SCOPE_VERIFIED_ONLY","static_input_receipts":static_receipts,
    "before_source_receipts":allowed_inputs,"source_receipts":two_receipts,
    "source_pins":source_pins,"checks":checks,"scope":scope_receipt,
    "pre_refresh_report_pins":SETTLED_REPORT_PINS,"artifact_pins":artifact_pins,
    "coverage":coverage,"usage":usage,"acceptance":acceptance,
    "proof_limit":"Standard-library text/bytes/hash/JSON only; no product import/AST/compile/pytest/static/probe/SQL/Git."}
verification_bytes = encode(verification_doc)
with verification_path.open("xb") as stream:
    stream.write(verification_bytes)
assert verification_path.read_bytes() == verification_bytes
for path_string, raw in local_bytes.items():
    assert Path(path_string).read_bytes() == raw
for path_string, raw in refreshed.items():
    assert Path(path_string).read_bytes() == raw
immutable_recheck()
artifact_pins.append(file_pin(verification_path))
print(json.dumps({"status":"R173_CANDIDATE_SOURCE_REPAIR_METADATA_ONLY",
    "artifact_pins":artifact_pins,"source_receipts":two_receipts,
    "counts":{"plan_inputs":31,"static_inputs_unchanged":29,"allowed_source_changes":2,
        "other_owned_unchanged":22,"owned":24,"original_before":23,"unchanged_later":15,
        "protected":211,"test_nodes":7,"A_prefix":80556,"golden_tags":16,
        "archived_reports":13,"refreshed_reports":13},
    "coverage":coverage,"usage":usage,"acceptance":acceptance},sort_keys=True))
