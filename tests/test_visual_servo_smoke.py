"""The offline development entry must exercise real RGBD-driven motion."""

import importlib

import pytest


def test_fixed_camera_smoke_records_real_visual_feedback(tmp_path):
    module = importlib.import_module("scripts.verify_visual_servo")
    result = module.run_case("fixed", tmp_path / "case")
    assert result["feedback_count"] >= 3, result
    assert result["model_calls"] == 0
    assert result["hardware_dispatch"] is False
    assert result["simulation_visual_hz"] == 30
    assert result["motion_status"] == "SUCCEEDED", result
    assert result["final_position_error_m"] <= 0.005
    assert result["independent_horizontal_error_m"] <= 0.005


@pytest.mark.parametrize("fault", ["no_injection", "wrong_reason", "command_after", "late_stop"])
def test_loss_gate_requires_actual_injection_and_immediate_observation_stop(fault):
    module = importlib.import_module("scripts.verify_visual_servo")
    result = {
        "case": "loss", "motion_status": "STOPPED", "held_on_exit": True,
        "terminal_reason": "ValueError:servo registered marker geometry unavailable",
        "feedback_count": 7, "loss_injected_at_step": 56,
        "last_safe_sample_step": 48, "stop_physics_step": 56,
        "joint_commands_after_loss": 0,
    }
    if fault == "no_injection":
        result["loss_injected_at_step"] = None
    elif fault == "wrong_reason":
        result["terminal_reason"] = "ValueError:visual servo sample/IK deadline exceeded"
    elif fault == "command_after":
        result["joint_commands_after_loss"] = 1
    else:
        result["stop_physics_step"] = 57
    assert not module.case_passed(result)


@pytest.mark.parametrize("case", ["target_motion", "camera_move"])
def test_perturbation_gate_requires_measured_motion(case):
    module = importlib.import_module("scripts.verify_visual_servo")
    assert not module.case_passed({
        "case": case, "motion_status": "SUCCEEDED", "held_on_exit": True,
        "final_position_error_m": 0.001, "independent_horizontal_error_m": 0.001,
        "feedback_count": 90, "camera_translation_m": 0,
        "independent_object_displacement_m": 0,
    })
