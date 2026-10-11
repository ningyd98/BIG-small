from pathlib import Path
import copy
import hashlib
import json
import os
import stat

ROUND = Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round132-p6-root-state-metadata-recovery-20261011")
plan = json.loads((ROUND / "plan.json").read_text())
activation = json.loads((ROUND / "root-activation.json").read_text())
target = Path(plan["state"]["path"])
before_raw = target.read_bytes()
before_sha = hashlib.sha256(before_raw).hexdigest()
if before_sha != activation["fresh_state_sha256"]:
    raise RuntimeError("Fresh state no longer matches activation; no mutation")
before = json.loads(before_raw)
if not isinstance(before, dict) or not isinstance(before.get("planning"), dict):
    raise RuntimeError("Unexpected state shape; no mutation")
candidate = copy.deepcopy(before)
added = []
for key, value in plan["state"]["allowed_additions"].items():
    if key not in candidate["planning"]:
        candidate["planning"][key] = value
        added.append(key)
    elif key == "R132" and candidate["planning"][key] != value:
        raise RuntimeError("Conflicting R132 record; no mutation")
protected = copy.deepcopy(candidate)
for key in added:
    del protected["planning"][key]
if protected != before:
    raise RuntimeError("Candidate changes protected existing state; no mutation")
candidate_raw = (json.dumps(candidate, ensure_ascii=False, indent=2) + "\n").encode()
if json.loads(candidate_raw) != candidate:
    raise RuntimeError("Candidate round trip mismatch; no mutation")
evidence = ROUND / "implementation"
evidence.mkdir(exist_ok=True)
with (evidence / "state-before.json").open("xb") as stream:
    stream.write(before_raw)
with (evidence / "state-candidate.json").open("xb") as stream:
    stream.write(candidate_raw)
if hashlib.sha256(target.read_bytes()).hexdigest() != before_sha:
    raise RuntimeError("Concurrent state change detected; candidate preserved, no mutation")
if added:
    mode = stat.S_IMODE(target.stat().st_mode)
    temporary = evidence / "state-replacement.json"
    with temporary.open("xb") as stream:
        stream.write(candidate_raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, mode)
    if hashlib.sha256(target.read_bytes()).hexdigest() != before_sha:
        raise RuntimeError("Concurrent state change before replacement; no mutation")
    os.replace(temporary, target)
after_raw = target.read_bytes()
after = json.loads(after_raw)
if after != candidate:
    raise RuntimeError("Post-update state mismatch; preserve evidence and stop")
with (evidence / "state-after.json").open("xb") as stream:
    stream.write(after_raw)
receipt = {
    "status": "PASS_METADATA_ONLY",
    "added": added,
    "before_sha256": before_sha,
    "candidate_sha256": hashlib.sha256(candidate_raw).hexdigest(),
    "after_sha256": hashlib.sha256(after_raw).hexdigest(),
    "protected_existing_state_unchanged": protected == before,
    "product_commands": 0,
    "original_failure_preserved": True,
}
with (evidence / "state-update-result.json").open("x") as stream:
    stream.write(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(receipt, ensure_ascii=False))
