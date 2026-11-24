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
