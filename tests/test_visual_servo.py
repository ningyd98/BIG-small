"""Visual feedback must use current RGBD and its matching camera pose."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from tests.test_opencv_target_evidence import scene, tracker


def acquisition():
    reference = scene(started=datetime.now(UTC) - timedelta(seconds=0.04), source="mujoco_camera")
    tracked = tracker(reference)
    initial = Pose(**dict(zip("xyz", tracked.initial["center"], strict=True)))
    evidence = {
        "resolved_top_grasp_tcp": {**initial.model_dump(), "z": 0.04},
        "grounded_destination": dict(zip("xyz", tracked.destination["center"], strict=True)),
        "top_grasp_support_height_m": 0.0,
    }
    return reference, tracked, evidence, Pose(**evidence["resolved_top_grasp_tcp"])


def current(reference, **kwargs):
    return scene(
        "current", time=1 / 30, started=reference.captured_at,
        source=reference.source, **kwargs,
    )


def revised(observation, **changes):
    return RGBDObservation.model_validate(
        observation.model_dump() | changes | {"checksum_sha256": ""}
    )


def feedback(**kwargs):
    from cloud_edge_robot_arm.vision.servo import OpenCVServoFeedback

    reference, tracked, evidence, initial = acquisition()
    return (
        OpenCVServoFeedback(
            reference, tracked, evidence, skill="APPROACH", initial_target=initial, **kwargs
        ), reference, initial,
    )


def test_current_target_moves_during_same_skill():
    provider, reference, initial = feedback()
    target = provider.update(current(reference, x=11))
    assert target.x - initial.x == pytest.approx(0.0094, abs=1e-6)
    assert target.y == initial.y
    assert target.z == pytest.approx(initial.z, abs=1e-12)
    assert provider.records[-1]["ground_truth_used_for_control"] is False


def test_camera_translation_does_not_become_object_motion():
    provider, reference, initial = feedback()
    moved = current(reference, x=9, calibration_version="translated-camera")
    transform = np.array(moved.camera_to_world).reshape(4, 4)
    transform[0, 3] += 0.0094
    moved = revised(moved, camera_to_world=tuple(transform.ravel()))
    target = provider.update(moved)
    assert target.x == pytest.approx(initial.x, abs=1e-6)
    assert target.y == initial.y
    assert provider.records[-1]["camera_position_m"] == pytest.approx([0.0094, 0, 1])


@pytest.mark.parametrize("damage", ["missing", "decoy", "depth", "edge_occluder"])
def test_bad_current_geometry_never_reuses_previous_target(damage):
    provider, reference, _ = feedback()
    with pytest.raises(ValueError, match="geometry"):
        provider.update(current(reference, damage=damage))
    assert provider.records == []


@pytest.mark.parametrize("fault", ["stale", "future", "episode", "gap", "jump", "old_calibration"])
def test_invalid_frame_or_discontinuity_is_rejected(fault):
    provider, reference, _ = feedback()
    observation = current(reference)
    if fault == "stale":
        observation = revised(observation, captured_at=datetime.now(UTC) - timedelta(seconds=1))
    elif fault == "future":
        observation = revised(observation, captured_at=datetime.now(UTC) + timedelta(seconds=1))
    elif fault == "episode":
        observation = revised(observation, episode_id="another-episode")
    elif fault == "gap":
        observation = revised(observation, sim_time_s=0.2)
    elif fault == "jump":
        observation = current(reference, x=14)
    else:
        matrix = list(observation.camera_to_world)
        matrix[3] += 0.01
        observation = revised(observation, camera_to_world=tuple(matrix))
    with pytest.raises(ValueError):
        provider.update(observation)


def test_repeated_frame_and_old_fixed_camera_binding_remain_rejected():
    provider, reference, _ = feedback()
    observation = current(reference)
    provider.update(observation)
    with pytest.raises(ValueError, match="repeated"):
        provider.update(observation)
    tracked = tracker(reference)
    matrix = list(observation.camera_to_world)
    matrix[3] += 0.01
    moved = revised(observation, camera_to_world=tuple(matrix), calibration_version="moved")
    assert tracked._binding_reason(moved) is not None


def test_reference_frame_is_not_a_new_servo_sample():
    provider, reference, _ = feedback()
    with pytest.raises(ValueError, match="repeated"):
        provider.update(reference)


def test_future_frame_within_legacy_tolerance_is_rejected():
    provider, reference, _ = feedback()
    future = revised(current(reference), captured_at=datetime.now(UTC) + timedelta(seconds=0.04))
    with pytest.raises(ValueError, match="fresh"):
        provider.update(future)


def test_camera_position_changes_calibration_without_advancing_physics():
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

    backend = MuJoCoPhysicsBackend()
    try:
        backend.initialize(SimulatorConfig(render_rgb=True, render_depth=True))
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
        before = backend.get_sensor_frame()
        backend.set_camera_position((0.36, 0.01, 1.35))
        after = backend.capture_sensor_frame()
        assert backend.total_physics_steps == 0
        assert after.calibration_version != before.calibration_version
        transform = np.array(after.camera_to_world).reshape(4, 4)
        assert transform[:3, 3] == pytest.approx([0.36, 0.01, 1.35])
        assert transform[:3, 2] == pytest.approx([0, 0, -1])
    finally:
        backend.shutdown()


def test_explicit_on_demand_scope_preserves_fresh_owned_frames_without_redundant_renders():
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

    backend = MuJoCoPhysicsBackend()
    try:
        backend.initialize(SimulatorConfig(render_rgb=True, render_depth=True))
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
        before = backend.get_sensor_frame()
        with backend.sensor_capture_on_demand():
            backend.step(5)
            assert backend.get_sensor_frame() is before
            owned = backend.capture_sensor_frame()
            assert owned.sim_time_s == backend.get_sim_time()
            assert owned.frame_id != before.frame_id
        assert backend.get_sensor_frame().sim_time_s == backend.get_sim_time()
        backend.step(5)
        assert backend.get_sensor_frame().frame_id != owned.frame_id
    finally:
        backend.shutdown()
