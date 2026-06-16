from __future__ import annotations

import json
from pathlib import Path
from typing import cast

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
    assert 100 <= int(next(iter(domains))) < 220
    assert any("run_ros2_runtime_evidence.py" in command for command in commands)


def test_runtime_evidence_requires_all_required_fields(tmp_path: Path) -> None:
    evidence = {
        "status": "ROS2_INTEGRATION_VALIDATED",
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
                "log_path": str(tmp_path / f"{name}.log"),
                "observed_result": {"result": name},
            }
            for name in verification.ROS2_RUNTIME_CHECKS
        },
    }
    assert verification._evidence_has_required_runtime_fields(
        evidence,
        verification.ROS2_RUNTIME_CHECKS,
    )


def test_ros2_runtime_contract_requires_custom_message_service_and_action() -> None:
    assert "custom_message" in verification.ROS2_RUNTIME_CHECKS
    assert "custom_service" in verification.ROS2_RUNTIME_CHECKS
    assert "action_success" in verification.ROS2_RUNTIME_CHECKS


def test_runtime_evidence_missing_log_path_is_incomplete(tmp_path: Path) -> None:
    evidence = {
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
                "observed_result": {"result": name},
            }
            for name in verification.ROS2_RUNTIME_CHECKS
        },
    }
    (tmp_path / "ros2_runtime_evidence.json").write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    assert not verification._evidence_has_required_runtime_fields(
        evidence,
        verification.ROS2_RUNTIME_CHECKS,
    )


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
