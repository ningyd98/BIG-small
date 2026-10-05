"""Recompute all smoke outcomes from immutable per-step physical samples."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from cloud_edge_robot_arm.research.pilot_audit import physical_sample
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    evaluate_evidence,
)

OUTPUT = Path(__file__).resolve().parent
ROOT = OUTPUT.parents[3]


def read(path: Path):
    return json.loads(path.read_text())


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    smoke = OUTPUT / "smoke-20"
    assignments = read(smoke / "assignments.json")
    results = read(smoke / "results.json")
    summary = read(smoke / "summary.json")
    provenance = read(smoke / "provenance.json")
    assert provenance["assignments_sha256"] == sha(smoke / "assignments.json")
    assert provenance["config_sha256"] == sha(smoke / "config.yaml")
    for name, digest in provenance["source_sha256"].items():
        assert sha(ROOT / name) == digest, name
    for name, digest in provenance["frozen_bundle_sha256"].items():
        assert sha(ROOT / provenance["frozen_dir"] / name) == digest, name
    cases = assignments["cases"]
    assert len(cases) == len(results) == summary["assigned"] == 20
    rows = {row["case_id"]: row for row in results}
    assert len(rows) == 20
    entries = []
    for case in cases:
        case_id = case["case_id"]
        directory = smoke / "cases" / case_id
        episode = read(directory / "episode.json")
        samples = [physical_sample(row) for row in read(directory / "physical-evidence.json")]
        assert samples, case_id
        physical = evaluate_evidence(
            samples, CompletionCriteria("object", "target_region"),
            evaluation_start_step=samples[0].physics_step,
        )
        assert json.loads(json.dumps(asdict(physical))) == read(directory / "physical-outcome.json")
        visual_success = bool(physical.success and episode["online_reported_complete"]
                              and episode["terminal_reason"] is None)
        success = bool(visual_success and case["kind"] != "MISSING_TARGET")
        row = rows[case_id]
        assert episode["success"] == visual_success
        assert row["success"] == row["task_success"] == success
        assert row["physical_success"] == physical.success
        assert row["false_completion"] == bool(episode["online_reported_complete"] and not success)
        for record in episode["verification_records"]:
            evidence = record.get("evidence", {})
            if evidence.get("grasp_profile") is not None:
                assert evidence["grasp_profile"] == "mujoco_upright_box_v2"
        entries.append({
            "case_id": case_id, "kind": case["kind"], "success": success,
            "physical_success": physical.success, "physical_samples": len(samples),
            "safety_violation": physical.safety_violation, "safety_events": physical.safety_events,
            "false_completion": row["false_completion"], "blocked": row["blocked"],
            "model_calls": row["model_calls"], "executed_actions": row["executed_actions"],
        })
    assert sum(entry["success"] for entry in entries) == summary["succeeded"]
    assert sum(entry["false_completion"] for entry in entries) == summary["false_completions"]
    report = {
        "valid": True, "errors": [], "assigned": 20, "recorded": 20,
        "succeeded": summary["succeeded"], "normal_succeeded": summary["normal_succeeded"],
        "false_completions": summary["false_completions"], "blocked": summary["blocked"],
        "physical_sample_count": sum(entry["physical_samples"] for entry in entries),
        "safety_violations": sum(entry["safety_violation"] for entry in entries),
        "formal_g1": False, "cases": entries,
    }
    (OUTPUT / "smoke-validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}))


if __name__ == "__main__":
    main()
