"""Qualified CPU-only association probes; never execute the actual runner."""

import gzip
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
spec = importlib.util.spec_from_file_location("independent_offline_reviewer", HERE / "verify_offline.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sha = lambda data: hashlib.sha256(data).hexdigest()
guard = HERE / "independent-module-review.md"
guard_sha = sha(guard.read_bytes())
manifest = json.loads((HERE / "execution-source-hashes.json").read_text())
sources = {}
for name, expected in manifest.items():
    live, archive = (ROOT / name).read_bytes(), (HERE / "source-before" / name).read_bytes()
    sources[name] = {"expected": expected, "live": sha(live), "archive": sha(archive),
                     "bytes": len(live)}
assert len(sources) == 32 and sum(value["bytes"] for value in sources.values()) == 398949
assert all(value["expected"] == value["live"] == value["archive"] for value in sources.values())
result = {
    "scope": "QUALIFIED_CPU_ONLY_NO_RENDERER_OR_ACTUAL_RUNNER_CALL",
    "source_freeze": {"count": len(sources), "bytes": sum(v["bytes"] for v in sources.values()),
                      "all_live_archive_match": True},
    "runner_sha256": sha((HERE / "run_once.py").read_bytes()),
    "verifier_sha256": sha((HERE / "verify_offline.py").read_bytes()),
    "module_review_sha256": guard_sha,
    "cases": {},
}
with tempfile.TemporaryDirectory(prefix="step-rgbd-runner-review-") as temporary:
    for kind in ("baseline", "saved_payload_identity", "terminal_episode", "terminal_time", "action_ownership"):
        directory = Path(temporary) / kind
        directory.mkdir()
        module.synthetic_attempt(directory)
        changes = {}
        if kind in {"saved_payload_identity", "action_ownership"}:
            path = directory / "nominal-journal.jsonl.gz"
            rows = list(module.runner_api().read_jsonl_gzip(path))
            for row in rows:
                if kind == "saved_payload_identity" and row["event"] == "ACQUISITION_END" and row["physics_step"] == 1:
                    for key, value in {"observation_id": "unrelated-frame",
                                       "observation_checksum_sha256": "b" * 64,
                                       "file": "frames/unrelated.json.gz"}.items():
                        changes[key] = {"before": row["saved"][key], "after": value}
                        row["saved"][key] = value
                if kind == "action_ownership" and row["event"] in {"ACQUISITION_BEGIN", "ACQUISITION_END"} and row["physics_step"] == 1:
                    changes[row["event"]] = {"before": row["action_ordinal"], "after": None}
                    row["action_ordinal"] = None
            path.write_bytes(gzip.compress(b"".join(json.dumps(row).encode() + b"\n" for row in rows), mtime=0))
        elif kind.startswith("terminal_"):
            path = directory / "terminal.json"
            terminal = json.loads(path.read_text())
            key, value = ("episode_id", "unrelated-episode") if kind == "terminal_episode" else ("final_sim_time_s", 9.0)
            changes[key] = {"before": terminal[key], "after": value}
            terminal[key] = value
            path.write_text(json.dumps(terminal))
        checked = module.verify_attempt(directory, decode=False)
        result["cases"][kind] = {"changes": changes, "report": checked}
        assert checked["integrity_status"] == "VERIFIED", (kind, checked["failures"])
        assert checked["allocated_steps"] == checked["verified_frames"] == 3
        assert checked["source_authenticity"] == "UNKNOWN"
        assert checked["continuous_motion"] == "NOT_CERTIFIED" and checked["formal_accepted"] is False

assert sha(guard.read_bytes()) == guard_sha == "a7ae2306bd4fd8c04c4ad0fb2d620f9b58e8489bb11f462f91c77214e8bc0847"
assert all(sha((ROOT / name).read_bytes()) == expected for name, expected in manifest.items())
(HERE / "independent-runner-counterexamples.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"qualified_cases": list(result["cases"]), "source_freeze": result["source_freeze"],
                  "module_review_unchanged": True}))
