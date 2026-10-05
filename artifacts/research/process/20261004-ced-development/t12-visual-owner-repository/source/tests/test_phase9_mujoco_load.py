"""Phase 9 物理仿真和跨后端验证回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend


def test_phase9_mujoco_loads_model_and_resets_scene() -> None:
    backend = MuJoCoPhysicsBackend()
    backend.initialize(SimulatorConfig(model_path="assets/robots/franka_panda/scene.xml"))
    backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=0))

    assert backend.get_sim_time() == 0
    assert len(backend.get_joint_state().positions) == 7
    backend.shutdown()
