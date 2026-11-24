import copy
import importlib.util
from pathlib import Path

import pytest

from cloud_edge_robot_arm.research.native_calibration_collection import source_inventory
from cloud_edge_robot_arm.research.native_collection_grounding import geometry_registration
from cloud_edge_robot_arm.vision.marker_families import (
    PREPARE_ONLY_FAMILY,
    SIDE_PREPARE_ONLY_FAMILY,
)

ROOT = Path(__file__).resolve().parents[1]


def test_build_exports_exact_baseline_and_refuses_drift(tmp_path):
    name = "scripts.graduation.g1_mount_runtime_build"
    assert importlib.util.find_spec(name), "missing pinned one-site runtime builder"
    from scripts.graduation.g1_mount_runtime_build import build, configure_vision, load_lock

    original = ROOT / "scripts/graduation/dynamic_vision.py"
    with pytest.raises(ValueError, match="SHA256"):
        configure_vision(original.read_bytes() + b"\n")
    runtime = tmp_path / "runtime-source"
    lock = build(ROOT, runtime)
    assert load_lock(runtime) == lock
    assert (runtime / "scripts/graduation/dynamic_vision.py").read_bytes() == configure_vision(
        original.read_bytes()
    )
    assert lock["source_changes"] == ["scripts/graduation/dynamic_vision.py"]
    changed = runtime / "src/cloud_edge_robot_arm/vision/servo.py"
    assert changed.read_bytes() == (ROOT / changed.relative_to(runtime)).read_bytes()
    changed.write_bytes(changed.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="SHA256"):
        load_lock(runtime)


def test_allocation_binds_both_native_families_and_rejects_crossed_inputs():
    name = "scripts.graduation.g1_mount_trials"
    assert importlib.util.find_spec(name), "missing allocation family binding"
    from scripts.graduation.g1_mount_trials import check_registration

    baseline = SIDE_PREPARE_ONLY_FAMILY
    candidate = PREPARE_ONLY_FAMILY
    geometry = geometry_registration(marker_family_id=candidate)
    catalog = source_inventory(marker_family_id=candidate)
    asset = geometry["pose_marker"]["marked_asset_sha256"]
    assert check_registration(candidate, geometry, asset, catalog).marker_family_id == candidate
    baseline_geometry = geometry_registration(marker_family_id=baseline)
    baseline_catalog = source_inventory(marker_family_id=baseline)
    baseline_sha = baseline_geometry["pose_marker"]["marked_asset_sha256"]
    assert check_registration(baseline, baseline_geometry, baseline_sha, baseline_catalog)
    for field, wrong in [
        ("marker_to_object", baseline_geometry["marker_to_object"]),
        ("asset_path", baseline_geometry["asset_path"]),
        ("camera", {**geometry["camera"], "calibration_version": "other"}),
    ]:
        with pytest.raises(ValueError):
            check_registration(candidate, {**geometry, field: wrong}, asset, catalog)
    with pytest.raises(ValueError):
        check_registration(candidate, geometry, baseline_sha, catalog)
    with pytest.raises(ValueError):
        check_registration(candidate, geometry, asset, baseline_catalog)


def test_command_readback_matches_native_dispatch_receipts_and_half_open_range():
    name = "scripts.graduation.g1_mount_trials"
    assert importlib.util.find_spec(name), "missing original command and receipt reader"
    from scripts.graduation.g1_mount_trials import command_readback

    action = {
        "skill": "APPROACH",
        "dispatch_step": 10,
        "backend_return_step": 20,
        "executor_entered": True,
        "command_records": 2,
        "dispatched": True,
        "accepted_command_types": {"joint_target": 2},
        "controller_return_step": 20,
        "return_evidence": {"absolute_step": 20, "elapsed_steps": 10, "success": True},
    }
    commands = [
        dict(
            type="joint_target",
            reason="",
            accepted=True,
            episode_id="ep",
            command_seq=seq,
            physics_step=at,
        )
        for seq, at in ((1, 10), (2, 15))
    ]
    receipt = dict(skill="APPROACH", step_id="step-1", attempt=1, success=True)
    audit = [
        {"phase": "actual_command_records", "skill": "APPROACH", "first_seq": 1, "rows": commands},
        {"phase": "actual_executor_return", "receipt": receipt},
        {"phase": "controller", "receipt": receipt},
    ]
    untouched = {"skill": "GRASP", "status": "NOT_RUN"}
    rows = command_readback([action, untouched], audit, "ep")
    assert rows[0]["command_seq_half_open"] == [1, 3]
    assert rows[0]["verified_original_receipt"]
    assert len(rows) == 1
    for tamper in ("foreign_episode", "swapped_receipt", "duplicate_batch", "missing_receipt"):
        changed = copy.deepcopy(audit)
        if tamper == "foreign_episode":
            changed[0]["rows"][0]["episode_id"] = "unrelated"
        if tamper == "swapped_receipt":
            changed[-1]["receipt"] = {**receipt, "step_id": "step-2"}
        if tamper == "duplicate_batch":
            changed.append(changed[0])
        if tamper == "missing_receipt":
            changed.pop(1)
        with pytest.raises(ValueError):
            command_readback([action, untouched], changed, "ep")


def test_trial_issue_rejects_missing_selection_plan_and_changed_old_attempt_count():
    from scripts.graduation import g1_mount_trials as trials

    assert hasattr(trials, "check_issue_inputs"), "missing pre-issue provenance and retry gate"
    plan = {
        "stage_order": ["A"],
        "attempts_per_slot": 1,
        "slots": [{"reset_fixture_center_m": [1, 2, 3]}],
    }
    selection = {"plan_sha256": trials.PLAN_SHA}
    old = {
        "case": {"visual_stages_in_order": ["A"], "attempts": 1},
        "intent_descriptor": {"stages": ["A"]},
    }
    historic = {"cases": [{"reset_fixture_center_m": [4, 5, 6]}]}
    trials.check_issue_inputs(plan, selection, old, historic)
    with pytest.raises(ValueError):
        trials.check_issue_inputs(plan, {}, old, historic)
    old["case"]["attempts"] = 2
    with pytest.raises(ValueError):
        trials.check_issue_inputs(plan, selection, old, historic)
