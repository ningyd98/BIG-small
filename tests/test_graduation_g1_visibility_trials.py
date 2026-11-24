"""Development identities, runtime binding and real-witness checks for G1 repair."""

import hashlib
import importlib
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


def module(name):
    path = "scripts.graduation.g1_visibility_" + name
    assert importlib.util.find_spec(path) is not None, f"missing development {name} entry"
    return importlib.import_module(path)


def test_runtime_binds_new_estimator_at_every_live_consumer_and_scopes_sqlite():
    build = module("runtime")
    parent = Path("experiments/results/g1-formal-paired-20261124/runtime-source")
    if not parent.exists():
        pytest.skip("private registered runtime unavailable")
    adapted = build.adapted_sources(parent, (build.DETECTOR, build.GRID))
    observer = adapted[build.OBSERVER].decode()
    for caller in ("derive", "matches_current_owner", "servo_measure"):
        assert 'consumer="' + caller + '"' in observer
    assert "expected_scene(asset.SCENE_ID)" in observer
    assert "visibility.measure_frame(frame, geometry)" in observer
    assert "visibility.pose_estimate" in observer
    assert build.GRID in adapted[build.ASSET].decode()
    for filename in (build.CAPTURE, build.VISION):
        assert b"FORMAL_G1_PAIRED" not in adapted[filename]
        assert b"G1_VISIBILITY_DEVELOPMENT" in adapted[filename]
    assert b"development_identity" in adapted[build.VISION]
    assert not any(name.startswith("src/") for name in adapted)


def test_training_placements_only_accept_measured_historical_development_groups():
    trials = module("trials")
    old = [
        {
            "id": "d02-dual",
            "arm": "dual",
            "seed": 12,
            "reset_fixture_center_m": [0.464, 0.016, 0.035],
            "yaw_rad": -0.1,
        },
        {
            "id": "f01-dual",
            "arm": "dual",
            "seed": 71,
            "reset_fixture_center_m": [0.43, -0.018, 0.035],
            "yaw_rad": 0.1,
        },
    ]
    result = trials.training_placements(["d02"], old)
    assert result == [
        dict(id="d02", seed=12, reset_fixture_center_m=[0.464, 0.016, 0.035], yaw_rad=-0.1)
    ]
    for ids in (["d02", "d02"], ["f01"], ["d01"], ["../f01"]):
        with pytest.raises(ValueError):
            trials.training_placements(ids, old)


def test_evaluation_requires_four_distinct_new_positions_and_integer_distinct_seeds():
    trials = module("trials")
    placements = [
        {
            "id": f"e{i:02d}",
            "seed": 70 + i,
            "reset_fixture_center_m": [0.43 + 0.001 * i, 0.003, 0.035],
            "yaw_rad": 0.05,
        }
        for i in range(1, 5)
    ]
    assert trials.checked_placements(placements, "evaluation") == placements
    for field, value in (
        ("id", "../capture"),
        ("seed", True),
        ("seed", 71),
        ("yaw_rad", float("nan")),
        ("reset_fixture_center_m", placements[0]["reset_fixture_center_m"]),
    ):
        invalid = [dict(row) for row in placements]
        invalid[1][field] = value
        with pytest.raises(ValueError):
            trials.checked_placements(invalid, "evaluation")
    with pytest.raises(ValueError):
        trials.checked_placements(placements[:1], "evaluation")


def test_all_eight_admissions_contact_and_independent_physical_witnesses_required():
    trials = module("trials")
    row = {
        "evidence_status": "SCORED",
        "dispatched": 8,
        "verified_posts": 8,
        "online_success": True,
        "physical_success": True,
        "joint_success": True,
        "both_windows_qualified": True,
        "independent_physical_outcome": {
            "success": True,
            "safety_assessment": "SCOPED_NO_VIOLATION",
            "measured_lift_m": 0.06,
            "hold_s": 0.51,
            "placed_stable_s": 1.01,
        },
        "registered_windows": {key: {"qualified": True} for key in ("lift", "release")},
        "contacts": {"bilateral_cube_steps": 2},
        "hand_contacts": {"board_or_support_hand_or_finger_steps": []},
    }
    assert trials.training_success(row)
    for replacement in (
        {"dispatched": 7},
        {"physical_success": False},
        {"contacts": {"bilateral_cube_steps": 0}},
        {"registered_windows": {"lift": {"qualified": True}}},
        {"hand_contacts": {"board_or_support_hand_or_finger_steps": [845]}},
    ):
        assert not trials.training_success({**row, **replacement})


