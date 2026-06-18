"""Phase 9 物理仿真和跨后端验证回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from pathlib import Path

from cloud_edge_robot_arm.simulation.config import (
    RandomizationLevel,
    SimulatorConfig,
    load_simulator_config,
)


def test_phase9_simulator_config_loads_defaults() -> None:
    config = load_simulator_config(Path("configs/phase9/simulator.yaml"))

    assert config.backend == "mujoco"
    assert config.robot_profile == "franka_panda"
    assert config.physics_dt_s > 0
    assert config.control_dt_s >= config.physics_dt_s
    assert config.randomization_level == RandomizationLevel.NONE


def test_phase9_config_rejects_mixed_time_units() -> None:
    try:
        SimulatorConfig(physics_dt_s=0.02, control_dt_s=0.004, sensor_dt_s=0.033)
    except ValueError as exc:
        assert "control_dt_s" in str(exc)
    else:
        raise AssertionError("config accepted control_dt_s smaller than physics_dt_s")
