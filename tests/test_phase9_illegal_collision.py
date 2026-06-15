from __future__ import annotations

from cloud_edge_robot_arm.simulation.evaluation.metrics import run_mujoco_physical_trial


def test_phase9_normal_static_has_no_illegal_collision_metric() -> None:
    result = run_mujoco_physical_trial("S01_NORMAL_STATIC", seed=0, randomization_level="NONE")

    assert result.metrics["illegal_collision_count"] == 0
    assert result.metrics["illegal_collision_impulse"] == 0
