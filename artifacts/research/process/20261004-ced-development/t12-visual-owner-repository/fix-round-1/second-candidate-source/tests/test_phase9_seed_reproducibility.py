"""Phase 9 物理仿真和跨后端验证回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from cloud_edge_robot_arm.simulation.evaluation.metrics import run_mujoco_physical_trial


def test_phase9_same_seed_reproduces_physical_metrics() -> None:
    first = run_mujoco_physical_trial("S01_NORMAL_STATIC", seed=11, randomization_level="MODERATE")
    second = run_mujoco_physical_trial("S01_NORMAL_STATIC", seed=11, randomization_level="MODERATE")

    assert first.result_hash == second.result_hash
    assert first.metrics == second.metrics


def test_phase9_different_seed_changes_physical_or_sensor_metrics() -> None:
    first = run_mujoco_physical_trial("S01_NORMAL_STATIC", seed=11, randomization_level="MODERATE")
    second = run_mujoco_physical_trial("S01_NORMAL_STATIC", seed=12, randomization_level="MODERATE")

    differing = [
        "joint_tracking_rmse",
        "tcp_position_error_m",
        "sensor_latency_ms",
        "object_slip_distance_m",
    ]
    assert any(first.metrics[name] != second.metrics[name] for name in differing)
