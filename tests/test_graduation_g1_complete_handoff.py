from types import SimpleNamespace

import numpy as np
from scripts.graduation import g1_complete_cv_handoff as handoff


def entry():
    return dict(
        source_skill="APPROACH",
        destination_skill="GRASP",
        prior_end_step=1392,
        entry_step=1392,
        current_step=1392,
        entry_command_seq=255,
        last_command_seq=255,
        entry_frame_id="frame",
        entry_checksum_sha256="bound",
        entry_joint_positions_rad=[0.1] * 7,
        entry_joint_velocities_rad_s=[0.09] * 7,
        entry_finger_positions_m=[0.039] * 2,
        entry_finger_velocities_m_s=[0.0] * 2,
        entry_target_rad=[0.08] * 7,
        entry_finger_target_m=[0.039] * 2,
        entry_effective_arm_goal_rad=[0.11] * 7,
        entry_native_arm_velocity_rad_s=[0.0] * 7,
        entry_gripper_open=True,
        effective_joint_target_rad=[0.08] * 7,
        effective_finger_target_m=[0.039] * 2,
    )


def test_entry_requires_previous_native_return_same_command_and_same_frame():
    frame = SimpleNamespace(frame_id="frame", checksum_sha256="bound")
    h = entry()
    assert handoff.binding_error(h, "GRASP", "PRE", frame) is None
    for change in (
        {"source_skill": "LIFT"},
        {"prior_end_step": 1391},
        {"entry_frame_id": "stale"},
        {"entry_checksum_sha256": "foreign"},
        {"last_command_seq": 254},
        {"entry_target_rad": [0.09] * 7},
        {"entry_gripper_open": None},
    ):
        assert handoff.binding_error(h | change, "GRASP", "PRE", frame)


def test_motion_domain_requires_one_jointly_matching_reference_and_includes_optical_error():
    obs = np.array([0.0, 0.0])
    unit = np.ones(2)
    assert handoff.nearby_rows(obs, np.zeros(2), [[0.1, 0.1]], unit) == [0]
    assert handoff.nearby_rows(obs, np.zeros(2), [[0.0, 1.1], [1.1, 0.0]], unit) == []
    assert handoff.nearby_rows(obs, [0.3, 0.0], [[0.8, 0.0]], unit) == []


def test_direct_gripper_covers_every_tick_before_and_after_dispatch():
    assert handoff.required_delays("GRASP") == {"pre", *map(str, range(241))}
    assert handoff.required_delays("RELEASE") == handoff.required_delays("GRASP")
    assert handoff.required_delays("LIFT") == set(map(str, range(9)))


def test_only_finger_to_named_cube_contact_is_exempt():
    assert handoff.authorized_pair("GRASP", "left_finger_geom", "object_geom")
    assert not handoff.authorized_pair("GRASP", "hand", "object_geom")
    assert not handoff.authorized_pair("GRASP", "left_finger_geom", "g1_dual_id8_plate")
    assert not handoff.authorized_pair("APPROACH", "left_finger_geom", "object_geom")
