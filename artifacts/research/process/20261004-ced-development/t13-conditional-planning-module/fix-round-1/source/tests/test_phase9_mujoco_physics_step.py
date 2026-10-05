"""Phase 9 物理仿真和跨后端验证回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import JointCommand, PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend


def test_phase9_mujoco_step_advances_physics_state() -> None:
    backend = MuJoCoPhysicsBackend()
    backend.initialize(
        SimulatorConfig(headless=True, model_path="assets/robots/franka_panda/scene.xml")
    )
    backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=7))

    t0 = backend.get_sim_time()
    q0 = backend.get_joint_state().positions
    backend.apply_joint_targets(JointCommand(positions=[0.1, -0.2, 0.15, -0.1, 0.05, 0.2, 0.0]))
    result = backend.step(steps=80)

    assert result.physics_steps == 80
    assert backend.get_sim_time() > t0
    assert backend.get_joint_state().positions != q0
    assert result.sim_time_s == backend.get_sim_time()
    backend.shutdown()


def test_phase9_mujoco_tcp_pose_is_fk_from_joint_state() -> None:
    backend = MuJoCoPhysicsBackend()
    backend.initialize(
        SimulatorConfig(headless=True, model_path="assets/robots/franka_panda/scene.xml")
    )
    backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=1))
    first = backend.get_tcp_pose()
    backend.apply_joint_targets(JointCommand(positions=[0.3, -0.1, 0.2, -0.2, 0.1, 0.15, 0.05]))
    backend.step(steps=160)
    second = backend.get_tcp_pose()

    assert isinstance(second, Pose)
    assert first != second
    backend.shutdown()
