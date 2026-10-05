"""Temporal effects require independently observed object geometry, never TCP alone."""

from __future__ import annotations

from datetime import timedelta

import pytest

from cloud_edge_robot_arm.contracts import Pose, RobotState
from tests.test_opencv_target_evidence import scene, tracker


def held(z=0.1):
    return RobotState(
        connected=True, gripper_open=False, holding_object_id="object", tcp_pose=Pose(x=0, y=0, z=z)
    )


def test_tcp_lift_without_object_lift_cannot_prove_effect():
    initial = scene()
    tracked = tracker(initial)
    facts = tracked.facts(scene("next", time=0.1, started=initial.captured_at), held(0.3))
    assert facts["object_lifted"]["value"] is False
    assert facts["object_stable"]["value"] is None


def test_metric_lift_and_fresh_half_second_hold_prove_effect():
    initial = scene()
    tracked = tracker(initial)
    for index in range(7):
        facts = tracked.facts(
            scene(f"lift-{index}", time=0.1 + index * 0.1, lift=0.06, started=initial.captured_at),
            held(),
        )
        if index < 5:
            assert facts["object_stable"]["value"] is None
    assert facts["object_lifted"]["value"] is True
    assert facts["object_stable"]["value"] is True
    measured = facts["object_stable"]["measured_values"]
    assert measured["observed_sim_duration_s"] >= 0.5
    assert measured["minimum_visual_lift_m"] >= 0.05
    assert len(measured["samples"]) >= 6


@pytest.mark.parametrize("lift", [0.049, 0.05])
def test_error_bounds_cannot_round_subthreshold_lift_up(lift):
    initial = scene()
    facts = tracker(initial).facts(
        scene("next", time=0.1, lift=lift, started=initial.captured_at), held()
    )
    assert facts["object_lifted"]["value"] is not True


def test_occlusion_breaks_continuous_lift_hold():
    initial = scene()
    tracked = tracker(initial)
    for index in range(8):
        facts = tracked.facts(
            scene(
                str(index),
                time=0.1 + index * 0.1,
                lift=0.06,
                damage="occluded" if index == 4 else None,
                started=initial.captured_at,
            ),
            held(),
        )
    assert facts["object_stable"]["value"] is None


def test_duplicate_observation_cannot_accumulate_hold():
    initial = scene()
    tracked = tracker(initial)
    lifted = scene("lifted", time=0.1, lift=0.06, started=initial.captured_at)
    for _ in range(20):
        facts = tracked.facts(lifted, held())
    assert facts["object_stable"]["value"] is None


def test_sparse_endpoints_cannot_prove_continuous_hold():
    initial = scene()
    tracked = tracker(initial)
    tracked.facts(scene("lift-a", time=0.1, lift=0.06, started=initial.captured_at), held())
    facts = tracked.facts(scene("lift-b", time=0.8, lift=0.06, started=initial.captured_at), held())
    assert facts["object_stable"]["value"] is None


def test_release_requires_fresh_full_extent_and_one_second_stability():
    initial = scene()
    tracked = tracker(initial)
    for index, x in enumerate((20, 30, 40, 48), 1):
        tracked.facts(scene(str(index), time=index * 0.1, x=x, started=initial.captured_at), held())
    released = RobotState(connected=True, gripper_open=True, holding_object_id=None)
    for index in range(12):
        facts = tracked.facts(
            scene(f"placed-{index}", time=0.5 + index * 0.1, x=48, started=initial.captured_at),
            released,
        )
        if index < 10:
            assert facts["object_placed"]["value"] is None
    assert facts["object_inside_target_region"]["value"] is True
    assert facts["placement_stable"]["value"] is True
    assert facts["object_placed"]["value"] is True


def test_release_feedback_alone_cannot_prove_stability():
    initial = scene()
    released = RobotState(connected=True, gripper_open=True, holding_object_id=None)
    facts = tracker(initial).facts(
        scene("next", time=0.1, damage="missing", started=initial.captured_at), released
    )
    assert facts["object_placed"]["value"] is None


def test_unpaced_simulator_hold_uses_physics_duration_with_real_capture_provenance():
    initial = scene().model_copy(update={"source": "mujoco_camera"})
    tracked = tracker(initial)
    for index in range(7):
        current = scene(
            f"sim-{index}",
            time=0.1 + index * 0.1,
            lift=0.06,
            started=initial.captured_at,
        ).model_copy(
            update={
                "source": "mujoco_camera",
                "captured_at": initial.captured_at + timedelta(seconds=0.001 * (index + 1)),
            }
        )
        facts = tracked.facts(current, held())
    assert facts["object_stable"]["value"] is True
    assert facts["object_stable"]["measured_values"]["observed_sim_duration_s"] >= 0.5
    assert facts["object_stable"]["measured_values"]["observed_capture_duration_s"] < 0.01
