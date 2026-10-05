"""Read-only reconstruction of pilot outcomes and final request costs."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec, content_digest
from cloud_edge_robot_arm.research.cost_ledger import RequestCost
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    PhysicalSample,
    evaluate_evidence,
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def physical_sample(row: dict[str, Any]) -> PhysicalSample:
    values = dict(row)
    for key in ("contact_pairs", "self_collision_checked_pairs"):
        values[key] = tuple(tuple(pair) for pair in values.get(key, ()))
    return PhysicalSample(**values)


def audit_pilot(directory: Path) -> dict[str, Any]:
    assignments = read_json(directory / "assignments.json")
    results = read_json(directory / "results.json")
    ids = [r["assignment_id"] for r in assignments]
    errors: list[str] = []
    if len(set(ids)) != len(ids) or {r["assignment_id"] for r in results} != set(ids):
        errors.append("assignment/result identities are incomplete or duplicated")
    rows = {r["assignment_id"]: r for r in results}
    cases = []
    for assignment in assignments:
        case_id = assignment["assignment_id"]
        case = directory / "cases" / case_id
        row = rows.get(case_id, {})
        entry: dict[str, Any] = {"assignment_id": case_id,
            "stratum_id": assignment["stratum_id"], "success": False,
            "blocked": bool(row.get("blocked")), "errors": []}
        try:
            scene = SceneSpec.model_validate(assignment["scene"])
            if scene.scene_hash != assignment["scene_hash"]:
                raise ValueError("scene hash mismatch")
            samples = [physical_sample(r) for r in read_json(case / "physical-evidence.json")]
            if not samples:
                raise ValueError("missing independent physical samples")
            physical = evaluate_evidence(samples, CompletionCriteria("object", "target_region"),
                                        evaluation_start_step=samples[0].physics_step)
            recomputed = json.loads(json.dumps(asdict(physical)))
            if recomputed != read_json(case / "physical-outcome.json"):
                entry["errors"].append("independent physical result does not reproduce")
            episode = read_json(case / "episode.json")
            expected = bool(physical.success and episode["online_reported_complete"]
                            and episode["terminal_reason"] is None)
            if expected != episode["success"] or expected != row.get("success"):
                entry["errors"].append("visual success conjunction mismatch")
            costs = read_json(case / "costs.json")
            requests = [RequestCost.model_validate(r) for r in costs["requests"]]
            sent = [r for r in requests if r.sent_at is not None]
            if len(sent) != costs["summary"]["model_requests"]:
                entry["errors"].append("actual request denominator mismatch")
            entry.update(success=expected, physical_success=physical.success,
                online_reported_complete=episode["online_reported_complete"],
                safety_violation=physical.safety_violation, evidence_samples=len(samples),
                terminal_reason=row.get("terminal_reason"),
                wall_duration_s=row["wall_duration_s"], costs=costs["summary"],
                cost_publications_consistent=(row["costs"] == costs["summary"]
                    == read_json(case / "case-result.json")["costs"]),
                inflight_requests=sum(r.status == "IN_FLIGHT" for r in requests),
                requests_by_status=dict(Counter(r.status for r in sent)),
                supervision_ticks=sum(r.get("ticks", 0) for r in
                    episode["verification_records"] if r.get("layer") == "SUPERVISION_SUMMARY"),
                perturbation=assignment.get("perturbation"),
                legacy_level=scene.seed % 3 if "perturbation" not in assignment else None)
        except (ValueError, KeyError, OSError) as exc:
            entry["errors"].append(f"{type(exc).__name__}: {exc}")
        cases.append(entry)
        errors.extend(f'{case_id}: {error}' for error in entry["errors"])
    nominal = [r for r in cases if r["stratum_id"].startswith("STATIC")]
    successes = sum(r["success"] for r in cases)
    summary = {
        "assigned": len(ids), "recorded": len(cases), "succeeded": successes,
        "success_rate_all_assigned": successes / len(ids) if ids else None,
        "nominal_success_rate": sum(r["success"] for r in nominal) / len(nominal)
                                 if nominal else None,
        "blocked": sum(r["blocked"] for r in cases),
        "safety_violations": sum(r.get("safety_violation", False) for r in cases),
        "online_complete_claims": sum(r.get("online_reported_complete", False) for r in cases),
        "false_completion_claims": sum(r.get("online_reported_complete", False)
                                      and not r.get("physical_success") for r in cases),
        "cost_publication_mismatches": sum(not r.get("cost_publications_consistent", False)
                                           for r in cases),
        "actual_model_requests": sum(r.get("costs", {}).get("model_requests", 0) for r in cases),
        "actual_application_bytes": sum(r.get("costs", {}).get("application_bytes", 0)
                                        for r in cases),
        "inflight_requests": sum(r.get("inflight_requests", 0) for r in cases),
        "independent_physical_samples": sum(r.get("evidence_samples", 0) for r in cases),
    }
    return {"schema_version": "rgbd.pilot-audit.v1", "summary": summary,
            "errors": errors, "physical_reconstruction_valid": not errors,
            "assignment_hash": content_digest(assignments), "cases": cases}
