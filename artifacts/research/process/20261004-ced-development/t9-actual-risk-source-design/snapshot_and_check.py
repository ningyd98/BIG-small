"""Read-only source inspection; writes only this design artifact directory."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUTPUT = Path(__file__).resolve().parent
REFS = (
    "src/cloud_edge_robot_arm/vision/risk/models.py",
    "src/cloud_edge_robot_arm/vision/risk/features.py",
    "src/cloud_edge_robot_arm/vision/risk/fit.py",
    "src/cloud_edge_robot_arm/vision/risk/calibration.py",
    "src/cloud_edge_robot_arm/vision/risk/__init__.py",
    "scripts/calibrate_rgbd_risk.py",
    "configs/research/risk.yaml",
    "tests/test_rgbd_risk_calibration.py",
    "src/cloud_edge_robot_arm/datasets/rgbd/models.py",
    "src/cloud_edge_robot_arm/datasets/rgbd/writer.py",
    "src/cloud_edge_robot_arm/datasets/rgbd/quality.py",
    "src/cloud_edge_robot_arm/datasets/rgbd/splitter.py",
    "src/cloud_edge_robot_arm/datasets/rgbd/capture.py",
    "src/cloud_edge_robot_arm/vision/offline_reader.py",
    "src/cloud_edge_robot_arm/vision/observations.py",
    "src/cloud_edge_robot_arm/vision/runtime_binding.py",
    "src/cloud_edge_robot_arm/vision/action_evidence.py",
    "src/cloud_edge_robot_arm/vision/pose_markers.py",
    "src/cloud_edge_robot_arm/vision/pose_marker_assets.py",
    "src/cloud_edge_robot_arm/vision/role_models.py",
    "src/cloud_edge_robot_arm/research/admission.py",
    "src/cloud_edge_robot_arm/research/protocol.py",
    "src/cloud_edge_robot_arm/research/protocol_evidence.py",
    "src/cloud_edge_robot_arm/research/freeze_evidence.py",
    "src/cloud_edge_robot_arm/research/pilot.py",
    "src/cloud_edge_robot_arm/research/resource_plan.py",
    "src/cloud_edge_robot_arm/auto_mode/joint_policy.py",
    "src/cloud_edge_robot_arm/auto_mode/runtime_composition.py",
    "src/cloud_edge_robot_arm/auto_mode/runtime_events.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/backend.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/camera.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/episode_evaluator.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/motion_controller.py",
    "src/cloud_edge_robot_arm/edge/evidence/validator.py",
    "scripts/run_rgbd_pilot.py",
    "configs/research/ced_exclusions.yaml",
    "configs/research/ced_roles.yaml",
    "assets/robots/franka_panda/scene_pose_marker_v1.xml",
    "assets/robots/franka_panda/scene_pose_marker_color_v2.xml",
    "docs/superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md",
    "docs/superpowers/plans/2026-10-04-cloud-edge-device-research-roadmap.md",
    "docs/superpowers/specs/2026-10-04-cloud-edge-device-research-design.md",
    "datasets/rgbd-ced-dev-smoke-20261004/manifest.json",
    "datasets/rgbd-ced-dev-smoke-20261004/samples.jsonl",
    "datasets/rgbd-ced-dev-smoke-20261004/reports/split_audit.json",
    "datasets/rgbd-ced-dev-smoke-20261004/source.json",
    "artifacts/research/process/20261004-ced-development/t9-software/"
    "fix-round-1-genuine-capture-cli/report.json",
    "artifacts/research/process/20261004-ced-development/"
    "t7b-pose-marker-motion-development/report.md",
    "artifacts/research/process/20261004-ced-development/"
    "t7b-pose-marker-motion-development/root-independent-review.md",
    "artifacts/research/process/20261004-ced-development/"
    "t7b-pose-marker-motion-development/root-review-setup.json",
    "artifacts/research/process/20261004-ced-development/"
    "t7b-pose-marker-motion-development/development-exclusion.json",
    "artifacts/research/process/20261004-ced-development/"
    "t7b-pose-marker-motion-development/header.json",
    "artifacts/research/process/20261004-ced-development/"
    "t7b-pose-marker-motion-development/attempt-1/summary.json",
    "artifacts/research/process/20261004-ced-development/"
    "t7b-pose-marker-motion-development/attempt-1/observability.json",
    "artifacts/research/process/20261004-ced-development/"
    "t8b-module/fix-round-3-release-source-hashes.json",
    "artifacts/research/process/20261004-ced-development/"
    "t8-billing-source-design/artifact-hashes.json",
)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def function(source: str, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def call_names(node: ast.AST) -> list[str]:
    return sorted(
        {
            ast.unparse(child.func)
            for child in ast.walk(node)
            if isinstance(child, ast.Call)
        }
    )


def main() -> None:
    if (OUTPUT / "source-ref-hashes.json").exists():
        raise RuntimeError("historical source snapshot already exists; do not overwrite")
    originals: dict[str, bytes] = {}
    for name in REFS:
        source = ROOT / name
        if not source.is_file() or any(
            part.is_symlink() for part in (source, *source.parents) if part.is_relative_to(ROOT)
        ):
            raise ValueError(f"missing or symlinked inspected source: {name}")
        originals[name] = source.read_bytes()
    source_text = {name: payload.decode() for name, payload in originals.items()}
    for name, source in source_text.items():
        if name.endswith(".py"):
            ast.parse(source, filename=name)
    fit = source_text["src/cloud_edge_robot_arm/vision/risk/fit.py"]
    calibration = source_text["src/cloud_edge_robot_arm/vision/risk/calibration.py"]
    features = source_text["src/cloud_edge_robot_arm/vision/risk/features.py"]
    cli = source_text["scripts/calibrate_rgbd_risk.py"]
    admission = source_text["src/cloud_edge_robot_arm/research/admission.py"]
    native = source_text["src/cloud_edge_robot_arm/vision/action_evidence.py"]
    accepted_calls = call_names(function(cli, "accepted_records"))
    selection_calls = call_names(function(cli, "verify_selection_snapshot"))
    checks = {
        "direct_fit_writes_source_accepted_false": '"source_accepted": False' in fit,
        "cli_changes_source_accepted_true":
            "data.update(source_accepted=True, source_bindings=bindings)" in cli,
        "estimate_checks_file_flag":
            'if not data.get("source_accepted", False):' in calibration,
        "selection_does_not_call_fit_calibrate_or_predict": not (
            {"fit_risk_model", "calibrate_risk", "predict", "estimate_risk"}
            & set(selection_calls)
        ),
        "accepted_reader_has_no_raw_physics_or_initial_auditor_call": not (
            {"_trace", "_audit_actuators", "evaluate_evidence", "sample_physical_observation",
             "InitialSourceAdmissionAuditor"} & set(accepted_calls)
        ),
        "group_bound_preserves_none_skip":
            "if value is None:\n            continue" in calibration,
        "observed_motion_wall_clock":
            "(observation.captured_at - previous.captured_at).total_seconds()" in features,
        "fresh_pair_also_requires_advancing_sim_time":
            "observation.sim_time_s > previous.sim_time_s" in features,
        "method_risk_verifier_explicitly_unavailable":
            '"method_risk_source_verifier_unavailable"' in admission,
        "method_weight_verifier_explicitly_unavailable":
            '"method_weight_selection_verifier_unavailable"' in admission,
        "method_owner_explicitly_unavailable":
            '"execution_owner_registration_unavailable"' in admission,
        "native_bound_fields_unknown":
            "geometric_error_bound_m=None" in native and "motion_bound_m_s=None" in native,
    }
    assert all(checks.values()), checks
    dataset = "datasets/rgbd-ced-dev-smoke-20261004"
    manifest = json.loads(originals[f"{dataset}/manifest.json"])
    indexed = [json.loads(row) for row in originals[f"{dataset}/samples.jsonl"].splitlines()]
    observed = {
        "scope": "INDEX_FIELDS_ONLY_NOT_DATASET_ACCEPTANCE",
        "dataset": dataset,
        "manifest_status": manifest["status"],
        "indexed_sample_count": len(indexed),
        "indexed_group_id_count": len({row["group_id"] for row in indexed}),
        "indexed_risk_supervision_count": sum(
            "risk_supervision" in row.get("labels", {}) for row in indexed
        ),
        "risk_acceptance_report_present": (ROOT / dataset / "reports/risk_acceptance.json").exists(),
        "risk_selection_report_present": (ROOT / dataset / "reports/risk_selection.json").exists(),
        "actual_risk_status": "NOT_RUN",
        "method_status": "UNKNOWN",
    }
    assert observed["indexed_sample_count"] == 100
    assert observed["indexed_group_id_count"] == 100
    assert observed["indexed_risk_supervision_count"] == 0
    assert not observed["risk_acceptance_report_present"]
    assert not observed["risk_selection_report_present"]
    for name, payload in originals.items():
        path = OUTPUT / "source" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        assert path.read_bytes() == payload
        if (ROOT / name).read_bytes() != payload:
            raise RuntimeError(f"inspected source changed during design snapshot: {name}")
    hashes = {name: digest(payload) for name, payload in originals.items()}
    write_json(OUTPUT / "source-ref-hashes.json", hashes)
    write_json(OUTPUT / "read-only-audit.json", {
        "schema_version": "ced.risk-source-design-audit.v1",
        "scope": "DESIGN_ONLY",
        "source_reference_count": len(hashes),
        "source_ast_parse": "PASS",
        "boundary_checks": checks,
        "accepted_records_call_inventory": accepted_calls,
        "selection_check_call_inventory": selection_calls,
        "index_observations": observed,
        "executed_physics": False,
        "fitted_models": False,
        "production_changes": [],
        "source_hashes_are_acceptance_authority": False,
    })
    print(json.dumps({"scope": "DESIGN_ONLY", "references": len(hashes),
                      "static_boundary_checks": len(checks), "index": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
