from __future__ import annotations

from cloud_edge_robot_arm.simulation.evaluation.metrics import run_mujoco_physical_trial


def test_phase9_mass_and_friction_change_physical_metrics() -> None:
    mild = run_mujoco_physical_trial(
        "S16_PAYLOAD_MASS_VARIATION", seed=8, randomization_level="MILD"
    )
    severe = run_mujoco_physical_trial(
        "S17_CONTACT_FRICTION_VARIATION", seed=8, randomization_level="SEVERE"
    )

    assert mild.metrics != severe.metrics
