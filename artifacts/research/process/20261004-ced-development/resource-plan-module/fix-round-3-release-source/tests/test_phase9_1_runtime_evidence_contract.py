"""Phase 9.1 ROS2/Isaac/MoveIt 边界回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from pytest import MonkeyPatch

from cloud_edge_robot_arm.simulation.environment import detect_environment
from cloud_edge_robot_arm.simulation.phase9_1 import verification
from cloud_edge_robot_arm.simulation.phase9_1.verification import CommandEvidence


def _ok(argv: list[str], *, timeout: float = 20) -> CommandEvidence:
    stdout = "jazzy\nrmw_fastrtps_cpp\n91" if "printenv ROS_DISTRO" in " ".join(argv) else "ok"
    return CommandEvidence(argv=argv, exit_code=0, stdout=stdout, stderr="")


def test_ros2_ready_environment_without_runtime_evidence_is_not_validated(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ROS_DISTRO", "jazzy")
    monkeypatch.setattr(verification, "_run", _ok)
    monkeypatch.setattr(
        verification, "_package_prefix", lambda package: f"/opt/ros/jazzy/{package}"
    )
    monkeypatch.setattr(verification, "_python_import_available", lambda module: True)

    result = verification.verify_ros2_integration(tmp_path)
    payload = result.to_jsonable()

    assert payload["status"] == "ROS2_READY"
    assert payload["validation_claimed"] is False
    assert payload["environment_ready"] is True
    assert cast(str, payload["runtime_evidence_path"]).endswith("ros2_runtime_evidence.json")


def test_moveit_ready_environment_without_runtime_evidence_is_not_validated(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ROS_DISTRO", "jazzy")
    monkeypatch.setattr(verification, "_run", _ok)
    monkeypatch.setattr(
        verification, "_package_prefix", lambda package: f"/opt/ros/jazzy/{package}"
    )
    monkeypatch.setattr(verification, "_python_import_available", lambda module: True)

    result = verification.verify_moveit_safety(tmp_path)
    payload = result.to_jsonable()

    assert payload["status"] == "MOVEIT_READY"
    assert payload["validation_claimed"] is False
    assert payload["environment_ready"] is True
    assert cast(str, payload["runtime_evidence_path"]).endswith("moveit_safety_evidence.json")


def test_ros_verifier_commands_use_output_scoped_ros_domain(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ROS_DISTRO", "jazzy")
    monkeypatch.setattr(verification, "_run", _ok)
    monkeypatch.setattr(
        verification,
        "_load_json",
        lambda path: {
            "validation_claimed": True,
            "artifact_provenance_complete": True,
            "checks": {
                name: {
                    "passed": True,
                    "command": ["python", "scripts/phase9/run_ros2_runtime_evidence.py"],
                    "exit_code": 0,
                    "start_wall_time": "2026-06-16T00:00:00Z",
                    "end_wall_time": "2026-06-16T00:00:01Z",
                    "ros_time": {"sec": 1, "nanosec": 0},
                    "log_path": str(path.with_suffix(".log")),
                    "observed_result": {"result": name},
                }
                for name in verification.ROS2_RUNTIME_CHECKS
            },
        },
    )

    result = verification.verify_ros2_integration(tmp_path / "ros", run_runtime=True)
    commands = [command.argv[-1] for command in result.commands]
    domains = {
        command.split("export ROS_DOMAIN_ID=", maxsplit=1)[1].split(" ", maxsplit=1)[0]
        for command in commands
        if "export ROS_DOMAIN_ID=" in command
    }

    assert len(domains) == 1
    assert 20 <= int(next(iter(domains))) < 90
    assert any("run_ros2_runtime_evidence.py" in command for command in commands)


def test_runtime_evidence_requires_all_required_fields(tmp_path: Path) -> None:
    evidence = _complete_evidence(tmp_path, verification.ROS2_RUNTIME_CHECKS)
    assert verification._evidence_has_required_runtime_fields(
        evidence,
        verification.ROS2_RUNTIME_CHECKS,
    )


def test_ros2_runtime_contract_requires_custom_message_service_and_action() -> None:
    assert "custom_message" in verification.ROS2_RUNTIME_CHECKS
    assert "custom_service" in verification.ROS2_RUNTIME_CHECKS
    assert "action_success" in verification.ROS2_RUNTIME_CHECKS


def test_ros2_runtime_node_crash_probe_kills_process_group() -> None:
    source = Path("scripts/phase9/run_ros2_runtime_evidence.py").read_text(encoding="utf-8")
    node_crash_body = source.split("    def _check_node_crash(", maxsplit=1)[1].split(
        "    def _check_node_restart_reconnect", maxsplit=1
    )[0]

    assert "os.killpg" in node_crash_body
    assert "os.getpgid" in node_crash_body


def test_runtime_evidence_missing_log_path_is_incomplete(tmp_path: Path) -> None:
    evidence = _complete_evidence(tmp_path, verification.ROS2_RUNTIME_CHECKS)
    first = next(iter(evidence["checks"].values()))
    first.pop("log_path")
    (tmp_path / "ros2_runtime_evidence.json").write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    assert not verification._evidence_has_required_runtime_fields(
        evidence,
        verification.ROS2_RUNTIME_CHECKS,
    )


def test_runtime_evidence_rejects_forbidden_process_log_markers(tmp_path: Path) -> None:
    log_path = tmp_path / "bridge.log"
    log_path.write_text("RCLError: failed to initialize wait set\n", encoding="utf-8")
    evidence = _complete_evidence(tmp_path, verification.ROS2_RUNTIME_CHECKS)
    first = next(iter(evidence["checks"].values()))
    first["log_path"] = str(log_path)
    evidence["log_integrity"]["violations"] = ["RCLError"]
    evidence["log_integrity"]["passed"] = False

    assert not verification._evidence_has_required_runtime_fields(
        evidence,
        verification.ROS2_RUNTIME_CHECKS,
    )


def test_moveit_collision_evidence_requires_full_collision_chain(tmp_path: Path) -> None:
    evidence = _complete_evidence(tmp_path, verification.MOVEIT_SAFETY_CHECKS)
    collision = evidence["checks"]["collision_path_rejection_or_valid_replanning"]
    collision["observed_result"] = {
        "moveit_error_code": 99999,
        "observed_result": "valid_replanning",
    }

    assert not verification._evidence_has_required_runtime_fields(
        evidence,
        verification.MOVEIT_SAFETY_CHECKS,
    )

    collision["observed_result"] = {
        "baseline_plan": {
            "moveit_error_code": 1,
            "trajectory_points": 3,
            "joint_space_path_length": 1.0,
        },
        "collision_object": {
            "id": "phase9_1_collision_box",
            "frame_id": "panda_link0",
            "dimensions": [0.25, 0.25, 0.25],
            "pose": {"x": 0.35, "y": 0.0, "z": 0.45},
        },
        "planning_scene_object": {
            "id": "phase9_1_collision_box",
            "frame_id": "world",
            "dimensions": [0.25, 0.25, 0.25],
            "pose": {"x": 0.35, "y": 0.0, "z": 0.45},
        },
        "planning_scene_confirmed": True,
        "replanned_or_rejected": "valid_replanning",
        "collision_free": True,
        "trajectory_delta": {
            "point_count_delta": 1,
            "joint_space_path_length_delta": 0.25,
            "max_joint_delta": 0.1,
            "changed": True,
        },
        "moveit_error_code": 1,
        "process_provenance": {"runtime": "robostack-moveit2"},
    }
    evidence["log_integrity"]["passed"] = True

    assert verification._evidence_has_required_runtime_fields(
        evidence,
        verification.MOVEIT_SAFETY_CHECKS,
    )


def test_moveit_collision_object_insertion_requires_scene_pose_and_dimensions(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path, verification.MOVEIT_SAFETY_CHECKS)
    insertion = evidence["checks"]["collision_object_insertion"]
    observed = insertion["observed_result"]
    assert isinstance(observed, dict)
    scene_object = observed["planning_scene_object"]
    assert isinstance(scene_object, dict)
    scene_object["pose"] = {"x": 0.0, "y": 0.0, "z": 0.0}

    assert not verification._evidence_has_required_runtime_fields(
        evidence,
        verification.MOVEIT_SAFETY_CHECKS,
    )


def test_moveit_timeout_evidence_rejects_generic_planning_failures(tmp_path: Path) -> None:
    evidence = _complete_evidence(tmp_path, verification.MOVEIT_SAFETY_CHECKS)
    timeout = evidence["checks"]["planning_timeout"]
    timeout["observed_result"] = {
        "configured_timeout_ms": 1.0,
        "planning_elapsed_ms": 5.0,
        "moveit_error_code": -31,
        "normal_budget_success": False,
        "timeout_budget_result": "failed",
    }

    assert not verification._evidence_has_required_runtime_fields(
        evidence,
        verification.MOVEIT_SAFETY_CHECKS,
    )

    timeout["observed_result"] = {
        "configured_timeout_ms": 1.0,
        "planning_start_wall_time": "2026-06-16T00:00:00Z",
        "planning_end_wall_time": "2026-06-16T00:00:00.010000Z",
        "planning_elapsed_ms": 10.0,
        "moveit_error_code": -6,
        "normal_budget_success": True,
        "timeout_budget_result": "TIMED_OUT",
        "target_reused_from_normal_budget": True,
        "alternative_timeout_criterion": "",
    }
    evidence["log_integrity"]["passed"] = True

    assert verification._evidence_has_required_runtime_fields(
        evidence,
        verification.MOVEIT_SAFETY_CHECKS,
    )


def _complete_evidence(tmp_path: Path, checks: tuple[str, ...]) -> dict[str, Any]:
    for name in checks:
        (tmp_path / f"{name}.json").write_text("{}", encoding="utf-8")
    return {
        "validation_claimed": True,
        "artifact_provenance_complete": True,
        "process_provenance": {"runtime": "robostack-moveit2", "run_id": "phase9_1"},
        "log_integrity": {
            "passed": True,
            "violations": [],
            "checked_logs": [str(tmp_path / f"{name}.json") for name in checks],
        },
        "checks": {
            name: {
                "passed": True,
                "command": ["python", "scripts/phase9/runtime.py"],
                "exit_code": 0,
                "start_wall_time": "2026-06-16T00:00:00Z",
                "end_wall_time": "2026-06-16T00:00:01Z",
                "ros_time": {"sec": 1, "nanosec": 0},
                "log_path": str(tmp_path / f"{name}.json"),
                "observed_result": _observed_result_for(name),
            }
            for name in checks
        },
    }


def _observed_result_for(name: str) -> dict[str, object]:
    if name == "node_crash":
        return {"pid": 123, "return_code": -9, "bridge_log": "bridge.log"}
    if name == "node_restart_reconnect":
        return {
            "status": "SCENARIO_LOADED",
            "accepted": True,
            "bridge_log": "bridge.log",
        }
    if name == "custom_service":
        return {
            "load_scenario_status": "SCENARIO_LOADED",
            "emergency_stop_status": "EMERGENCY_STOPPED",
        }
    if name == "collision_object_insertion":
        return {
            "success": True,
            "object_id": "phase9_1_collision_box",
            "collision_object": {
                "id": "phase9_1_collision_box",
                "frame_id": "panda_link0",
                "dimensions": [0.25, 0.25, 0.25],
                "pose": {"x": 0.35, "y": 0.0, "z": 0.45},
            },
            "planning_scene_object": {
                "id": "phase9_1_collision_box",
                "frame_id": "world",
                "dimensions": [0.25, 0.25, 0.25],
                "pose": {"x": 0.35, "y": 0.0, "z": 0.45},
            },
            "planning_scene_confirmed": True,
        }
    if name == "collision_path_rejection_or_valid_replanning":
        return {
            "baseline_plan": {
                "moveit_error_code": 1,
                "trajectory_points": 3,
                "joint_space_path_length": 1.0,
            },
            "collision_object": {
                "id": "phase9_1_collision_box",
                "frame_id": "panda_link0",
                "dimensions": [0.25, 0.25, 0.25],
                "pose": {"x": 0.35, "y": 0.0, "z": 0.45},
            },
            "planning_scene_object": {
                "id": "phase9_1_collision_box",
                "frame_id": "world",
                "dimensions": [0.25, 0.25, 0.25],
                "pose": {"x": 0.35, "y": 0.0, "z": 0.45},
            },
            "planning_scene_confirmed": True,
            "replanned_or_rejected": "valid_replanning",
            "collision_free": True,
            "trajectory_delta": {
                "point_count_delta": 1,
                "joint_space_path_length_delta": 0.25,
                "max_joint_delta": 0.1,
                "changed": True,
            },
            "moveit_error_code": 1,
            "process_provenance": {"runtime": "robostack-moveit2"},
        }
    if name == "planning_timeout":
        return {
            "configured_timeout_ms": 1.0,
            "planning_start_wall_time": "2026-06-16T00:00:00Z",
            "planning_end_wall_time": "2026-06-16T00:00:00.010000Z",
            "planning_elapsed_ms": 10.0,
            "moveit_error_code": -6,
            "normal_budget_success": True,
            "timeout_budget_result": "TIMED_OUT",
            "target_reused_from_normal_budget": True,
            "alternative_timeout_criterion": "",
        }
    return {"result": name}


def test_detector_supports_robostack_conda_without_opt_ros(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROS_DISTRO", "jazzy")
    monkeypatch.setenv("CONDA_DEFAULT_ENV", "bigsmall-ros2-jazzy-moveit")
    monkeypatch.setenv("CONDA_PREFIX", "/conda")
    monkeypatch.setenv("RMW_IMPLEMENTATION", "rmw_fastrtps_cpp")
    monkeypatch.setattr("shutil.which", lambda name: f"/conda/bin/{name}")
    monkeypatch.setattr(
        "cloud_edge_robot_arm.simulation.environment._package_version",
        lambda name: "3.2.0" if name == "mujoco" else "",
    )
    monkeypatch.setattr(
        "cloud_edge_robot_arm.simulation.environment._python_import_available",
        lambda module: module in {"rclpy", "ament_index_python", "moveit_configs_utils"},
    )
    monkeypatch.setattr(
        "cloud_edge_robot_arm.simulation.environment._ros_package_prefix",
        lambda package: (
            f"/conda/share/{package}"
            if package
            in {
                "rclpy",
                "moveit_ros_move_group",
                "moveit_msgs",
                "moveit_configs_utils",
                "moveit_resources_panda_moveit_config",
            }
            else ""
        ),
    )
    monkeypatch.setattr(
        "cloud_edge_robot_arm.simulation.environment._command",
        lambda argv: "ros2 cli" if "ros2 --version" in " ".join(argv) else "",
    )

    report = detect_environment()

    assert report.level == "MOVEIT_READY"
    assert report.details["ros2_ready"] is True
    assert report.details["moveit_ready"] is True
    assert report.details["ros_installation_mode"] == "conda-robostack"


def test_ros2_readiness_uses_valid_colcon_cli_probe() -> None:
    source = Path("src/cloud_edge_robot_arm/simulation/phase9_1/verification.py").read_text(
        encoding="utf-8"
    )

    assert "colcon --version" not in source
    assert "colcon --help" in source


def test_moveit_boundary_acceptance_probe_drains_accepted_goals() -> None:
    source = Path("scripts/phase9/run_moveit_safety_evidence.py").read_text(encoding="utf-8")
    function_body = source.split("    def _boundary_goal_accepted(", maxsplit=1)[1].split(
        "    def _call_reset_world", maxsplit=1
    )[0]

    assert "get_result_async" in function_body
    assert "cancel_goal_async" in function_body


def test_phase9_1_text_sanitizer_redacts_home_user_and_proxy_credentials(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("USER", "phase9user")
    monkeypatch.setenv("LOGNAME", "phase9user")

    text = (
        "/home/ningyd/project phase9user "
        "https_proxy=http://user:pass@example.invalid:8080 "
        "token=super-secret password=hunter2"
    )

    sanitized = verification._sanitize_text(text)

    assert "/home/ningyd" not in sanitized
    assert "phase9user" not in sanitized
    assert "user:pass" not in sanitized
    assert "super-secret" not in sanitized
    assert "hunter2" not in sanitized


def test_phase9_1_self_hosted_workflow_builds_before_full_workspace_activation() -> None:
    workflow = Path(".github/workflows/phase9-isaac-self-hosted.yml").read_text(encoding="utf-8")
    build_step = workflow.split("- name: Build persistent ROS 2 workspace", maxsplit=1)[1].split(
        "- name: Run Phase 9.1 ROS 2 runtime verifier", maxsplit=1
    )[0]
    ros_step = workflow.split("- name: Run Phase 9.1 ROS 2 runtime verifier", maxsplit=1)[1].split(
        "- name: Run Phase 9.1 MoveIt safety verifier", maxsplit=1
    )[0]
    moveit_step = workflow.split("- name: Run Phase 9.1 MoveIt safety verifier", maxsplit=1)[
        1
    ].split("- name: Run Phase 9.1 aggregate verifier", maxsplit=1)[0]
    aggregate_step = workflow.split("- name: Run Phase 9.1 aggregate verifier", maxsplit=1)[
        1
    ].split("- name: Upload Phase 9.1 artifacts", maxsplit=1)[0]

    assert "activate_ros2_moveit_env.sh" not in build_step
    assert 'conda activate "$BIGSMALL_CONDA_ENV"' in build_step
    assert "source scripts/phase9/activate_ros2_moveit_env.sh" in ros_step
    assert "source scripts/phase9/activate_ros2_moveit_env.sh" in moveit_step
    assert "activate_ros2_moveit_env.sh" not in aggregate_step
    assert "python scripts/verify_phase9_1.py --output artifacts/phase9_1" in aggregate_step
