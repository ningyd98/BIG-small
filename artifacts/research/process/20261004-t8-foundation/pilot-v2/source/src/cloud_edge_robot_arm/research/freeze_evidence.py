"""Reconstruct initial freeze inputs from immutable evidence, never summary flags."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from cloud_edge_robot_arm.datasets.rgbd.models import content_digest
from cloud_edge_robot_arm.research.pilot import derive_tcap
from cloud_edge_robot_arm.research.pilot_audit import audit_pilot, physical_sample, read_json
from cloud_edge_robot_arm.research.protocol import (
    STRATA,
    OpportunitySeed,
    ProtocolSpec,
    file_hash,
)
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot


def initial_spec_from_evidence(directory: Path) -> ProtocolSpec:
    report = read_json(directory / "summary.json")
    if report.get("method_id") != "B0":
        raise ValueError("initial protocol requires actual B0 foundation pilot")
    # A report can claim anything; completeness and quality come from raw artifacts.
    assignments = read_json(directory / "assignments.json")
    if len(assignments) != 120 or Counter(r["stratum_id"] for r in assignments) != (
        Counter({s: 10 for s in STRATA})
    ):
        raise ValueError("foundation requires all 120 balanced preregistered records")
    audit = audit_pilot(directory)
    if not audit["physical_reconstruction_valid"]:
        raise ValueError(f'foundation physical evidence invalid: {audit["errors"]}')
    measured = audit["summary"]
    if measured["cost_publication_mismatches"] or measured["inflight_requests"]:
        raise ValueError("foundation request costs are inconsistent or unsettled")
    if measured["blocked"] or measured["nominal_success_rate"] < .9 or (
        measured["success_rate_all_assigned"] < .8 or measured["safety_violations"] / 120 > .01
    ):
        raise ValueError("NO_FEASIBLE_BASELINE; cannot accept initial protocol")
    pools = read_json(directory / "pools.json")
    expected = {"foundation": 120, "power": 120, "formal": 2400, "recovery": 200, "ood": 300}
    groups: set[str] = set(read_json(directory / "excluded-groups.json"))
    for name, count in expected.items():
        rows = pools.get(name, [])
        if len(rows) != count:
            raise ValueError(f"missing {name} pool evidence")
        for row in rows:
            group = row["scene"]["group_id"]
            if group in groups:
                raise ValueError("cross-pool scene group leakage")
            groups.add(group)
            if not row.get("perturbation"):
                raise ValueError("missing preregistered perturbation schedule")
    if pools["foundation"] != assignments:
        raise ValueError("pilot assignment/pool mismatch")
    source_hashes = read_json(directory / "source-hashes.json")
    for relative, digest in source_hashes.items():
        archived = directory / "source" / relative
        if not archived.is_relative_to(directory) or not archived.is_file() or (
            file_hash(archived) != digest
        ):
            raise ValueError("missing or drifted archived source evidence")
    model = ModelConfigSnapshot(**read_json(directory / "model-probe" / "model-frozen.json"))
    from scripts.probe_rgbd_model import verify_frozen_bundle

    if not verify_frozen_bundle(directory / "model-probe"):
        raise ValueError("model probe evidence is missing or drifted")
    if model.digest() != report.get("model_snapshot_hash"):
        raise ValueError("pilot model snapshot mismatch")
    opportunities = read_json(directory / "opportunities.json")
    if not opportunities:
        raise ValueError("missing fixed opportunity snapshots")
    ids = set()
    for item in opportunities:
        seed = OpportunitySeed.model_validate(item["seed"])
        if seed.opportunity_id in ids or seed.group_id not in {
            row["scene"]["group_id"] for row in pools["formal"]
        }:
            raise ValueError("opportunity identity is duplicate or outside formal pool")
        ids.add(seed.opportunity_id)
        hashes = item["payload_hashes"]
        if not hashes or content_digest(hashes) != seed.observation_hash:
            raise ValueError("opportunity snapshot hash mismatch")
        for relative, digest in hashes.items():
            path = (directory / relative).resolve()
            if not path.is_relative_to(directory.resolve()) or file_hash(path) != digest:
                raise ValueError("opportunity snapshot payload drift")
        # This proof is produced by the independent opportunity evaluator, not online.
        proof = item["independent_label_evidence"]
        expected_label = "UNKNOWN" if not proof["sensor_and_identity_sufficient"] else (
            "VALID" if proof["geometry_safe"] and proof["within_validity"] else "INVALID"
        )
        if proof["rule_version"] != "rgbd.opportunity.v1" or seed.oracle_label != expected_label:
            raise ValueError("opportunity independent label mismatch")
    faults = read_json(directory / "recovery-faults.json")
    fault_groups = {row["scene"]["group_id"] for row in pools["recovery"]}
    if len(faults) != 200 or {r["group_id"] for r in faults} != fault_groups:
        raise ValueError("recovery requires all 200 independent frozen faults")
    for item in faults:
        # Full independent successful teacher traces must demonstrate recoverability.
        path = (directory / item["recoverability_evidence_path"]).resolve()
        if not path.is_relative_to(directory.resolve()) or file_hash(path) != (
            item["recoverability_evidence_hash"]
        ):
            raise ValueError("recoverability evidence missing or drifted")
        if not item.get("fault"):
            raise ValueError("missing fixed recovery fault parameters")
        from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
            CompletionCriteria,
            evaluate_evidence,
        )

        samples = [physical_sample(row) for row in read_json(path)]
        if not samples or not evaluate_evidence(
            samples, CompletionCriteria("object", "target_region"),
            evaluation_start_step=samples[0].physics_step,
        ).success:
            raise ValueError("fault recoverability requires independent successful trajectory")
    return ProtocolSpec(
        tcap_s=derive_tcap([r["wall_duration_s"] for r in audit["cases"] if r["success"]]),
        pool_hashes={name: content_digest(rows) for name, rows in pools.items()},
        model_snapshot_hash=model.digest(), opportunity_hash=content_digest(opportunities),
        recovery_fault_manifest_hash=content_digest(faults),
    )