def test_development_attempt_is_atomic_and_not_reusable(tmp_path):
    trials = module("trials")
    file = tmp_path / "attempt.json"

    def claim(_):
        try:
            return trials.reserve_attempt(file, {"id": "d02", "scope": "training"})
        except FileExistsError:
            return None

    with ThreadPoolExecutor(max_workers=6) as workers:
        hashes = list(workers.map(claim, range(6)))
    assert hashes.count(None) == 5
    assert hashlib.sha256(file.read_bytes()).hexdigest() in hashes
    assert json.loads(file.read_text())["scope"] == "training"


def test_measurement_log_is_per_frame_and_keeps_invocations_without_feeding_previous_pose():
    runtime = module("runtime")
    observation = {
        "frame_id": "abc",
        "checksum": "12",
        "usable": False,
        "reason": "no_grid",
        "selected_id": None,
    }
    with runtime.log_measurements() as records:
        runtime.record_measurement(observation, "derive")
        runtime.record_measurement({**observation}, "matches_current_owner")
    assert list(records) == ["abc"]
    assert records["abc"]["measurement"] == observation
    assert records["abc"]["callers"] == {"derive": 1, "matches_current_owner": 1}
    runtime.record_measurement(dict(frame_id="outside"), "offline")
    assert len(records) == 1


def test_capture_receipt_names_the_actual_shared_egl_lock():
    build = module("runtime")
    parent = Path("experiments/results/g1-formal-paired-20261124/runtime-source")
    if not parent.exists():
        pytest.skip("private registered runtime unavailable")
    code = build.adapted_sources(parent, (build.DETECTOR,))
    assert b'egl_lock=str(raw.parent.parent / "egl.lock")' in code[build.CAPTURE]


def test_matching_live_and_independent_tcp_compares_at_frozen_transform_precision():
    trials = module("trials")
    live = {
        "checksum": "a",
        "usable": True,
        "observed_ids": [7],
        "usable_ids": [7],
        "selected_id": 7,
        "reason": "observed",
        "grasp_world_m": [0.4, 0.2, 0.05],
    }
    blind = {k: live[k] for k in ("usable", "observed_ids", "usable_ids", "selected_id", "reason")}
    blind.update(checksum_sha256="a", tcp_m=[0.4 + 1e-14, 0.2, 0.05])
    assert trials.matches_online(blind, live)
    assert not trials.matches_online({**blind, "selected_id": 8}, live)
    assert not trials.matches_online({**blind, "tcp_m": [0.401, 0.2, 0.05]}, live)


def test_full_occlusion_probe_uses_the_live_controller_hold_without_physics_steps():
    source = Path("scripts/graduation/g1_visibility_trials.py").read_text()
    assert ".monitor_hold(" in source and '"hold_current_joints"' in source


def test_zero_step_mask_preserves_acquisition_clocks_depth_and_reference_identity():
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    file = Path(
        "experiments/results/g1-formal-paired-20261124/trials/f01-dual/instance/frames/0001.json"
    )
    if not file.is_file():
        pytest.skip("private historical packet unavailable")
    frame = RGBDObservation.model_validate_json(file.read_bytes())
    changed = module("trials").obscured_packet(frame)
    for key in (
        "captured_at",
        "sim_time_s",
        "depth_float32_base64",
        "valid_mask_base64",
        "intrinsics",
        "camera_to_world",
        "episode_id",
        "scene_id",
    ):
        assert getattr(changed, key) == getattr(frame, key)
    assert changed.rgb_png_base64 != frame.rgb_png_base64
    assert changed.checksum_sha256 != frame.checksum_sha256
    assert changed.frame_id != frame.frame_id


def test_zero_step_registration_is_the_same_qualified_pose_for_both_conditions():
    trials = module("trials")
    result = trials.qualified_preflight_pose(Path.cwd())
    assert result["pose"] == "preregistered-0" and result["kind"] == "both"
    assert result["pose_xyzyaw"] == [0.45, 0, 0.035, 0] and result["seed"] == 24113040
    assert result["path_success"] is True and result["usable_ids"] == [7, 8]


@pytest.mark.parametrize("kind", ["positive", "full-occlusion"])
def test_diagnostic_owner_identifiers_are_distinct_from_permitted_shared_scene(kind):
    from cloud_edge_robot_arm.vision.worker_owner import _identity_string

    trials = module("trials")
    scene = "g1-visibility-pose-repair-20261124/zero-step-seal-qualification"
    case = trials.diagnostic_case(scene, kind, 24113040)
    assert case["scene_id"] == scene and case["visual_id"] == scene + "/" + kind
    assert case["run_id"] == case["visual_id"].replace("/", ":")
    for value in [case[k] for k in ("run_id", "plan_id", "task_id")] + [
        case["release"] + "-worker"
    ]:
        assert _identity_string(value) == value
    with pytest.raises(ValueError):
        _identity_string(scene + "-worker")
    with pytest.raises(ValueError):
        _identity_string(scene + "/" + kind + ":plan")


