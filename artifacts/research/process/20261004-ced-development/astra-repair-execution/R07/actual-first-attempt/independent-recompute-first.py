"""Read-only actual-source audit; never import the active producer or run physics."""

import hashlib
import json
import time
from pathlib import Path

from cloud_edge_robot_arm.research.protocol import content_digest
from cloud_edge_robot_arm.research.protocol_evidence import _recovery

ROOT = Path(__file__).resolve().parents[7]
HERE = Path(__file__).resolve().parent
PRODUCER = HERE.parent / "producer"
RAW = PRODUCER / "raw/recovery-0001/attempt-1"
PROTOCOL = PRODUCER / "protocol-final"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    started = time.monotonic_ns()
    result = json.loads((RAW / "result.json").read_text())
    plan = json.loads((RAW / "execution-plan.json").read_text())
    header = json.loads((PROTOCOL / "generation.json").read_text())
    frozen_hash = "66570b912ba08e0924e4cbe31098be9df7f1f02ed43548b131f65b2695ded724"
    assert content_digest(header) == plan["protocol_hash"] == frozen_hash
    assert result["assignment_id"] == plan["row"]["assignment_id"] == "recovery-0001"
    assert result["attempt"] == plan["attempt"] == 1

    targets = {p for p in RAW.rglob("*") if p.is_file()}
    targets.update(PROTOCOL / n for n in ("generation.json", *header["payload_hashes"]))
    for name, expected in header["payload_hashes"].items():
        assert digest(PROTOCOL / name) == expected, name
    # Current producer may be under successor development; actual original code
    # is checked against its immutable archived version, never imported here.
    for name, expected in header["source_hashes"].items():
        path = ROOT / name
        if name.endswith("/protocol_generation.py") or name.endswith(
            "/generate_rgbd_protocol_evidence.py"
        ):
            path = PRODUCER / "source-package" / path.name
        assert digest(path) == expected, name
        targets.add(path)
    for name, expected in result["payload_hashes"].items():
        assert digest(RAW / name) == expected, name

    allocations = sorted((PROTOCOL / "allocations").glob("*.json"))
    assert len(allocations) == 1, "additional allocation invalidates this fixed snapshot"
    targets.update(allocations)
    before = {str(p.relative_to(ROOT)): digest(p) for p in sorted(targets)}
    samples, proof = _recovery(
        RAW / "source",
        plan["row"],
        plan["fault"],
        json.loads((PROTOCOL / "recipe.json").read_text()),
    )
    assert proof == result["proof"], "actual independent proof mismatch"
    assert len(samples) == result["diagnostics"]["raw_states"] == 7048
    assert [s["physics_step"] for s in samples] == list(range(7048))
    assert samples[0]["sim_time_s"] == 0.0
    counts = {}
    for name in ("raw-observations.jsonl", "raw-actuators.jsonl", "raw-step-journal.jsonl"):
        with (RAW / name).open() as stream:
            counts[name] = sum(1 for _ in stream)
    assert counts["raw-observations.jsonl"] == 7048
    assert counts["raw-actuators.jsonl"] == 7047
    assert proof["independent_outcome"]["success"] is True
    assert proof["independent_outcome"]["safety_assessment"] == "SCOPED_NO_VIOLATION"
    fault_duration = samples[-1]["sim_time_s"] - proof["injection_start_s"]
    assert fault_duration < 60.0
    assert result["denominator"] == 200 and result["unattempted"] == 199
    after = {str(p.relative_to(ROOT)): digest(p) for p in sorted(targets)}
    assert before == after, "read-only inputs changed"
    elapsed = (time.monotonic_ns() - started) / 1e9
    report = {
        "schema": "root.actual-recovery-audit.v1",
        "status": "PASS_SCOPED_ACTUAL_SOURCE",
        "new_actual_calls": 0,
        "physics_or_renderer_calls": 0,
        "provider_calls": 0,
        "scope": "first original source only; no 200-group or formal G4 acceptance",
        "original_result_sha256": digest(RAW / "result.json"),
        "original_protocol_hash": frozen_hash,
        "source_proof": proof,
        "source_identity": {
            "group_id": plan["row"]["scene"]["group_id"],
            "scene_hash": plan["row"]["scene_hash"],
        },
        "raw_jsonl_rows": counts,
        "raw_file_count": len([p for p in RAW.rglob("*") if p.is_file()]),
        "raw_bytes_including_result": sum(p.stat().st_size for p in RAW.rglob("*") if p.is_file()),
        "result_reported_bytes_excludes_result": result["retained_bytes"],
        "fault_start_to_terminal_sim_s": fault_duration,
        "full_trace_elapsed_sim_s": proof["independent_outcome"]["elapsed_s"],
        "sim_elapsed_is_not_wall_elapsed": True,
        "attempted_groups": 1,
        "unattempted_groups": 199,
        "fixed_denominator": 200,
        "all_source_inputs_sha256": before,
        "changed_inputs": [],
        "audit_wall_elapsed_s": elapsed,
        "g4_measured": False,
        "formal_accepted": False,
    }
    output = HERE / "independent-actual-review.json"
    with output.open("x") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "status",
                    "raw_file_count",
                    "raw_bytes_including_result",
                    "fault_start_to_terminal_sim_s",
                    "audit_wall_elapsed_s",
                    "changed_inputs",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
