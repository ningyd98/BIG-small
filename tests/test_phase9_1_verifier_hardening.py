"""Phase 9.1 ROS2/Isaac/MoveIt 边界回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pytest import MonkeyPatch
from scripts.verify_phase9_1 import _phase9_1_acceptance_ready, _phase9_1_status

from cloud_edge_robot_arm.simulation.models import PhysicalTrialResult
from cloud_edge_robot_arm.simulation.phase9_1 import verification
from cloud_edge_robot_arm.simulation.phase9_1.verification import CommandEvidence


def _ok(argv: list[str], *, timeout: float = 20) -> CommandEvidence:
    stdout = "jazzy\nrmw_fastrtps_cpp\n91" if "printenv ROS_DISTRO" in " ".join(argv) else "ok"
    return CommandEvidence(argv=argv, exit_code=0, stdout=stdout, stderr="")


def test_phase9_1_ros_moveit_verifiers_do_not_require_core_mujoco_imports() -> None:
    source = Path("src/cloud_edge_robot_arm/simulation/phase9_1/verification.py").read_text(
        encoding="utf-8"
    )
    ros_moveit_section = source.split("def verify_cross_backend", maxsplit=1)[0]

    assert (
        "simulation.evaluation.metrics import run_mujoco_physical_trial" not in ros_moveit_section
    )


def test_ros2_env_ready_without_runtime_evidence_is_not_validated(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ROS_DISTRO", "jazzy")
    monkeypatch.setattr(verification, "_run", _ok)

    result = verification.verify_ros2_integration(tmp_path)
    payload = result.to_jsonable()

    assert payload["status"] == "ROS2_READY"
    assert payload["validation_claimed"] is False
    for key in (
        "qos_checked",
        "namespace_checked",
        "timestamp_checked",
        "action_timeout_checked",
        "cancel_checked",
        "node_crash_reconnect_checked",
    ):
        assert payload[key] is False
    assert "runtime evidence" in " ".join(result.blockers)


def test_moveit_ready_without_safety_evidence_is_not_validated(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(verification, "_run", _ok)

    result = verification.verify_moveit_safety(tmp_path)
    payload = result.to_jsonable()

    assert payload["status"] == "MOVEIT_READY"
    assert payload["validation_claimed"] is False
    for key in (
        "reachability_checked",
        "joint_limits_checked",
        "collision_scene_checked",
        "planning_failure_checked",
        "execution_cancel_checked",
        "emergency_stop_boundary_checked",
    ):
        assert payload[key] is False


def test_isaac_ready_without_smoke_artifact_does_not_claim_real_run(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    isaac_root = tmp_path / "isaac"
    isaac_root.mkdir()
    python_sh = isaac_root / "python.sh"
    python_sh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python_sh.chmod(0o755)
    monkeypatch.setenv("ISAAC_SIM_ROOT", str(isaac_root))
    monkeypatch.setattr(verification, "_run", _ok)

    result = verification.verify_isaac_smoke(tmp_path)
    payload = result.to_jsonable()

    assert payload["status"] == "ISAAC_READY"
    assert payload["validation_claimed"] is False
    assert payload["real_isaac_run_count"] == 0
    assert payload["rgb_sensor_checked"] is False
    assert payload["depth_sensor_checked"] is False
    assert payload["contact_sensor_checked"] is False
    assert payload["moveit_execution_checked"] is False


def test_cross_backend_requires_real_isaac_artifact_even_when_env_ready(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        verification, "detect_environment", lambda: SimpleNamespace(level="ISAAC_READY")
    )

    payload = verification.verify_cross_backend(tmp_path)

    assert payload["status"] in {"BLOCKED_BY_ENV", "NOT_RUN"}
    assert payload["validation_claimed"] is False
    assert payload["isaac_comparison_status"] in {"MISSING_ISAAC_ARTIFACT", "NOT_RUN"}


def test_cross_backend_env_block_does_not_require_core_mujoco_import(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        verification, "detect_environment", lambda: SimpleNamespace(level="MOVEIT_READY")
    )
    monkeypatch.setattr(
        verification,
        "run_mujoco_physical_trial",
        lambda *args, **kwargs: (_ for _ in ()).throw(ModuleNotFoundError("pydantic")),
    )

    payload = verification.verify_cross_backend(tmp_path)

    assert payload["status"] == "BLOCKED_BY_ENV"
    assert payload["mujoco_reference_status"] == "NOT_RUN_CORE_ENV_UNAVAILABLE"
    assert payload["isaac_comparison_status"] == "NOT_RUN_BLOCKED_BY_ENV"
    assert payload["validation_claimed"] is False


def test_safety_pressure_counts_real_trials_hashes_and_estop_records(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, int, str]] = []

    def fake_trial(scenario_id: str, *, seed: int, randomization_level: str) -> PhysicalTrialResult:
        calls.append((scenario_id, seed, randomization_level))
        return PhysicalTrialResult(
            scenario_id=scenario_id,
            seed=seed,
            randomization_level=randomization_level,
            result_hash=f"hash-{seed % 17}",
            metrics={
                "illegal_collision_count": 1 if seed in {3, 17} else 0,
                "emergency_stop_post_command_count": 2 if seed in {5, 19} else 0,
            },
        )

    monkeypatch.setattr(verification, "run_mujoco_physical_trial", fake_trial)

    payload = verification.run_safety_pressure(tmp_path, trials=500)

    assert len(calls) == 500
    assert payload["trial_count"] == 500
    assert payload["illegal_collision_count"] == 2
    assert payload["emergency_stop_post_command_count"] == 4
    assert payload["unique_result_hash_count"] == 17
    assert payload["status"] == "FAILED"


def test_phase9_1_acceptance_requires_all_runtime_evidence() -> None:
    components: dict[str, dict[str, object]] = {
        "ros2": {
            "validation_claimed": True,
            "qos_checked": True,
            "namespace_checked": True,
            "timestamp_checked": True,
            "action_timeout_checked": True,
            "cancel_checked": True,
            "node_crash_reconnect_checked": False,
        },
        "moveit": {
            "validation_claimed": True,
            "reachability_checked": True,
            "joint_limits_checked": True,
            "collision_scene_checked": True,
            "planning_failure_checked": True,
            "execution_cancel_checked": True,
            "emergency_stop_boundary_checked": True,
        },
        "isaac": {
            "validation_claimed": True,
            "real_isaac_run_count": 1,
        },
    }
    cross_backend: dict[str, object] = {
        "validation_claimed": True,
        "artifact_provenance_complete": True,
        "success_rate_delta": 0.0,
        "completion_time_delta": 0.0,
        "joint_rmse": 0.1,
        "tcp_rmse": 0.1,
        "collision_count_delta": 0,
        "state_machine_final_state_consistency": True,
    }
    isaac_benchmark_guard = {"validation_claimed": True, "benchmark_status": "PASSED"}
    safety_pressure = {
        "status": "PASSED",
        "trial_count": 500,
        "illegal_collision_count": 0,
        "emergency_stop_post_command_count": 0,
        "unique_result_hash_count": 20,
    }

    assert not _phase9_1_acceptance_ready(
        components=components,
        cross_backend=cross_backend,
        isaac_benchmark_guard=isaac_benchmark_guard,
        safety_pressure=safety_pressure,
    )


def test_phase9_1_rejects_incomplete_ros2_even_when_isaac_is_blocked() -> None:
    components = _components(ros2_status="INCOMPLETE")

    assert _phase9_1_status(**_status_inputs(components)) == "PHASE9_1_REJECTED"


def test_phase9_1_rejects_ros2_ready_even_when_isaac_is_blocked() -> None:
    components = _components(ros2_status="ROS2_READY")

    assert _phase9_1_status(**_status_inputs(components)) == "PHASE9_1_REJECTED"


def test_phase9_1_rejects_incomplete_moveit_even_when_isaac_is_blocked() -> None:
    components = _components(moveit_status="INCOMPLETE")

    assert _phase9_1_status(**_status_inputs(components)) == "PHASE9_1_REJECTED"


def test_phase9_1_rejects_moveit_ready_even_when_isaac_is_blocked() -> None:
    components = _components(moveit_status="MOVEIT_READY")

    assert _phase9_1_status(**_status_inputs(components)) == "PHASE9_1_REJECTED"


def test_phase9_1_core_accepts_only_validated_ros2_moveit_with_isaac_blocked() -> None:
    components = _components()

    assert _phase9_1_status(**_status_inputs(components)) == "PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK"


def test_phase9_1_rejects_cross_backend_incomplete_even_when_isaac_is_blocked() -> None:
    components = _components()
    inputs = _status_inputs(components)
    inputs["cross_backend"] = {
        "status": "NOT_RUN",
        "validation_claimed": False,
        "artifact_provenance_complete": False,
        "isaac_comparison_status": "MISSING_ISAAC_ARTIFACT",
    }

    assert _phase9_1_status(**inputs) == "PHASE9_1_REJECTED"


def test_phase9_1_accepts_when_all_runtime_components_and_cross_backend_validate() -> None:
    components = _components(
        isaac_status="ISAAC_SMOKE_VALIDATED",
        isaac_validation_claimed=True,
        isaac_environment_ready=True,
        real_isaac_run_count=1,
    )
    cross_backend = {
        "status": "CROSS_BACKEND_VALIDATED",
        "validation_claimed": True,
        "artifact_provenance_complete": True,
        "success_rate_delta": 0.0,
        "completion_time_delta": 0.0,
        "joint_rmse": 0.1,
        "tcp_rmse": 0.1,
        "collision_count_delta": 0,
        "state_machine_final_state_consistency": True,
    }
    isaac_benchmark_guard = {
        "status": "PASSED",
        "benchmark_status": "PASSED",
        "validation_claimed": True,
    }

    assert (
        _phase9_1_status(
            **_status_inputs(
                components,
                cross_backend=cross_backend,
                isaac_benchmark_guard=isaac_benchmark_guard,
            )
        )
        == "PHASE9_1_ACCEPTED"
    )


def _components(
    *,
    ros2_status: str = "ROS2_INTEGRATION_VALIDATED",
    moveit_status: str = "MOVEIT_SAFETY_VALIDATED",
    isaac_status: str = "BLOCKED_BY_ENV",
    isaac_validation_claimed: bool = False,
    isaac_environment_ready: bool = False,
    real_isaac_run_count: int = 0,
) -> dict[str, dict[str, object]]:
    return {
        "ros2": {
            "status": ros2_status,
            "validation_claimed": ros2_status == "ROS2_INTEGRATION_VALIDATED",
            "environment_ready": ros2_status != "BLOCKED_BY_ENV",
            "custom_interfaces_checked": ros2_status == "ROS2_INTEGRATION_VALIDATED",
            "qos_checked": ros2_status == "ROS2_INTEGRATION_VALIDATED",
            "namespace_checked": ros2_status == "ROS2_INTEGRATION_VALIDATED",
            "timestamp_checked": ros2_status == "ROS2_INTEGRATION_VALIDATED",
            "action_timeout_checked": ros2_status == "ROS2_INTEGRATION_VALIDATED",
            "cancel_checked": ros2_status == "ROS2_INTEGRATION_VALIDATED",
            "node_crash_reconnect_checked": ros2_status == "ROS2_INTEGRATION_VALIDATED",
        },
        "moveit": {
            "status": moveit_status,
            "validation_claimed": moveit_status == "MOVEIT_SAFETY_VALIDATED",
            "environment_ready": moveit_status != "BLOCKED_BY_ENV",
            "reachability_checked": moveit_status == "MOVEIT_SAFETY_VALIDATED",
            "joint_limits_checked": moveit_status == "MOVEIT_SAFETY_VALIDATED",
            "collision_scene_checked": moveit_status == "MOVEIT_SAFETY_VALIDATED",
            "planning_failure_checked": moveit_status == "MOVEIT_SAFETY_VALIDATED",
            "execution_cancel_checked": moveit_status == "MOVEIT_SAFETY_VALIDATED",
            "emergency_stop_boundary_checked": moveit_status == "MOVEIT_SAFETY_VALIDATED",
        },
        "isaac": {
            "status": isaac_status,
            "validation_claimed": isaac_validation_claimed,
            "environment_ready": isaac_environment_ready,
            "real_isaac_run_count": real_isaac_run_count,
        },
    }


def _status_inputs(
    components: dict[str, dict[str, object]],
    *,
    cross_backend: dict[str, object] | None = None,
    isaac_benchmark_guard: dict[str, object] | None = None,
) -> dict[str, Any]:
    return {
        "components": components,
        "cross_backend": cross_backend
        or {
            "status": "BLOCKED_BY_ENV",
            "validation_claimed": False,
            "artifact_provenance_complete": False,
            "isaac_comparison_status": "NOT_RUN_BLOCKED_BY_ENV",
        },
        "isaac_benchmark_guard": isaac_benchmark_guard
        or {
            "status": "PASSED",
            "benchmark_status": "BLOCKED_BY_ENV",
            "validation_claimed": False,
        },
        "safety_pressure": {
            "status": "PASSED",
            "trial_count": 500,
            "illegal_collision_count": 0,
            "emergency_stop_post_command_count": 0,
            "unique_result_hash_count": 20,
        },
        "history": {"returncode": 0},
        "process_protocol_guard": {"status": "PASSED"},
        "isaac_backend_guard": {"status": "PASSED"},
        "ros_interface_guard": {"status": "PASSED"},
        "ros_bridge_source_guard": {"status": "PASSED"},
        "moveit_source_guard": {"status": "PASSED"},
    }
