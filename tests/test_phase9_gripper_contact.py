from __future__ import annotations

from cloud_edge_robot_arm.simulation.evaluation.metrics import run_mujoco_physical_trial


def test_phase9_grasp_contact_metric_comes_from_contact_channel() -> None:
    result = run_mujoco_physical_trial("S01_NORMAL_STATIC", seed=2, randomization_level="NONE")

    assert "grasp_contact_count" in result.metrics
    assert result.metrics["expected_contact_count"] == result.metrics["grasp_contact_count"]
