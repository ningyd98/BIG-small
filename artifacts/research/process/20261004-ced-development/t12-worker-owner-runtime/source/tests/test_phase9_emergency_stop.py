"""Phase 9 物理仿真和跨后端验证回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.physics_robot_adapter import PhysicsRobotAdapter


def test_phase9_emergency_stop_cancels_motion_commands() -> None:
    backend = MuJoCoPhysicsBackend()
    backend.initialize(
        SimulatorConfig(headless=True, model_path="assets/robots/franka_panda/scene.xml")
    )
    backend.reset(PhysicalScenarioConfig.scenario("S14_EMERGENCY_STOP", seed=5))
    robot = PhysicsRobotAdapter(backend)
    robot.connect()

    stop = robot.emergency_stop(timeout_ms=1_000)
    after_stop_steps = backend.total_physics_steps
    move = robot.home(timeout_ms=1_000)

    assert stop.success
    assert backend.estop_engaged
    assert not move.success
    assert move.error_code == "EMERGENCY_STOP_ENGAGED"
    assert backend.total_physics_steps == after_stop_steps
    backend.shutdown()