def test_live_hold_uses_the_sensed_tcp_and_native_lift_skill_separately_from_move_above():
    import inspect

    trials = module("trials")
    source = inspect.getsource(trials.occlusion_control)
    assert 'skill="LIFT"' in source
    assert "state.tcp_pose, _DOWNWARD" in source
    assert 'skill="MOVE_ABOVE"' in source
    assert "sample-evidence.json" in source


def archived_native_feedback(directory):
    """Software-only fixture clock follows each unchanged recorded acquisition."""
    from datetime import UTC, datetime, timedelta
    from unittest.mock import patch

    from scripts.graduation import dynamic_vision as native
    from scripts.graduation import g1_dual_asset as asset
    from scripts.graduation import g1_dual_probe as probe
    from scripts.graduation.g1_formal_runtime import bind_scene
    from scripts.graduation.g1_visibility_trials import obscured_packet

    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD
    from cloud_edge_robot_arm.vision import servo, tracking
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    def load(tag):
        return RGBDObservation.model_validate_json((directory / (tag + ".rgbd.json")).read_bytes())

    bootstrap, initial, reference, current = [
        load(tag) for tag in ("bootstrap", "initial-target", "servo-reference", "current")
    ]
    audit = json.loads((directory / "trace.json").read_text())["initial_registered_target"]
    assert audit["observation_id"] == initial.frame_id
    assert audit["checksum_sha256"] == initial.checksum_sha256
    target = native.Pose.model_validate(audit["grounded_step"]["parameters"]["target_pose"])
    fixed = native.Pose(x=0.4, y=0, z=0.38)
    geometry = asset.geometry_descriptor()
    with (
        bind_scene(bootstrap.scene_id),
        patch.object(tracking, "datetime", wraps=datetime) as tracker_clock,
        patch.object(servo, "datetime", wraps=datetime) as servo_clock,
    ):
        tracker_clock.now.return_value = bootstrap.captured_at + timedelta(milliseconds=1)
        color, grounding = native.bootstrap_collection_tracker(bootstrap, geometry)

        def provider(skill, position):
            servo_clock.now.return_value = reference.captured_at + timedelta(milliseconds=1)
            feedback = native.OpenCVServoFeedback(
                reference,
                color,
                grounding,
                skill=skill,
                initial_target=position,
                marker_family_id=asset.FAMILY,
                verify_mujoco_calibration=True,
            )
            servo_clock.now.return_value = current.captured_at + timedelta(milliseconds=1)
            return feedback

        moving = provider("MOVE_ABOVE", target)
        moved = moving.update(current)
        distance = sum((getattr(target, a) - getattr(moved, a)) ** 2 for a in "xyz") ** 0.5
        assert distance == pytest.approx(0.0005096532235293567, abs=1e-12)
        assert native.MotionTarget(moved, _DOWNWARD) != native.MotionTarget(target, _DOWNWARD)
        previous = native.MotionTarget(fixed, _DOWNWARD)
        lift = provider("LIFT", fixed)
        assert native.MotionTarget(lift.update(current), _DOWNWARD) == previous
        assert lift.records[0]["observation_id"] == current.frame_id
        assert lift.records[0]["checksum_sha256"] == current.checksum_sha256
        covered = provider("LIFT", fixed)
        with pytest.raises(ValueError, match="^servo registered marker geometry unavailable$"):
            covered.update(obscured_packet(current))
        assert covered.records == []
        stale = provider("LIFT", fixed)
        servo_clock.now.return_value = datetime.now(UTC)
        with pytest.raises(ValueError, match="^servo frame not fresh$"):
            stale.update(current)
        foreign = provider("LIFT", fixed)
        with pytest.raises(ValueError, match="^servo observation scene_id changed$"):
            foreign.update(probe.change_packet(current, "wrong-scene", scene_id="foreign-fixture"))
        assert stale.records == foreign.records == []


def test_frozen_native_feedback_replays_four_original_packets_at_software_clock():
    import os
    import subprocess
    import sys

    generation = "f00a35621f30fc4d1ea43a5e7c8cee8f1808145c093de4439188ad1046c7b397"
    build = Path("experiments/results/g1-visibility-pose-repair-20261124/builds") / generation
    directory = (build / "zero-step-rslm979s/positive").resolve()
    if not directory.is_dir():
        pytest.skip("retained four-packet software fixture unavailable")
    tree = (build / "runtime-source").resolve()
    subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "import runpy,sys;from pathlib import Path;"
            "runpy.run_path(sys.argv[1])['archived_native_feedback'](Path(sys.argv[2]))",
            str(Path(__file__).resolve()),
            str(directory),
        ],
        cwd=tree,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(map(str, (tree, tree / "src")))},
        check=True,
    )
