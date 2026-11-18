"""Explicit software lifecycle evidence cannot stand in for RGB-D or research runs."""

import json

import pytest

from cloud_edge_robot_arm.final_evaluation import validation
from cloud_edge_robot_arm.final_evaluation.adapters.base import Phase12RunContext
from cloud_edge_robot_arm.final_evaluation.adapters.simulation_runtime import Phase11RuntimeAdapter
from cloud_edge_robot_arm.final_evaluation.models import Phase12Backend


def context(root):
    return Phase12RunContext(
        run_id="explicit-lifecycle",
        experiment_id="F20_STRESS_AND_RECOVERY",
        scenario_id="S01_NORMAL_STATIC",
        backend=Phase12Backend.MOCK,
        control_mode="PCSC",
        seed=0,
        repetition=0,
        output_root=root,
    )


def test_explicit_lifecycle_collects_real_execution_recovery_and_competition(tmp_path):
    result = Phase11RuntimeAdapter(lifecycle_only=True).run(context(tmp_path))
    receipt = json.loads((tmp_path / result.source_artifact_path).read_text())
    assert result.runtime_invoked and result.runtime_completed
    assert result.status == "SUCCESS"
    assert result.authoritative_for_thesis is False
    assert receipt["validation_scope"] == "SOFTWARE_LIFECYCLE_ONLY"
    assert validation._runtime_receipt_internal_hash_valid(receipt)
    assert validation._recovery_evidence_valid(receipt)
    assert validation._duplicate_competition_evidence_valid(receipt)
    assert validation._terminal_artifact_paths_valid(receipt)
    assert receipt["duplicate_competition_evidence"]["runner_invocation_count"] == 1
    probes = [
        receipt["main_job"],
        receipt["recovery_evidence"],
        receipt["duplicate_competition_evidence"],
    ]
    for probe in probes:
        proof = probe["execution_evidence"]
        assert proof["input_mode"] == "LEGACY_PIPELINE"
        assert proof["executor_invoked"] and proof["executor_returned"]
        assert proof["evidence_valid"] and proof["artifacts_verified"]
        assert proof["attempt_completed"] and proof["lease_released"]
    assert receipt["real_controller_contacted"] is False
    assert receipt["hardware_motion_observed"] is False


def test_default_runtime_adapter_keeps_camera_block_and_zero_executor(tmp_path):
    result = Phase11RuntimeAdapter().run(context(tmp_path))
    receipt = json.loads((tmp_path / result.source_artifact_path).read_text())
    assert result.status == "BLOCKED_BY_ENV"
    assert result.runtime_invoked is result.runtime_completed is False
    assert result.authoritative_for_thesis is False
    assert "RGBD_CAMERA_REQUIRED" in result.failure_type
    for probe in (
        receipt["main_job"],
        receipt["recovery_evidence"],
        receipt["duplicate_competition_evidence"],
    ):
        assert probe["execution_evidence"]["input_mode"] == "RGBD"
        assert probe["execution_evidence"]["executor_invoked"] is False


@pytest.mark.parametrize("value", [1, "true", None])
def test_lifecycle_switch_requires_explicit_boolean(value):
    with pytest.raises(ValueError, match="boolean"):
        Phase11RuntimeAdapter(lifecycle_only=value)


def test_supplement_links_original_blocked_row_without_replacing_it(tmp_path):
    from scripts.run_phase12_runtime_lifecycle import run_supplement

    original = tmp_path / "original.jsonl"
    data = {
        "run_id": "original-f20",
        "experiment_id": "F20_STRESS_AND_RECOVERY",
        "scenario_id": "S15_SQLITE_RESTART_DURING_RUN",
        "backend": "MOCK",
        "control_mode": "PCSC",
        "seed": 0,
        "repetition": 0,
        "status": "BLOCKED_BY_ENV",
        "profile": "validation",
        "runtime_invoked": False,
        "runtime_completed": False,
        "actual_runner_invoked": False,
        "failure_type": (
            "main: RGBD_CAMERA_REQUIRED; recovery: RGBD_CAMERA_REQUIRED; "
            "duplicate: RGBD_CAMERA_REQUIRED"
        ),
    }
    original.write_text(json.dumps(data) + "\n")
    before = original.read_bytes()
    result = run_supplement(output=tmp_path / "supplement", source_rows=original, count=1)
    assert result["status"] == "SOFTWARE_LIFECYCLE_EVIDENCE_COMPLETE"
    assert result["full_profile_execution"] == "NOT_RUN"
    assert result["physical_qualification"] == "NOT_GRANTED"
    assert result["rows"][0]["original_run_id"] == "original-f20"
    assert result["rows"][0]["new_run_id"] != "original-f20"
    assert result["rows"][0]["checks"] and all(result["rows"][0]["checks"].values())
    assert original.read_bytes() == before


