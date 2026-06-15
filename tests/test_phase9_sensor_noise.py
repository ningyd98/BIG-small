from __future__ import annotations

from cloud_edge_robot_arm.simulation.evaluation.metrics import run_mujoco_physical_trial


def test_phase9_sensor_noise_changes_pose_error() -> None:
    none = run_mujoco_physical_trial("S01_NORMAL_STATIC", seed=6, randomization_level="NONE")
    moderate = run_mujoco_physical_trial(
        "S19_CAMERA_NOISE_AND_OCCLUSION", seed=6, randomization_level="MODERATE"
    )

    assert float(moderate.metrics["pose_position_error_m"]) >= float(
        none.metrics["pose_position_error_m"]
    )
