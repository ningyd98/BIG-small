"""Phase 9 物理仿真和跨后端验证回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from cloud_edge_robot_arm.simulation.evaluation.metrics import run_mujoco_physical_trial


def test_phase9_object_slip_is_detected_from_low_friction_scenario() -> None:
    normal = run_mujoco_physical_trial("S01_NORMAL_STATIC", seed=3, randomization_level="NONE")
    severe = run_mujoco_physical_trial(
        "S21_OBJECT_SLIP_AFTER_LIFT", seed=3, randomization_level="SEVERE"
    )

    assert float(severe.metrics["object_slip_distance_m"]) >= float(
        normal.metrics["object_slip_distance_m"]
    )
