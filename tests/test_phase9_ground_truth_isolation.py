from __future__ import annotations

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend


def test_phase9_sensor_frame_marks_ground_truth_not_used_for_control() -> None:
    backend = MuJoCoPhysicsBackend()
    backend.initialize(SimulatorConfig(model_path="assets/robots/franka_panda/scene.xml"))
    backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=0))

    assert backend.get_sensor_frame().ground_truth_used_for_control is False
    backend.shutdown()