@pytest.mark.parametrize("count", [0, 19, True])
def test_supplement_rejects_invalid_count_before_creating_output(tmp_path, count):
    from scripts.run_phase12_runtime_lifecycle import run_supplement

    out = tmp_path / "supplement"
    with pytest.raises(ValueError):
        run_supplement(output=out, count=count)
    assert not out.exists()


def blocked_row():
    return {
        "run_id": "original-f20",
        "experiment_id": "F20_STRESS_AND_RECOVERY",
        "scenario_id": "S15_SQLITE_RESTART_DURING_RUN",
        "backend": "MOCK",
        "control_mode": "PCSC",
        "seed": 0,
        "repetition": 0,
        "status": "BLOCKED_BY_ENV",
        "profile": "validation",
        "runtime_invoked": False,
        "runtime_completed": False,
        "actual_runner_invoked": False,
        "failure_type": (
            "main: RGBD_CAMERA_REQUIRED; recovery: RGBD_CAMERA_REQUIRED; "
            "duplicate: RGBD_CAMERA_REQUIRED"
        ),
    }


@pytest.mark.parametrize(
    "damage",
    [
        "duplicate",
        "empty_id",
        "success",
        "missing_status",
        "entered",
        "completed",
        "legacy_alias",
        "missing_runtime",
        "missing_reason",
        "bad_seed",
        "bad_repetition",
        "bad_mode",
    ],
)
def test_source_rows_are_rejected_before_output_or_adapter(tmp_path, monkeypatch, damage):
    from scripts import run_phase12_runtime_lifecycle as module

    rows = [blocked_row()]
    changes = {
        "empty_id": ("run_id", ""),
        "success": ("status", "SUCCESS"),
        "entered": ("runtime_invoked", True),
        "completed": ("runtime_completed", True),
        "legacy_alias": ("actual_runner_invoked", True),
        "missing_reason": ("failure_type", ""),
        "bad_seed": ("seed", True),
        "bad_repetition": ("repetition", -1),
        "bad_mode": ("control_mode", "OTHER"),
    }
    if damage == "duplicate":
        rows.append(dict(rows[0]))  # Duplicate is outside count=1; still must be rejected.
    elif damage == "missing_status":
        rows[0].pop("status")
    elif damage == "missing_runtime":
        rows[0].pop("runtime_invoked")
    else:
        field, value = changes[damage]
        rows[0][field] = value
    path = tmp_path / "source.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    monkeypatch.setattr(
        module,
        "Phase11RuntimeAdapter",
        lambda **kwargs: pytest.fail("invalid input reached adapter construction"),
    )
    out = tmp_path / "new-output"
    with pytest.raises(ValueError):
        module.run_supplement(output=out, source_rows=path, count=1)
    assert not out.exists()


def test_supplement_source_identity_is_independent_of_caller_cwd(tmp_path, monkeypatch):
    from scripts import run_phase12_runtime_lifecycle as module

    from cloud_edge_robot_arm.final_evaluation.provenance import git_commit

    monkeypatch.chdir(tmp_path)
    identity = module.source_identity()
    assert identity["commit"] == git_commit(module.ROOT) != "UNKNOWN"
    assert {
        "scripts/run_phase12_runtime_lifecycle.py",
        "src/cloud_edge_robot_arm/final_evaluation/adapters/simulation_runtime.py",
    }.issubset(identity["files"])
    assert all(len(value) == 64 for value in identity["files"].values())


@pytest.mark.parametrize("damage", ["unregistered", "other_error_code", "duplicate_key", "nan"])
def test_original_source_uses_registered_scenario_exact_code_and_strict_json(damage):
    from scripts import run_phase12_runtime_lifecycle as module

    row = blocked_row()
    if damage == "unregistered":
        row["scenario_id"] = "S99_NOT_REGISTERED"
    elif damage == "other_error_code":
        row["failure_type"] = "NOT_RGBD_CAMERA_REQUIRED"
    raw = json.dumps(row)
    if damage == "duplicate_key":
        raw = raw.replace(
            '"runtime_invoked": false', '"runtime_invoked": true, "runtime_invoked": false'
        )
    elif damage == "nan":
        raw = raw[:-1] + ', "unused": NaN}'
    with pytest.raises(ValueError):
        module.read_original_rows(raw.encode(), count=1)


@pytest.mark.parametrize("damage", ["wrong_profile", "missing_profile", "negated", "other_stage"])
def test_linked_source_requires_validation_profile_and_emitted_block_clauses(damage):
    from scripts import run_phase12_runtime_lifecycle as module

    row = blocked_row()
    if damage == "wrong_profile":
        row["profile"] = "full"
    elif damage == "missing_profile":
        row.pop("profile")
    elif damage == "negated":
        row["failure_type"] = "main: no RGBD_CAMERA_REQUIRED occurred"
    else:
        row["failure_type"] = "unrelated_stage: RGBD_CAMERA_REQUIRED"
    with pytest.raises(ValueError):
        module.read_original_rows(json.dumps(row).encode(), count=1)
