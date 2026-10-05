"""Research provenance counts only new, authentic physics evidence."""

from __future__ import annotations

from scripts.verify_phase11_1_simulation_runtime import _draft

from cloud_edge_robot_arm.research.models import RunProvenance, StageEvidence, StageStatus
from cloud_edge_robot_arm.research.provenance import audit_provenance


def _record(**changes: object) -> RunProvenance:
    values: dict[str, object] = {
        "run_id": "new-1",
        "source_tree_hash": "tree-1",
        "scene_group_id": "scene-1",
        "split_role": "TEST",
        "model_snapshot_hash": "model-1",
        "observation_hashes": ["rgb-1", "depth-1"],
        "physics_steps": 5,
        "evidence_kind": "PHYSICS",
        "task_success": True,
        "stages": [
            StageEvidence(stage="PERCEPTION", status=StageStatus.REAL, source_hashes=["rgb-1"]),
            StageEvidence(stage="INFERENCE", status=StageStatus.REAL, source_hashes=["vlm-1"]),
            StageEvidence(stage="ACTION", status=StageStatus.REAL, source_hashes=["physics-1"]),
        ],
    }
    values.update(changes)
    return RunProvenance.model_validate(values)


def test_mock_or_plan_is_not_physical_success() -> None:
    records = [
        _record(run_id="mock", evidence_kind="MOCK"),
        _record(run_id="plan", evidence_kind="PLANNING"),
        _record(run_id="physics"),
    ]
    audit = audit_provenance(records)
    assert audit.success_denominator == 3
    assert audit.physical_success_count == 1


def test_missing_model_is_blocked() -> None:
    record = _record(
        model_snapshot_hash=None,
        physics_steps=0,
        task_success=False,
        stages=[
            StageEvidence(stage="INFERENCE", status=StageStatus.BLOCKED, reason="model unavailable")
        ],
    )
    audit = audit_provenance([record])
    assert audit.success_denominator == 1
    assert audit.physical_success_count == 0
    assert audit.blocked_reasons == {"new-1": "missing model snapshot"}


def test_historical_runs_are_not_new_denominator() -> None:
    audit = audit_provenance([_record(cohort="HISTORICAL", run_id="old-1")])
    assert audit.historical_count == 1
    assert audit.success_denominator == 0
    assert audit.physical_success_count == 0


def test_pre_action_block_keeps_denominator_without_fake_steps() -> None:
    record = _record(
        physics_steps=0,
        task_success=False,
        blocked_reason="model load failed",
        stages=[
            StageEvidence(stage="PERCEPTION", status=StageStatus.REAL, source_hashes=["rgb-1"]),
            StageEvidence(
                stage="INFERENCE", status=StageStatus.BLOCKED, reason="model load failed"
            ),
            StageEvidence(stage="ACTION", status=StageStatus.NOT_EXECUTED),
        ],
    )
    audit = audit_provenance([record])
    assert audit.success_denominator == 1
    assert audit.physical_success_count == 0
    assert audit.occurred_stage_count == 2
    assert audit.real_stage_count == 1
    assert audit.stage_coverage == 2 / 3
    assert audit.stage_authenticity == 1 / 2
    assert audit.stage_authenticity_by_name == {
        "PERCEPTION": {"real": 1, "occurred": 1},
        "INFERENCE": {"real": 0, "occurred": 1},
    }


def test_same_scene_across_methods_is_pairing_not_leakage() -> None:
    audit = audit_provenance([_record(run_id="method-a"), _record(run_id="method-b")])
    assert audit.cross_split_scene_groups == {}
    assert audit.leakage_count == 0


def test_same_scene_across_splits_is_leakage() -> None:
    audit = audit_provenance([_record(run_id="train", split_role="TRAIN"), _record(run_id="test")])
    assert audit.cross_split_scene_groups == {"scene-1": ["TEST", "TRAIN"]}
    assert audit.leakage_count == 1


def test_online_ground_truth_is_leakage() -> None:
    audit = audit_provenance([_record(ground_truth_exposed_online=True)])
    assert audit.leakage_count == 1
    assert audit.physical_success_count == 0


