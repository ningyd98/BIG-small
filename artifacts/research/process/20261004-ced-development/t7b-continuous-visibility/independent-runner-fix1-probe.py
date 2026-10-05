"""Post-fix CPU replay and final exact-source audit; no actual runner call."""

import copy
import gzip
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sha = lambda data: hashlib.sha256(data).hexdigest()
spec = importlib.util.spec_from_file_location("independent_fix1_verifier", HERE / "verify_offline.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
manifest = json.loads((HERE / "execution-source-hashes.json").read_text())
baseline = json.loads((HERE / "fix-round-1/baseline/execution-source-hashes.json").read_text())
archive_index = json.loads((HERE / "fix-round-1/execution-archive-index.json").read_text())
header = json.loads((HERE / "header.json").read_text())
changed = [name for name in manifest if manifest[name] != baseline[name]]
assert set(manifest) == set(baseline) == set(archive_index) and len(manifest) == 32
assert changed == [str((HERE / "verify_offline.py").relative_to(ROOT))]
byte_count = 0
for name, expected in manifest.items():
    live = (ROOT / name).read_bytes()
    archived = (HERE / archive_index[name]["archive"]).read_bytes()
    initial_archive = (HERE / "source-before" / name).read_bytes()
    assert sha(live) == sha(archived) == archive_index[name]["sha256"] == expected
    assert sha(initial_archive) == baseline[name]
    assert len(live) == archive_index[name]["bytes"]
    byte_count += len(live)
assert byte_count == header["source_bytes"] == 408064 and header["source_count"] == 32
assert sha((HERE / "execution-source-hashes.json").read_bytes()) == header["source_manifest_sha256"]
protected = {
    "independent-runner-review.md": "2a6eee00eaf2ebfedfd5b70993baeaea6a4d43149ba930f7607da3baeffc07f2",
    "independent-module-review.md": "a7ae2306bd4fd8c04c4ad0fb2d620f9b58e8489bb11f462f91c77214e8bc0847",
    "independent-runner-probe.py": "c4fc7b5a2e2fe80c8725b3b700481808522e11f2bff84bcdd935334bb611c40f",
    "independent-runner-counterexamples.json": "5aae0ceaf276581cda58b3a11af8fdb0bdb2a0d43efe6e66bc64f7624cb5234f",
}
assert all(sha((HERE / name).read_bytes()) == expected for name, expected in protected.items())
assert not (HERE / "attempt-1").exists()
result = {
    "scope": "POST_FIX_CPU_ONLY_NO_ACTUAL_RUNNER_RENDERER_PHYSICS_MODEL_HARDWARE",
    "runner_sha256": sha((HERE / "run_once.py").read_bytes()),
    "verifier_sha256": sha((HERE / "verify_offline.py").read_bytes()),
    "manifest_sha256": sha((HERE / "execution-source-hashes.json").read_bytes()),
    "header_sha256": sha((HERE / "header.json").read_bytes()),
    "archive_index_sha256": sha((HERE / "fix-round-1/execution-archive-index.json").read_bytes()),
    "source_freeze": {"count": 32, "bytes": byte_count, "all_live_archive_match": True,
                      "initial_32_archive_unchanged": True, "changed_inputs": changed},
    "protected_hashes": protected,
    "actual_attempt_exists": False,
    "cases": {},
}
expected_error = {
    "saved_payload_identity": "saved acquisition differs from complete index END",
    "terminal_episode": "terminal episode/step/time differs",
    "terminal_time": "terminal episode/step/time differs",
    "action_ownership": "action ownership not unique",
    "acquisition_episode": "acquisition/raw physical identity mismatch",
    "camera_step": "camera measured step/time mismatch",
    "final_physics_time": "declared PHYSICS source identity mismatch",
    "overlapping_actions": "action ownership not unique",
    "camera_clock": "camera/raw capture clock interval mismatch",
}
with tempfile.TemporaryDirectory(prefix="step-rgbd-runner-fix1-review-") as temporary:
    for kind in ("baseline", *expected_error):
        directory = Path(temporary) / kind
        directory.mkdir()
        module.synthetic_attempt(directory)
        if kind.startswith("terminal_"):
            path = directory / "terminal.json"
            terminal = json.loads(path.read_text())
            key, value = ("episode_id", "unrelated-episode") if kind == "terminal_episode" else ("final_sim_time_s", 9.0)
            terminal[key] = value
            path.write_text(json.dumps(terminal))
        elif kind != "baseline":
            path = directory / "nominal-journal.jsonl.gz"
            rows = list(module.runner_api().read_jsonl_gzip(path))
            rewritten = []
            for row in rows:
                if row["event"] == "ACQUISITION_END" and row["physics_step"] == 1:
                    if kind == "saved_payload_identity":
                        row["saved"].update(observation_id="unrelated-frame",
                            observation_checksum_sha256="b" * 64, file="frames/unrelated.json.gz")
                    elif kind == "camera_step":
                        for state in ("before_state", "after_state"):
                            row["camera"][state]["physical_step"] = 99
                    elif kind == "camera_clock":
                        row["camera"]["capture_monotonic_begin_ns"] = row["saved"]["monotonic_begin_ns"] - 1
                if row["event"] in {"ACQUISITION_BEGIN", "ACQUISITION_END"} and row["physics_step"] == 1:
                    if kind == "action_ownership":
                        row["action_ordinal"] = None
                    elif kind == "acquisition_episode":
                        row["episode_id"] = "unrelated-episode"
                if (kind == "final_physics_time" and row["event"] == "OPERATION"
                    and row["source"]["kind"] == "PHYSICS" and row["source"]["phase"] == "END"
                    and row["source"]["physics_step"] == 2):
                    row["source"]["result"]["physics_state"]["sim_time_s"] = 9.0
                rewritten.append(row)
                if kind == "overlapping_actions" and row["event"] in {"ACTION_BEGIN", "ACTION_END", "TEACHER_ACTION"}:
                    duplicate = copy.deepcopy(row)
                    duplicate["action_ordinal"] = 2
                    duplicate["clock"]["monotonic_before_ns"] = duplicate["clock"]["monotonic_after_ns"]
                    rewritten.append(duplicate)
            for sequence, row in enumerate(rewritten, 1):
                row["record_seq"] = sequence
            path.write_bytes(gzip.compress(b"".join(json.dumps(row).encode() + b"\n" for row in rewritten), mtime=0))
            if kind == "overlapping_actions":
                path = directory / "summary.json"
                summary = json.loads(path.read_text())
                summary.update(action_begins=2, action_ends=2)
                path.write_text(json.dumps(summary))
        checked = module.verify_attempt(directory, decode=False)
        result["cases"][kind] = checked
        expected = "VERIFIED" if kind == "baseline" else "INCOMPLETE_OR_INVALID"
        assert checked["integrity_status"] == expected, (kind, checked)
        if kind != "baseline":
            assert any(expected_error[kind] in failure for failure in checked["failures"]), (kind, checked)
        assert checked["allocated_steps"] == checked["verified_frames"] == 3
        assert checked["source_authenticity"] == "UNKNOWN"
        assert checked["continuous_motion"] == "NOT_CERTIFIED" and checked["formal_accepted"] is False
        assert checked["future_stability"] == checked["calibrated_error_bound"] == checked["external_utc_uncertainty"] == "UNAVAILABLE"

assert all(sha((ROOT / name).read_bytes()) == expected for name, expected in manifest.items())
assert all(sha((HERE / name).read_bytes()) == expected for name, expected in protected.items())
assert not (HERE / "attempt-1").exists()
(HERE / "independent-runner-fix1-counterexamples.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"baseline": "VERIFIED", "closed": list(expected_error),
                  "exact32": result["source_freeze"], "protected_unchanged": True}))
