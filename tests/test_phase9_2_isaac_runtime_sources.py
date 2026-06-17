from __future__ import annotations

from pathlib import Path


def test_isaac_standalone_app_contains_real_runtime_paths() -> None:
    source = Path("scripts/phase9/isaac_standalone_app.py").read_text(encoding="utf-8")

    required_tokens = [
        "SimulationApp",
        "UsdPhysics",
        "MJCFImporter",
        "open_stage",
        "SimulationContext",
        "SingleArticulation",
        "Camera",
        "ContactSensor",
        "set_joint_positions",
        "get_joint_positions",
        "get_joint_velocities",
        "get_world_pose",
        "get_rgba",
        "get_depth",
        "reset_world",
        "follow_joint_trajectory",
        "emergency_stop",
        "sensor_request",
        "shutdown",
        "stage_metadata.json",
        "robot_state_sample.json",
        "rgb_sample.png",
        "depth_sample.npy",
        "contact_sample.json",
    ]
    for token in required_tokens:
        assert token in source


def test_phase9_2_verification_never_claims_isaac_from_source_guard() -> None:
    source = Path("src/cloud_edge_robot_arm/simulation/phase9_2/verification.py").read_text(
        encoding="utf-8"
    )

    assert "validation_claimed" in source
    assert "real_isaac_run_count" in source
    assert "ISAAC_SMOKE_VALIDATED" in source
    assert "source guard" not in source.lower()
