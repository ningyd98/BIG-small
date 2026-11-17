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


@pytest.mark.parametrize("failure", [
    "servo registered marker geometry unavailable",
    "servo region geometry unavailable: region_color_boundary_depth_unresolved",
    "servo registered object is not upright",
    "servo region geometry unavailable: region_occluder_depth_invalid",
])
@pytest.mark.parametrize("current_view", [None, 0, 1, 3])
def test_camera_recovery_is_bounded_and_only_for_observability_failures(
    monkeypatch, failure, current_view,
):
    recoverable = failure.endswith(("geometry unavailable", "color_boundary_depth_unresolved"))
    provider, reference, initial = feedback()
    observations = [revised(current(reference), frame_id=f"view-{i}", observation_id=f"view-{i}")
                    for i in range(3)]
    measured, changes, captured = [], [], []

    def update(observation):
        measured.append(observation.observation_id)
        if len(measured) < 3:
            raise ValueError(failure)
        return initial

    monkeypatch.setattr(provider, "update", update)
    views = [((0.1 * i, 0.2, 0.6), (0.2, 0.2, 0.1)) for i in (1, 2, 3, 4)]
    if current_view is not None:
        transform = np.array(observations[0].camera_to_world).reshape(4, 4)
        transform[:3, 3] = views[current_view][0]
        observations[0] = revised(observations[0], camera_to_world=tuple(transform.ravel()),
                                  calibration_version="current-side-view")

    def capture(attempt):
        captured.append(attempt)
        return observations[attempt]

    def set_view(position, aim, reason):
        changes.append((position, aim, reason))

    if recoverable:
        result = provider.update_with_camera_views(capture, set_view, views)
        assert result == initial and captured == [0, 1, 2] and len(changes) == 2
        preferred = 1 if current_view == 0 else 0
        assert changes[0][0] == views[preferred][0]
        if current_view is not None:
            assert all(change[0] != views[current_view][0] for change in changes)
        assert changes[0][0] != changes[1][0]
    else:
        with pytest.raises(ValueError, match=failure):
            provider.update_with_camera_views(capture, set_view, views)
        assert captured == [0] and changes == []


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


def test_camera_can_look_at_workspace_from_an_oblique_position():
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

    backend = MuJoCoPhysicsBackend()
    try:
        backend.initialize(SimulatorConfig(render_rgb=True, render_depth=True))
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
        before = backend.get_sensor_frame()
        position, aim = (-0.05, 0.4, 0.7), (0.3, 0.15, 0.05)
        backend.set_camera_position(position, look_at_m=aim)
        after = backend.capture_sensor_frame()
        transform = np.array(after.camera_to_world).reshape(4, 4)
        direction = np.array(aim) - position
        direction /= np.linalg.norm(direction)
        assert transform[:3, 2] == pytest.approx(direction)
        assert after.calibration_version != before.calibration_version
        assert backend.total_physics_steps == 0
        assert backend.command_records[-1]["look_at_m"] == list(aim)
        with pytest.raises(ValueError, match="look-at"):
            backend.set_camera_position(position, look_at_m=position)
        unchanged = backend.capture_sensor_frame()
        assert unchanged.calibration_version == after.calibration_version
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
