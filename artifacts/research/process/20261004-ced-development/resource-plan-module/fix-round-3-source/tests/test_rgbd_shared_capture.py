"""Borrowed capture preserves the owner's live episode and resource lifecycle."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cloud_edge_robot_arm.datasets.rgbd.models import DatasetConfig
from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import JointCommand, PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession


def test_action_and_recapture_share_backend_episode() -> None:
    config = SimulatorConfig(render_rgb=True, render_depth=True)
    backend = MuJoCoPhysicsBackend()
    try:
        backend.initialize(config)
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=17))
        backend.step(steps=5)
        owner_frame = backend.get_sensor_frame()
        with patch.object(backend, "reset", wraps=backend.reset) as reset:
            with MuJoCoCaptureSession(config, backend=backend) as session:
                first = session.capture_with_instances()
                positions = list(backend.get_joint_state().positions)
                positions[0] += 0.1
                backend.apply_joint_targets(JointCommand(positions=positions))
                backend.step(steps=24)
                second = session.capture_with_instances()
                assert first.observation.episode_id == owner_frame.episode_id
                assert second.observation.episode_id == first.observation.episode_id
                assert first.observation.frame_id != second.observation.frame_id
                assert first.observation.sim_time_s == owner_frame.sim_time_s
                assert second.observation.sim_time_s > first.observation.sim_time_s
                assert first.physics_state_hash != second.physics_state_hash
                assert backend.total_physics_steps == 29
                assert reset.call_count == 0
    finally:
        backend.shutdown()


@pytest.mark.parametrize("raises_in_body", [False, True])
def test_borrowed_backend_is_not_shutdown_by_capture(raises_in_body: bool) -> None:
    config = SimulatorConfig(render_rgb=True, render_depth=True)
    backend = MuJoCoPhysicsBackend()
    with (
        patch.object(backend, "initialize", wraps=backend.initialize) as initialize,
        patch.object(backend, "reset", wraps=backend.reset) as reset,
        patch.object(backend, "shutdown", wraps=backend.shutdown) as shutdown,
    ):
        try:
            backend.initialize(config)
            backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=19))
            episode_id = backend.get_sensor_frame().episode_id
            session = MuJoCoCaptureSession(config, backend=backend)
            try:
                with session:
                    assert session.capture().episode_id == episode_id
                    if raises_in_body:
                        raise RuntimeError("episode operation failed")
            except RuntimeError as exc:
                assert raises_in_body and str(exc) == "episode operation failed"
            assert initialize.call_count == reset.call_count == 1
            assert shutdown.call_count == 0
            with pytest.raises(RuntimeError, match="session is closed"):
                session.capture()
            # Exiting a borrowed capture must leave both physics and its renderer usable.
            backend.step(steps=1)
            frame, *_ = backend.capture_sensor_frame_with_instances()
            assert frame.episode_id == episode_id
        finally:
            backend.shutdown()
        assert shutdown.call_count == 1
        with pytest.raises(RuntimeError, match="not initialized"):
            backend.step()


def test_borrowed_capture_error_keeps_owner_backend_alive() -> None:
    config = SimulatorConfig(render_rgb=False, render_depth=False)
    backend = MuJoCoPhysicsBackend()
    try:
        backend.initialize(config)
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=23))
        with pytest.raises(RuntimeError, match="RGB-D rendering is not enabled"):
            with MuJoCoCaptureSession(config, backend=backend) as session:
                session.capture()
        # Borrowing must not silently turn on rendering, reset, or close the backend.
        backend.step(steps=2)
        assert backend.total_physics_steps == 2
        assert backend.get_sensor_frame().width == 0
    finally:
        backend.shutdown()


def test_borrowed_session_cannot_replace_owner_scene() -> None:
    config = SimulatorConfig(render_rgb=True, render_depth=True)
    scene = sample_scene(DatasetConfig(dataset_id="borrowed-scene-test"), seed=29)
    backend = MuJoCoPhysicsBackend()
    try:
        backend.initialize(config)
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=29))
        backend.step(steps=3)
        with MuJoCoCaptureSession(config, backend=backend) as session:
            before = session.capture_with_instances()
            with pytest.raises(RuntimeError, match="borrowed"):
                session.apply_scene(scene)
            after = session.capture_with_instances()
            assert after.observation.episode_id == before.observation.episode_id
            assert after.physics_state_hash == before.physics_state_hash
            assert backend.total_physics_steps == 3
    finally:
        backend.shutdown()


def test_moved_target_requires_new_frame() -> None:
    config = SimulatorConfig(render_rgb=True, render_depth=True)
    backend = MuJoCoPhysicsBackend()
    try:
        backend.initialize(config)
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
        with MuJoCoCaptureSession(config, backend=backend) as session:
            before = session.capture()
            backend.step(steps=24)
            stale_crop = before.crop((40, 30, 280, 210))
            after = session.capture()
            assert stale_crop.observation_id == before.observation_id
            assert stale_crop.captured_at == before.captured_at
            assert stale_crop.sim_time_s == before.sim_time_s
            assert after.observation_id != stale_crop.observation_id
            assert after.episode_id == stale_crop.episode_id
            assert after.sim_time_s > stale_crop.sim_time_s
    finally:
        backend.shutdown()
