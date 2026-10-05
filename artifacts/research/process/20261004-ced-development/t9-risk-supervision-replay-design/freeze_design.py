"""Archive exact, pre-existing frozen references; never import production code."""

import hashlib
import json
import math
from pathlib import Path


HERE = Path(__file__).resolve().parent
BASE = HERE.parent
RAW = BASE / "risk-sources-module"
FIRST = BASE / "t9-actual-risk-source-design"
REFS = [
    *[f"src/cloud_edge_robot_arm/vision/risk/{n}.py" for n in
      ["__init__", "calibration", "features", "fit", "models"]],
    "scripts/calibrate_rgbd_risk.py",
    "configs/research/risk.yaml",
    "tests/test_rgbd_risk_calibration.py",
    *[f"src/cloud_edge_robot_arm/research/{n}.py" for n in
      ["risk_sources", "admission", "protocol", "freeze_evidence", "resource_plan"]],
    *[f"src/cloud_edge_robot_arm/vision/{n}.py" for n in
      ["role_models", "runtime_binding", "observations", "offline_reader"]],
    *[f"src/cloud_edge_robot_arm/datasets/rgbd/{n}.py" for n in
      ["models", "writer", "quality", "splitter"]],
    "src/cloud_edge_robot_arm/simulation/mujoco/episode_evaluator.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/camera.py",
    "src/cloud_edge_robot_arm/auto_mode/runtime_composition.py",
    "src/cloud_edge_robot_arm/auto_mode/joint_policy.py",
    "configs/research/ced_roles.yaml",
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(name: str, data: object) -> None:
    (HERE / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


raw_manifest = json.loads((RAW / "source-hashes.json").read_text())
first_manifest = json.loads((FIRST / "source-ref-hashes.json").read_text())
inventory = {}
origins = {}
for ref in REFS:
    origin = RAW if ref in raw_manifest else FIRST
    manifest = raw_manifest if origin == RAW else first_manifest
    original = origin / "source" / ref
    content = original.read_bytes()
    assert sha(content) == manifest[ref], ref
    target = HERE / "source" / ref
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == content, ref
    else:
        target.write_bytes(content)
    inventory[ref] = sha(content)
    origins[ref] = str(origin.relative_to(BASE))
write("source-ref-hashes.json", inventory)
write("source-origins.json", origins)
write("api-contract.json", {
    "scope": "DESIGN_ONLY",
    "first_owner_files": ["research/risk_supervision.py", "tests/test_research_risk_supervision.py"],
    "second_owner_files": ["research/risk_replay.py", "tests/test_research_risk_replay.py"],
    "entrypoints": ["RiskSupervisionAuditor(registrations).audit(evidence_id)",
                    "RiskArtifactAuditor(registrations, supervision_auditor).audit(evidence_id)"],
    "authority": "original registered sources reread, never receipt/callback/source flag",
    "calibrated_probability": "isotonic_predict(calibrated['isotonic_blocks'], predict(data, features))",
    "artifact_digest": "canonical content_digest plus separate exact raw file SHA",
    "missing_actual_inputs": "UNKNOWN; no METHOD/execution authority",
    "raw_dependency": "corrected independently reviewed reader required before genuine positive",
    "default_production_changes": [],
    "source_usage": {
        "authorized_development_train": "allowed with original components/use history",
        "viewed_or_tuned_holdouts": "not independent calibration/selection/test",
        "formal_power_G3_G4": "remain excluded per frozen protocol",
        "unknown_history": "UNKNOWN",
    },
})
write("read-only-checks.json", {
    "scope": "SOFTWARE_ONLY arithmetic illustrations; no fitting or source acceptance",
    "group_rank": [{"groups": n, "rank": math.ceil((n + 1) * .9),
                    "finite_rank_available": math.ceil((n + 1) * .9) <= n} for n in [8, 9]],
    "brier_calibrated_example": sum((p-y)**2 for p, y in zip([.2, .8], [0, 1])) / 2,
    "brier_raw_example": sum((p-y)**2 for p, y in zip([.4, .6], [0, 1])) / 2,
    "source_refs_verified": len(inventory),
    "model_fit_capture_provider_account_calls": 0,
})
write("ownership.json", {
    "scope": "DESIGN_ONLY", "owned_production_files": [],
    "owned_artifact_directory": str(HERE.relative_to(BASE)),
    "readonly_refs": sorted(inventory),
    "raw_basis_manifest_sha256": sha((RAW / "source-hashes.json").read_bytes()),
    "raw_review_state": "REPAIR_REQUIRED; historical snapshot unchanged",
})
write("report.json", {
    "scope": "DESIGN_ONLY", "status": "DESIGN_FROZEN",
    "production_edits": [], "source_ref_count": len(inventory),
    "risk_supervision": "UNKNOWN", "actual_calibration": "NOT_RUN", "METHOD": "NOT_RUN",
    "actual_clock_calibration_INITIAL_derived_commit_sources": "UNAVAILABLE",
    "raw_reader_consistency_review": "REPAIR_REQUIRED",
    "setup_failures_preserved": ["freeze-first-missing-cli.log", "inspection-shell-setup.log"],
    "frozen_reference_only": True,
})
artifacts = {str(p.relative_to(HERE)): sha(p.read_bytes())
             for p in sorted(HERE.rglob("*")) if p.is_file() and p.name != "artifact-hashes.json"}
write("artifact-hashes.json", artifacts)
for ref, digest in artifacts.items():
    assert sha((HERE / ref).read_bytes()) == digest, ref
print(json.dumps({"refs": len(inventory), "artifacts": len(artifacts),
                  "source_manifest": sha((HERE / "source-ref-hashes.json").read_bytes()),
                  "artifact_manifest": sha((HERE / "artifact-hashes.json").read_bytes())}, sort_keys=True))