def test_missing_inference_stage_cannot_be_physical_success() -> None:
    record = _record(
        stages=[
            StageEvidence(stage="PERCEPTION", status=StageStatus.REAL, source_hashes=["rgb-1"]),
            StageEvidence(stage="ACTION", status=StageStatus.REAL, source_hashes=["physics-1"]),
        ]
    )
    audit = audit_provenance([record])
    assert audit.physical_success_count == 0
    assert audit.audit_issues == {"new-1": ["missing INFERENCE stage"]}


def test_duplicate_core_stage_cannot_be_physical_success() -> None:
    record = _record(
        stages=[
            StageEvidence(stage="PERCEPTION", status=StageStatus.REAL, source_hashes=["rgb-1"]),
            StageEvidence(stage="INFERENCE", status=StageStatus.REAL, source_hashes=["vlm-1"]),
            StageEvidence(stage="INFERENCE", status=StageStatus.REAL, source_hashes=["vlm-2"]),
            StageEvidence(stage="ACTION", status=StageStatus.REAL, source_hashes=["physics-1"]),
        ]
    )
    audit = audit_provenance([record])
    assert audit.physical_success_count == 0
    assert audit.audit_issues == {"new-1": ["duplicate INFERENCE stage"]}


def test_real_stage_without_source_is_not_authentic() -> None:
    record = _record(
        stages=[
            StageEvidence(stage="PERCEPTION", status=StageStatus.REAL),
            StageEvidence(stage="INFERENCE", status=StageStatus.REAL, source_hashes=["vlm-1"]),
            StageEvidence(stage="ACTION", status=StageStatus.REAL, source_hashes=["physics-1"]),
        ]
    )
    audit = audit_provenance([record])
    assert audit.real_stage_count == 2
    assert audit.stage_authenticity == 2 / 3
    assert audit.physical_success_count == 0
    assert audit.audit_issues == {"new-1": ["PERCEPTION REAL stage has no source hashes"]}


def test_duplicate_run_id_does_not_expand_denominator() -> None:
    audit = audit_provenance([_record(), _record()])
    assert audit.success_denominator == 1
    assert audit.physical_success_count == 1
    assert audit.duplicate_run_ids == ["new-1"]


def test_conflicting_duplicate_run_reports_leakage_and_invalidates_success() -> None:
    audit = audit_provenance(
        [
            _record(split_role="TRAIN"),
            _record(split_role="TEST", ground_truth_exposed_online=True),
        ]
    )
    assert audit.success_denominator == 1
    assert audit.physical_success_count == 0
    assert audit.duplicate_run_ids == ["new-1"]
    assert audit.cross_split_scene_groups == {"scene-1": ["TEST", "TRAIN"]}
    assert audit.leakage_count == 2
    assert audit.audit_issues == {"new-1": ["conflicting duplicate run ID"]}


def test_missing_core_stage_reduces_coverage() -> None:
    audit = audit_provenance(
        [
            _record(
                stages=[
                    StageEvidence(
                        stage="PERCEPTION", status=StageStatus.REAL, source_hashes=["rgb-1"]
                    ),
                    StageEvidence(
                        stage="ACTION", status=StageStatus.REAL, source_hashes=["physics-1"]
                    ),
                ]
            )
        ]
    )
    assert audit.expected_stage_count == 3
    assert audit.stage_coverage == 2 / 3


def test_blank_hash_entries_are_not_authentic_sources() -> None:
    record = _record(
        observation_hashes=[" "],
        stages=[
            StageEvidence(stage="PERCEPTION", status=StageStatus.REAL, source_hashes=[""]),
            StageEvidence(stage="INFERENCE", status=StageStatus.REAL, source_hashes=["  "]),
            StageEvidence(stage="ACTION", status=StageStatus.REAL, source_hashes=["\t"]),
        ],
    )
    audit = audit_provenance([record])
    assert audit.real_stage_count == 0
    assert audit.stage_authenticity == 0
    assert audit.physical_success_count == 0
    assert audit.blocked_reasons == {"new-1": "missing RGB-D observation hashes"}


def test_historical_verifier_draft_selects_legacy_pipeline() -> None:
    assert _draft("MOCK", "S01_NORMAL_STATIC", "PCSC", 0)["input_mode"] == "LEGACY_PIPELINE"
    assert _draft("MUJOCO", "S01_NORMAL_STATIC", "PCSC", 0)["input_mode"] == "LEGACY_PIPELINE"
