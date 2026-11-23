from dataclasses import asdict, replace

import pytest
from scripts.graduation.dynamic_physics import (
    CRITERIA,
    STAGES,
    read_seal,
    stage_windows,
    validate_series,
    window_report,
)
from scripts.graduation.perception_io import sha, write

from cloud_edge_robot_arm.simulation.mujoco.backend import PhysicsStepObservation
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import sample_physical_observation


def obs(step):
    return PhysicsStepObservation(
        episode_id="ep",
        physics_step=step,
        sim_time_s=step / 240,
        object_position_m=(0.2, 0.25, 0.135),
        object_geom_position_m=(0.2, 0.25, 0.135),
        object_geom_rotation_row_major=(1, 0, 0, 0, 1, 0, 0, 0, 1),
        object_half_extent_m=(0.02, 0.02, 0.02),
        object_bottom_z_m=0.015,
        object_linear_velocity_m_s=(0, 0, 0),
        object_angular_velocity_rad_s=(0, 0, 0),
        region_center_m=(0.2, 0.25, 0.015),
        region_half_extent_m=(0.08, 0.08, 0.001),
        table_top_m=0.015,
        tcp_position_m=(0.2, 0.25, 0.2),
        gripper_open=False,
        finger_positions_m=(0.02, 0.02),
        finger_velocities_m_s=(0, 0),
        finger_ranges_m=((0, 0.04), (0, 0.04)),
        joint_positions_rad=(0,),
        joint_velocities_rad_s=(0,),
        joint_ranges_rad=((-1, 1),),
        contact_pairs=(("left_finger_geom", "object_geom"), ("right_finger_geom", "object_geom")),
        self_collision_distances_m=(),
        estop_engaged=False,
    )


def envelope(step):
    return {"case_id": "case", "asset_sha256": "asset", "snapshot": asdict(obs(step))}


@pytest.mark.parametrize("steps", [[0, 2], [0, 1, 1], [1, 2], [0, 1]])
def test_missing_duplicate_or_shortened_series_is_rejected(steps):
    with pytest.raises(ValueError):
        validate_series([envelope(s) for s in steps], "case", "asset", "ep", 2, 1 / 240)


@pytest.mark.parametrize(
    "field,value",
    [
        ("case_id", "wrong"),
        ("asset_sha256", "other"),
        ("episode_id", "foreign"),
        ("sim_time_s", 0.01),
    ],
)
def test_wrong_identity_asset_or_clock_is_rejected(field, value):
    rows = [envelope(0), envelope(1)]
    target = rows[1]["snapshot"] if field in {"episode_id", "sim_time_s"} else rows[1]
    target[field] = value
    with pytest.raises(ValueError):
        validate_series(rows, "case", "asset", "ep", 1, 1 / 240)


def test_wrong_dwell_window_is_rejected_and_unstarted_suffix_stays_missing():
    names = STAGES[:5]
    spans = []
    step = 0
    for name in names:
        end = step + (120 if name == STAGES[4] else 1)
        spans.append({"stage": name, "start_step": step, "end_step": end, "status": "RETURNED"})
        step = end
    assert stage_windows(spans)["lift"] == (4, 124)
    assert stage_windows(spans)["release"] is None
    spans[-1]["end_step"] -= 1
    with pytest.raises(ValueError, match="dwell"):
        stage_windows(spans)


def test_one_failed_sample_splits_hold_without_removing_denominator():
    samples = [sample_physical_observation(obs(step), CRITERIA) for step in range(121)]
    samples[60] = replace(samples[60], left_finger_contact=False)
    summ, rows = window_report("lift", samples, 0.035, 0.035, True)
    assert (summ["samples"], summ["failed_samples"], summ["first_failed_step"]) == (121, 1, 60)
    assert summ["longest_s"] == pytest.approx(59 / 240)
    assert rows[60]["predicates"]["bilateral_contact"] is False


def test_modified_sealed_byte_is_rejected(tmp_path):
    evidence = tmp_path / "data"
    evidence.write_bytes(b"a\n")
    seal = tmp_path / "seal.json"
    write(seal, {"files": {"data": sha(evidence)}})
    before = sha(seal)
    read_seal(tmp_path, before)
    evidence.write_bytes(b"b\n")
    with pytest.raises(ValueError, match="data"):
        read_seal(tmp_path, before)
