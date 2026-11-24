"""A stationary source restore can issue one nominal camera record per scheduled pose."""

from copy import deepcopy

import pytest
from scripts.graduation import g1_refusal_capture as capture


def observations():
    rows, records = [], []
    for i in range(16):
        base = dict(
            camera=dict(
                position_m=[0.35, 0, 1.4],
                quaternion_wxyz=[1, 0, 0, 0],
                fovy_deg=50,
                world_body_id=0,
                mode=0,
            ),
            episode_id=None,
            physics_step=0,
        )
        before = dict(base, record_count=i, next_seq=i + 1, sim_time_s=i / 4)
        after = dict(base, record_count=i + 1, next_seq=i + 2, sim_time_s=(i + 1) / 4)
        rows.append(
            dict(
                before=before,
                after_normal=after,
                after_hidden=deepcopy(after),
                expected_source_time_s=(i + 1) / 4,
            )
        )
        records.append(
            dict(
                type="camera_position",
                accepted=True,
                reason="development_camera_translation",
                position_m=[0.35, 0, 1.4],
                after_emergency_stop=False,
                command_seq=i + 1,
                sim_time_s=i / 4,
                episode_id=None,
                physics_step=0,
            )
        )
    return rows, records


def check(rows, records):
    assert hasattr(capture, "audit_camera_commands"), "strict camera-vs-motion verification absent"
    return capture.audit_camera_commands(rows, records)


def test_one_nominal_camera_per_restore_and_zero_commands_for_hidden():
    rows, records = observations()
    assert check(rows, records) == dict(
        camera_records=16, integrated_steps=0, motion_dispatches=0, hidden_commands=0
    )
    for invalid in ([], records[:-1], records + [records[-1]]):
        with pytest.raises(ValueError):
            check(rows, invalid)


@pytest.mark.parametrize(
    ("field", "wrong"),
    [
        ("type", "joint_target"),
        ("accepted", 1),
        ("reason", "servo_move"),
        ("command_seq", 1),
        ("sim_time_s", 0),
        ("physics_step", 1),
        ("episode_id", "foreign"),
        ("after_emergency_stop", True),
        ("position_m", [0.35, 0, 1.41]),
        ("look_at_m", [0, 0, 0]),
    ],
)
def test_rejects_extra_or_malformed_actual_command(field, wrong):
    rows, records = observations()
    records[5][field] = wrong
    with pytest.raises(ValueError):
        check(rows, records)


@pytest.mark.parametrize(
    ("phase", "field", "wrong"),
    [
        ("before", "record_count", 1),
        ("after_normal", "physics_step", 1),
        ("after_normal", "next_seq", 1),
        ("after_hidden", "record_count", 7),
        ("after_hidden", "sim_time_s", 0),
        ("after_normal", "episode_id", "foreign"),
        ("before", "camera", {"quaternion_wxyz": [0, 1, 0, 0]}),
    ],
)
def test_camera_identity_and_same_state_hidden_boundary(phase, field, wrong):
    rows, records = observations()
    rows[5][phase][field] = wrong
    with pytest.raises(ValueError):
        check(rows, records)


def test_archived_command_checked_against_actual_pre_restore_clock_and_camera():
    from importlib.util import find_spec

    assert find_spec("scripts.graduation.g1_refusal_camera_readback"), (
        "missing independent archived camera reader"
    )
    from scripts.graduation.g1_refusal_camera_readback import check_record

    rows, records = observations()
    row = rows[1]
    check_record(records[1], row, 2, rows[0]["after_hidden"])
    for key, wrong in [
        ("episode_id", "renderer-token"),
        ("sim_time_s", row["after_normal"]["sim_time_s"]),
        ("physics_step", 2),
        ("accepted", 1),
    ]:
        with pytest.raises(ValueError):
            check_record({**records[1], key: wrong}, row, 2, rows[0]["after_hidden"])
