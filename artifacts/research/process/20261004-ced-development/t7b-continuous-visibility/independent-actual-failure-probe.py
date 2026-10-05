"""Read the sole failed actual attempt and frozen outputs; no simulator import."""

import gzip
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
ATTEMPT = HERE / "attempt-1"
sha = lambda data: hashlib.sha256(data).hexdigest()
summary = json.loads((ATTEMPT / "summary.json").read_text())
series = json.loads((ATTEMPT / "whole-step/summary.json").read_text())
terminal = json.loads((ATTEMPT / "terminal.json").read_text())
teacher = json.loads((ATTEMPT / "teacher-evidence.json").read_text())
verified = json.loads((ATTEMPT / "offline-verification.json").read_text())
index = [json.loads(line) for line in (ATTEMPT / "whole-step/index.jsonl").read_text().splitlines()]
with gzip.open(ATTEMPT / "nominal-journal.jsonl.gz", "rt") as stream:
    journal = [json.loads(line) for line in stream]
failed = [row for row in journal if row["event"] == "ACQUISITION_FAILED"]
assert len(failed) == 1 and failed[0]["physics_step"] == 10
failure = failed[0]
camera = failure["camera"]
before, after = camera["before_state"], camera["after_state"]
changed = {key: {"before": before.get(key), "after": after.get(key)}
           for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
assert list(changed) == ["data_arrays_sha256"]
assert camera["state_unchanged"] is False and len(camera["pass_state_hashes"]) == 2
assert camera["pass_state_hashes"][0] == camera["pass_state_hashes"][1]
assert before["physical_step"] == after["physical_step"] == terminal["final_step"] == 10
assert before["sim_time_s"] == after["sim_time_s"] == terminal["final_sim_time_s"]
assert before["sensor_noise_std_m"] == after["sensor_noise_std_m"] == 0.0
event_counts = Counter(row["event"] for row in journal)
index_counts = Counter(row["event"] for row in index)
ends = [row for row in index if row["event"] == "END"]
assert [row["physics_step"] for row in ends] == list(range(10))
assert index_counts == {"BEGIN": 11, "END": 10, "FAILED": 1}
assert event_counts["ACQUISITION_BEGIN"] == 11 and event_counts["ACQUISITION_END"] == 10
assert series["allocated_steps"] == series["attempted_captures"] == series["capture_calls_started"] == 11
assert series["completed_captures"] == 10 and series["failed_captures"] == 1
assert summary["whole_step_capture_calls"] == 11
assert summary["action_begins"] == summary["action_ends"] == summary["framed_actions"] == summary["unframed_actions"] == 0
assert teacher["evaluation_start_step"] is None and teacher["outcome"] is None
assert len(teacher["physical_samples"]) == 11
assert verified["integrity_status"] == "INCOMPLETE_OR_INVALID"
assert verified["allocated_steps"] == 11 and verified["verified_frames"] == 10
assert verified["failed_or_missing_frames"] == 1
assert verified["max_sim_sample_gap_s"] <= verified["original_max_sample_gap_s"] == 0.005
assert verified["formal_accepted"] is False and verified["continuous_motion"] == "NOT_CERTIFIED"
assert verified["source_authenticity"] == "UNKNOWN" and verified["native_admission"] == "NOT_PROMOTED"
assert verified["external_utc_uncertainty"] == verified["future_stability"] == verified["calibrated_error_bound"] == "UNAVAILABLE"
clock_order = all(row["record_seq"] == position and row["clock"]["monotonic_before_ns"] <= row["clock"]["monotonic_after_ns"]
                  and (position == 1 or journal[position - 2]["clock"]["monotonic_after_ns"] <= row["clock"]["monotonic_before_ns"])
                  for position, row in enumerate(journal, 1))
utc_order = all(datetime.fromisoformat(a["clock"]["utc"]) <= datetime.fromisoformat(b["clock"]["utc"])
                for a, b in zip(journal, journal[1:]))
assert clock_order and utc_order
failed_begin = next(row for row in journal if row["event"] == "ACQUISITION_BEGIN" and row["physics_step"] == 10)
assert failed_begin["clock"]["monotonic_after_ns"] <= camera["capture_monotonic_begin_ns"] <= camera["capture_monotonic_end_ns"] <= failure["clock"]["monotonic_before_ns"]
physics = [row for row in journal if row["event"] == "OPERATION" and row["source"]["kind"] == "PHYSICS" and row["source"]["phase"] == "END"]
assert [row["source"]["physics_step"] for row in physics] == list(range(1, 11))
last_physics = physics[-1]["source"]["result"]["physics_state"]
assert last_physics["episode_id"] == terminal["episode_id"] == series["episode_id"]
assert last_physics["physics_step"] == terminal["final_step"]
assert last_physics["sim_time_s"] == terminal["final_sim_time_s"]
assert terminal["commands"] == terminal["operation_observer_failures"] == []
manifest = json.loads((HERE / "execution-source-hashes.json").read_text())
archives = json.loads((HERE / "fix-round-1/execution-archive-index.json").read_text())
assert len(manifest) == 32 and set(manifest) == set(archives)
assert sum((ROOT / name).stat().st_size for name in manifest) == 408064
assert all(sha((ROOT / name).read_bytes()) == sha((HERE / archives[name]["archive"]).read_bytes()) == expected for name, expected in manifest.items())
protected = {
    "independent-runner-review.md": "2a6eee00eaf2ebfedfd5b70993baeaea6a4d43149ba930f7607da3baeffc07f2",
    "independent-runner-fix1-review.md": "d8aab41c9e95a24f488ffc53a97db1e6c307f114732f9db9a5bce51bf34dd307",
    "independent-module-review.md": "a7ae2306bd4fd8c04c4ad0fb2d620f9b58e8489bb11f462f91c77214e8bc0847",
}
assert all(sha((HERE / name).read_bytes()) == expected for name, expected in protected.items())
evidence = {str(path.relative_to(ATTEMPT)): sha(path.read_bytes()) for path in ATTEMPT.rglob("*") if path.is_file()}
result = {
    "scope": "READ_ONLY_FAILED_ACTUAL_ATTEMPT_OFFLINE_AUDIT_NO_RETRY_OR_RENDER",
    "status": "FAILED_INCOMPLETE_HORIZON",
    "actual_episode_id": terminal["episode_id"],
    "terminal_step": terminal["final_step"], "terminal_sim_time_s": terminal["final_sim_time_s"],
    "original_settle_steps": 120, "settle_steps_completed": 10,
    "evaluation_start_step": teacher["evaluation_start_step"], "teacher_actions_started": 0,
    "allocation": series, "actual_summary": summary,
    "offline_verifier_exit_code": 1, "offline_report": verified,
    "nominal_event_counts": dict(event_counts), "index_event_counts": dict(index_counts),
    "nominal_monotonic_order_valid": clock_order, "nominal_utc_order_valid": utc_order,
    "failed_camera_bracket_retained": True,
    "failed_camera": camera, "changed_state_components": changed,
    "unchanged_state_components": sorted(key for key in before if before[key] == after[key]),
    "diagnosis_limit": "Aggregate data_arrays hash does not identify a member or establish the cause; no rerender was performed.",
    "exact_source_count": 32, "exact_source_bytes": 408064, "all_live_final_archive_match": True,
    "protected_review_hashes": protected, "attempt_file_sha256": evidence,
}
(HERE / "independent-actual-failure-audit.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"status": result["status"], "allocation": {key: series[key] for key in ("allocated_steps", "capture_calls_started", "completed_captures", "failed_captures")},
                  "changed": changed, "source_count": 32, "all_pins_match": True}))
