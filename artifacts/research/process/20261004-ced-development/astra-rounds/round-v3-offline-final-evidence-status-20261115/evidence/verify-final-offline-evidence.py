"""只读复核离线27结果、完整来源、物理重算、SQLite租约及逐文件清单。"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from cloud_edge_robot_arm.research.sol_molmo_offline_regression import (
    ROOT, PROCESS, ENTRY_PATHS, SUCCESS_CASES, _verify_inventory,
)
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria, PhysicalSample, evaluate_evidence,
)


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


run = PROCESS / "offline-regression/27-case-run-01"
batch = read(run / "batch-result.json")
assert batch["original_denominator"] == batch["successes"] == 27
assert batch["complete"] is True and batch["not_run"] == 0
assert [row["case"] for row in batch["results"]] == list(SUCCESS_CASES)
rows = []
manifest_files = 0
for name in SUCCESS_CASES:
    folder = run / name
    result = read(folder / "result.json")
    episode = result["outcome"]
    assert result["component_success"] is True
    assert result["worker_status"] == "SUCCEEDED"
    assert result["source_bytes_unchanged_after"] is True
    assert result["network_attempts"] == []
    assert result["point_replays"] == 4 and result["cloud_replays"] == 1
    assert result["model_loads_started"] == result["generation_calls_started"] == 0
    assert result["generation_calls_completed"] == result["cloud_requests"] == 0
    costs = read(folder / "costs.json")
    assert costs["requests"] == []
    assert costs["summary"]["model_requests"] == costs["summary"]["cloud_model_requests"] == 0
    receipt = read(folder / "source-receipt.json")
    assert len(receipt["complete_source_inventory"]) == 599
    _verify_inventory(receipt["complete_source_inventory"])
    assert receipt["offline_entry_sources"] == {name: digest(ROOT / name) for name in ENTRY_PATHS}
    assert episode["planning_passed"] is episode["diagnostic_complete"] is episode["physical_success"] is True
    assert episode["executed_actions"] == 8 and episode["terminal_reason"] is None
    checks = episode["safety_checks"]
    assert [row["phase"] for row in checks] == [phase for _ in range(8) for phase in ("PRE", "POST")]
    assert all(row["verdict"]["allowed"] and row["verdict"]["evaluated_rules"] for row in checks)
    assert len(episode["marker_frames"]) == 20
    points = read(folder / "replay/points.json")
    assert len(points) == 4
    assert points[0]["phase_identity"] == points[1]["phase_identity"]
    assert points[2]["phase_identity"] == points[3]["phase_identity"]
    assert points[0]["phase_identity"] != points[2]["phase_identity"]
    for stage in (1, 2):
        planning = read(folder / f"planning/planning-stage-{stage:02d}.json")
        if stage == 2:
            assert planning["outcome"] == "PLANNED"
    raw = read(folder / "component/physical-evidence.json")
    samples = []
    for sample in raw:
        value = dict(sample)
        for key in ("object_position_m", "object_half_extent_xy_m", "region_center_xy_m", "region_half_extent_xy_m"):
            value[key] = tuple(value[key])
        for key in ("contact_pairs", "self_collision_checked_pairs"):
            value[key] = tuple(tuple(pair) for pair in value[key])
        samples.append(PhysicalSample(**value))
    assert samples[0].physics_step == 120
    assert samples[-1].physics_step == episode["physics_steps"]
    assert len(samples) == episode["physics_steps"] - 120 + 1
    assert {s.episode_id for s in samples} == {episode["episode_id"]}
    outcome = evaluate_evidence(samples, CompletionCriteria("object", "target_region"), evaluation_start_step=120)
    assert outcome.success and not outcome.safety_violation
    assert json.loads(json.dumps(asdict(outcome))) == episode["independent_physical_outcome"]
    connection = sqlite3.connect((folder / "runtime.db").as_uri() + "?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        attempts = [dict(r) for r in connection.execute("SELECT * FROM simulation_job_attempts")]
        leases = [dict(r) for r in connection.execute("SELECT * FROM simulation_job_leases")]
        events = [dict(r) for r in connection.execute("SELECT * FROM simulation_job_events ORDER BY sequence")]
        assert len(attempts) == len(leases) == 1
        assert attempts[0]["result"] == "SUCCEEDED" and attempts[0]["attempt"] == 1
        assert attempts[0]["job_id"] == leases[0]["job_id"] == result["job_id"]
        assert leases[0]["released_at"] and leases[0]["heartbeat_at"]
        assert events[-1]["next_status"] == "SUCCEEDED"
    finally:
        connection.close()
    entries = read(folder / "evidence-manifest.json")["files"]
    assert len({r["path"] for r in entries}) == len(entries)
    for entry in entries:
        path = (folder / entry["path"]).resolve()
        assert path.is_relative_to(folder.resolve())
        assert path.stat().st_size == entry["bytes"] and digest(path) == entry["sha256"]
        manifest_files += 1
    rows.append({"case": name, "split": name.rsplit("-", 1)[0], "component_success": True,
        "physical_rescore": asdict(outcome), "samples": len(samples), "safety_checks": len(checks),
        "frames": len(episode["marker_frames"]), "source_inventory_members":599,
        "result_sha256": digest(folder / "result.json"), "manifest_sha256": digest(folder / "evidence-manifest.json"),
        "lease_id": leases[0]["lease_id"], "lease_released":True, "attempts":1})
audit = read(PROCESS / "offline-regression/frame-audit-02/summary.json")
old = read(PROCESS / "offline-regression/frame-audit-02/v3.json")["rows"]
current = read(PROCESS / "offline-regression/frame-audit-02/current.json")["rows"]
assert audit["frames"] == len(old) == len(current) == 589
assert audit["new_grounding_rejections"] == 0
assert all(a["marker"] == b["marker"] and a["geometry"] == b["geometry"] for a,b in zip(old,current,strict=True))
report = {"scope":"OFFLINE_FROZEN_OUTPUT_NEW_WORKER_REGRESSION_NOT_NEW_MODEL_E2E_OR_GENERALIZATION",
    "denominator":27,"successes":27,"by_split":dict(Counter(r["split"] for r in rows)),
    "physical_rescores_passed":27,"manifest_files_verified":manifest_files,
    "per_step_samples":sum(r["samples"] for r in rows),"safety_checks":sum(r["safety_checks"] for r in rows),
    "new_closed_loop_frames":sum(r["frames"] for r in rows),"new_model_requests":0,"network_attempts":0,
    "frozen_frame_audit": {"frames":589,"marker_differences":0,"geometry_differences":0,"new_rejections":0},
    "entry_sha256":{name:digest(ROOT/name) for name in ENTRY_PATHS},"cases":rows}
output = Path('/tmp/bigsmall-v4-execution/final-offline-evidence-verification.json')
with output.open('x') as stream:
    json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps({k:v for k,v in report.items() if k not in {'cases','entry_sha256'}},ensure_ascii=False))
