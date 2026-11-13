"""组件诊断保留真实机器人硬停止，未知视觉支持不能升级为可见。"""

import importlib
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from tests.test_visual_worker_owner import running as running


@pytest.mark.parametrize("damage", ["released", "changed_attempt"])
def test_component_poll_rechecks_full_concrete_lease_and_attempt(
    running, damage  # noqa: F811 - pytest imports and injects this concrete SQLite fixture.
):
    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

    module = importlib.import_module("cloud_edge_robot_arm.research.sol_molmo_components")
    repository, job, lease, attempt = running
    worker = SimpleNamespace(
        repository=repository,
        worker_id=lease.worker_id,
        _heartbeat_failed=threading.Event(),
        _frozen_operational_time_mode=None,
    )
    worker._raise_if_cancelled_or_timed_out = lambda *args: (
        SimulationWorker._raise_if_cancelled_or_timed_out(worker, *args)
    )
    start = time.monotonic()
    module.check_component_lease(worker, job, start, expected_attempt=attempt.attempt)
    if damage == "released":
        repository.release_lease(lease.lease_id)
    else:
        repository.finish_open_attempts(job.job_id, result="FAILED", error="software-only")
        repository.start_attempt(job.job_id, worker_id=lease.worker_id)
    with pytest.raises(module.ComponentStopped, match="LEASE_SOURCE"):
        module.check_component_lease(worker, job, start, expected_attempt=attempt.attempt)


@pytest.mark.parametrize(
    "damage,reason", [("position", "HARD_JOINT_LIMIT"), ("velocity", "HARD_JOINT_VELOCITY")]
)
def test_real_joint_feedback_stops_component_before_next_command(damage, reason):
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    module = importlib.import_module("cloud_edge_robot_arm.research.sol_molmo_components")
    backend = MuJoCoPhysicsBackend()
    try:
        backend.initialize(SimulatorConfig())
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=42001))
        robot = MuJoCoSkillRobot(backend)
        module.check_component_hard_state(backend, robot)
        if damage == "position":
            backend._data.qpos[0] = 2.91
        else:
            backend._data.qvel[0] = 3.01
        with pytest.raises(module.ComponentStopped, match=reason):
            module.check_component_hard_state(backend, robot)
        assert backend.total_physics_steps == 0
    finally:
        backend.shutdown()


def test_missing_color_support_cannot_be_replaced_by_proprioception():
    from tests.test_molmo_grounded_planner import request_scene

    module = importlib.import_module("cloud_edge_robot_arm.research.sol_molmo_components")
    observation = request_scene().observation
    _, visible = module._visible_support(observation, np.array([0.8, 0.1, 0.1]))
    assert visible["visible_pixels"] >= 4
    assert visible["metric_error_bound_m"] is None
    with pytest.raises(module.ComponentStopped, match="IDENTITY"):
        module._visible_support(observation, np.array([0.1, 0.1, 0.8]))


def test_zero_depth_cannot_support_component_identity():
    import base64

    from tests.test_molmo_grounded_planner import request_scene
    from tests.test_molmo_revalidation import rebuild

    module = importlib.import_module("cloud_edge_robot_arm.research.sol_molmo_components")
    observation = request_scene().observation
    invalid = rebuild(
        observation,
        depth_float32_base64=base64.b64encode(
            np.zeros(observation.width * observation.height, dtype="<f4").tobytes()
        ).decode(),
    )
    with pytest.raises(module.ComponentStopped, match="DEPTH"):
        module._visible_support(invalid, np.array([0.8, 0.1, 0.1]))
