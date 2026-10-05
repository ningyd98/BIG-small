"""Temporal effects require independently observed object geometry, never TCP alone."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import cv2
import numpy as np
import pytest

from cloud_edge_robot_arm.contracts import Pose, RobotState
from tests.test_opencv_target_evidence import image_variant, scene, tracker


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


def test_precision_endpoints_prove_lift_but_not_unobserved_interval_stability():
    initial = scene(resolution=10, source="mujoco_camera")
    tracked = tracker(initial, depth_error_bound_m=0.000001)
    for index in range(7):
        facts = tracked.facts(
            scene(
                f"lift-{index}",
                time=0.1 + index * 0.1,
                lift=0.06,
                started=datetime.now(UTC) - timedelta(seconds=0.1 + index * 0.1),
                resolution=10,
                source="mujoco_camera",
            ),
            held(),
        )
        if index < 5:
            assert facts["object_stable"]["value"] is None
    assert facts["object_lifted"]["value"] is True
    assert facts["object_stable"]["value"] is None
    measured = facts["object_stable"]["measured_values"]
    assert measured["observed_sim_duration_s"] >= 0.5
    assert measured["minimum_visual_lift_m"] >= 0.05
    assert len(measured["samples"]) >= 6
    assert measured["endpoint_window_consistent"] is True
    assert "inter_frame_motion_not_bounded" in facts["object_stable"]["reasons"]
    assert "quarter_turn_symmetry_unresolved" in facts["object_stable"]["reasons"]


@pytest.mark.parametrize("lift", [0.049, 0.05])
def test_error_bounds_cannot_round_subthreshold_lift_up(lift):
    initial = scene()
    facts = tracker(initial).facts(
        scene("next", time=0.1, lift=lift, started=initial.captured_at), held()
    )
    assert facts["object_lifted"]["value"] is None


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


def test_release_geometry_and_endpoint_duration_do_not_prove_physical_stability():
    initial = scene(resolution=10, source="mujoco_camera")
    tracked = tracker(initial, depth_error_bound_m=0.000001)
    for index, x in enumerate((20, 30, 40, 48), 1):
        tracked.facts(
            scene(
                str(index),
                time=index * 0.1,
                x=x,
                started=datetime.now(UTC) - timedelta(seconds=index * 0.1),
                resolution=10,
                source="mujoco_camera",
            ),
            held(),
        )
    released = RobotState(connected=True, gripper_open=True, holding_object_id=None)
    for index in range(12):
        facts = tracked.facts(
            scene(
                f"placed-{index}",
                time=0.5 + index * 0.1,
                x=48,
                started=datetime.now(UTC) - timedelta(seconds=0.5 + index * 0.1),
                resolution=10,
                source="mujoco_camera",
            ),
            released,
        )
        if index < 10:
            assert facts["object_placed"]["value"] is None
    assert facts["object_inside_target_region"]["value"] is True
    assert facts["placement_stable"]["value"] is None
    assert facts["object_placed"]["value"] is None
    assert facts["object_placed"]["measured_values"]["endpoint_window_consistent"] is True


def test_release_feedback_alone_cannot_prove_stability():
    initial = scene()
    released = RobotState(connected=True, gripper_open=True, holding_object_id=None)
    facts = tracker(initial).facts(
        scene("next", time=0.1, damage="missing", started=initial.captured_at), released
    )
    assert facts["object_placed"]["value"] is None


def test_unpaced_simulator_hold_uses_physics_duration_with_real_capture_provenance():
    initial = scene(resolution=10, source="mujoco_camera")
    tracked = tracker(initial, depth_error_bound_m=0.000001)
    for index in range(7):
        current = scene(
            f"sim-{index}",
            time=0.1 + index * 0.1,
            lift=0.06,
            started=initial.captured_at,
            resolution=10,
            source="mujoco_camera",
        )
        payload = current.model_dump()
        payload.update(
            captured_at=initial.captured_at + timedelta(seconds=0.001 * (index + 1)),
            checksum_sha256="",
        )
        current = type(current).model_validate(payload)
        facts = tracked.facts(current, held())
    assert facts["object_stable"]["value"] is None
    assert facts["object_stable"]["measured_values"]["observed_sim_duration_s"] >= 0.5
    assert facts["object_stable"]["measured_values"]["observed_capture_duration_s"] < 0.01


@pytest.mark.parametrize("phase", ["lift", "placement"])
def test_visible_fast_oscillation_cannot_accumulate_stability(phase):
    initial = scene()
    tracked = tracker(initial)
    x = 10
    if phase == "placement":
        for index, x in enumerate((20, 30, 40, 48), 1):
            tracked.facts(
                scene(str(index), time=index * 0.1, x=x, started=initial.captured_at), held()
            )
    for index in range(14):
        facts = tracked.facts(
            scene(
                f"oscillate-{index}",
                time=0.5 + index * 0.1,
                x=x + index % 2,
                lift=0.06 if phase == "lift" else 0,
                started=initial.captured_at,
            ),
            held() if phase == "lift" else RobotState(connected=True, gripper_open=True),
        )
    condition = "object_stable" if phase == "lift" else "object_placed"
    assert facts[condition]["value"] is not True


def test_coarse_center_uncertainty_cannot_prove_slow_stability():
    initial = scene()
    tracked = tracker(initial)
    for index in range(7):
        facts = tracked.facts(
            scene(str(index), time=0.1 + index * 0.1, lift=0.06, started=initial.captured_at),
            held(),
        )
    assert facts["object_stable"]["value"] is None


def test_observed_orientation_oscillation_cannot_prove_angular_stability():
    initial = scene(resolution=10, source="mujoco_camera")
    tracked = tracker(initial, depth_error_bound_m=0.000001)
    for index in range(8):
        time = 0.1 + index * 0.1
        current = scene(
            str(index),
            time=time,
            lift=0.06,
            resolution=10,
            source="mujoco_camera",
            started=datetime.now(UTC) - timedelta(seconds=time),
        )

        def rotate_top(rgb, depth, angle=(index % 2) * 5.0):
            mask = (rgb[:, :, 0] > 200).astype(np.uint8)
            transform = cv2.getRotationMatrix2D((129.5, 269.5), angle, 1.0)
            rotated = (
                cv2.warpAffine(
                    mask, transform, (rgb.shape[1], rgb.shape[0]), flags=cv2.INTER_NEAREST
                )
                > 0
            )
            rgb[mask > 0] = 100
            depth[mask > 0] = 1.0
            rgb[rotated] = [230, 20, 20]
            depth[rotated] = 0.88

        facts = tracked.facts(image_variant(current, rotate_top), held())
        assert facts["target_visible"]["value"] is True
    assert facts["object_stable"]["value"] is None


@pytest.mark.parametrize("unsupported_motion", ["out_and_back", "quarter_turn"])
def test_identical_precision_frames_do_not_resolve_unobserved_motion(unsupported_motion):
    # Both possible motions have these exact observed endpoints. We do not give
    # the estimator hidden trajectories or fabricate a ground-truth fixture.
    initial = scene(resolution=10, source="mujoco_camera")
    tracked = tracker(
        initial, depth_error_bound_m=0.000001, stability_verified=True, max_object_speed_m_s=0.0
    )
    for index in range(7):
        time = 0.1 + index * 0.1
        facts = tracked.facts(
            scene(
                f"{unsupported_motion}-{index}",
                time=time,
                lift=0.06,
                resolution=10,
                source="mujoco_camera",
                started=datetime.now(UTC) - timedelta(seconds=time),
            ),
            held(),
        )
    stable = facts["object_stable"]
    assert stable["value"] is None
    assert stable["measured_values"]["endpoint_window_consistent"] is True
    assert stable["measured_values"]["physical_stability_support"]["status"] == "UNAVAILABLE"
    assert "inter_frame_motion_not_bounded" in stable["reasons"]
    assert "quarter_turn_symmetry_unresolved" in stable["reasons"]


def test_precision_translation_oscillation_rejects_endpoint_consistency():
    initial = scene(resolution=10, source="mujoco_camera")
    tracked = tracker(initial, depth_error_bound_m=0.000001)
    for index in range(7):
        time = 0.1 + index * 0.1
        facts = tracked.facts(
            scene(
                str(index),
                time=time,
                x=10 + index % 2,
                lift=0.06,
                resolution=10,
                source="mujoco_camera",
                started=datetime.now(UTC) - timedelta(seconds=time),
            ),
            held(),
        )
        assert facts["target_visible"]["value"] is True
    diagnostic = facts["object_stable"]["measured_values"]
    assert facts["object_stable"]["value"] is None
    assert diagnostic["endpoint_window_consistent"] is False
    assert diagnostic["samples"][-1]["net_endpoint_displacement_rate_upper_m_s"] > 0.08
