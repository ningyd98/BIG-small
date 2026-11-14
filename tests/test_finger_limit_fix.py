"""手指监测必须拒绝越界反馈，同时保留米制容差及只读边界。"""

import math

import numpy as np
import pytest

from cloud_edge_robot_arm.research.sol_molmo_components import (
    ComponentStopped,
    check_component_hard_state,
)
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot


@pytest.fixture
def physical_robot():
    backend = MuJoCoPhysicsBackend()
    backend.initialize(SimulatorConfig())
    backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=42001))
    try:
        yield backend, MuJoCoSkillRobot(backend)
    finally:
        backend.shutdown()


@pytest.mark.parametrize("finger", ["finger_left_joint", "finger_right_joint"])
@pytest.mark.parametrize("position", [-0.000101, 0.040101, math.nan, math.inf, -math.inf])
def test_finger_outside_tolerance_stops_before_another_command(physical_robot, finger, position):
    # Deleting either finger check, ignoring a lower bound, or admitting NaN breaks this test.
    backend, robot = physical_robot
    address = backend._model.joint(finger).qposadr[0]
    backend._data.qpos[address] = position
    with pytest.raises(ComponentStopped, match="HARD_FINGER_LIMIT"):
        check_component_hard_state(backend, robot)
    assert backend.total_physics_steps == 0


@pytest.mark.parametrize("finger", ["finger_left_joint", "finger_right_joint"])
@pytest.mark.parametrize("position", [-0.0001, -0.00005, 0.0, 0.02, 0.039, 0.04, 0.04005, 0.0401])
def test_finger_within_metre_tolerance_remains_allowed(physical_robot, finger, position):
    # Applying the arm's 1e-6 rad margin to a finger incorrectly rejects these safe readings.
    backend, robot = physical_robot
    backend._data.qpos[backend._model.joint(finger).qposadr[0]] = position
    check_component_hard_state(backend, robot)
    assert backend.total_physics_steps == 0


def test_finger_check_does_not_read_object_truth_or_mutate_physics(physical_robot, monkeypatch):
    backend, robot = physical_robot

    def forbidden():
        raise AssertionError("online checks cannot consume evaluator truth")

    monkeypatch.setattr(backend, "current_physics_observation", forbidden)
    qpos, qvel, ctrl = (
        array.copy() for array in (backend._data.qpos, backend._data.qvel, backend._data.ctrl)
    )
    check_component_hard_state(backend, robot)
    np.testing.assert_array_equal(backend._data.qpos, qpos)
    np.testing.assert_array_equal(backend._data.qvel, qvel)
    np.testing.assert_array_equal(backend._data.ctrl, ctrl)
    assert backend.total_physics_steps == 0


def test_finger_guard_exception_aborts_the_active_physics_batch(physical_robot):
    backend, robot = physical_robot
    backend._data.qpos[backend._model.joint("finger_right_joint").qposadr[0]] = 0.0403
    with backend.observe_physics_steps(
        lambda _snapshot: check_component_hard_state(backend, robot)
    ):
        with pytest.raises(ComponentStopped, match="HARD_FINGER_LIMIT"):
            backend.step(10)
    assert backend.total_physics_steps == 1
    robot.safe_stop()
    assert backend.total_physics_steps == 1
    assert robot.get_state().estop_engaged
