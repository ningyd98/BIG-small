"""Phase 9 物理仿真和跨后端验证回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.physics_robot_adapter import PhysicsRobotAdapter


def test_phase9_move_to_pose_generates_physics_steps_not_teleport() -> None:
    backend = MuJoCoPhysicsBackend()
    backend.initialize(
        SimulatorConfig(headless=True, model_path="assets/robots/franka_panda/scene.xml")
    )
    backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=4))
    robot = PhysicsRobotAdapter(backend)
    robot.connect()

    before_pose = backend.get_tcp_pose()
    before_steps = backend.total_physics_steps
    target = Pose(x=before_pose.x + 0.03, y=before_pose.y - 0.02, z=before_pose.z + 0.01)
    result = robot.move_to_pose(target, timeout_ms=3_000)

    assert result.success
    assert backend.total_physics_steps > before_steps
    assert result.duration_ms > 0
    assert result.details["physics_steps"] > 0
    assert result.state_before["tcp_pose"] != result.state_after["tcp_pose"]
    backend.shutdown()
