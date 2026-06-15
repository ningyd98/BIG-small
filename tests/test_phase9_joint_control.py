from __future__ import annotations

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import JointCommand, PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend


def test_phase9_joint_control_enforces_joint_count_and_limits() -> None:
    backend = MuJoCoPhysicsBackend()
    backend.initialize(SimulatorConfig(model_path="assets/robots/franka_panda/scene.xml"))
    backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=0))
    backend.apply_joint_targets(JointCommand(positions=[10, -10, 5, -5, 4, -4, 3]))
    backend.step(steps=20)

    assert all(-2.8 <= position <= 2.8 for position in backend.get_joint_state().positions)
    backend.shutdown()


def test_phase9_joint_control_rejects_wrong_joint_count() -> None:
    backend = MuJoCoPhysicsBackend()
    backend.initialize(SimulatorConfig(model_path="assets/robots/franka_panda/scene.xml"))
    backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=0))
    try:
        backend.apply_joint_targets(JointCommand(positions=[0.0]))
    except ValueError as exc:
        assert "7 joint" in str(exc)
    else:
        raise AssertionError("wrong joint count accepted")
    backend.shutdown()
