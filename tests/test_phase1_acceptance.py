from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cloud_edge_robot_arm.contracts import ActionResult, Pose
from cloud_edge_robot_arm.edge.fixed_pick_place import run_fixed_pick_place
from cloud_edge_robot_arm.edge.robot_adapter import RobotAdapter
from cloud_edge_robot_arm.simulation.mock_robot import FaultCode, MockRobotAdapter, MockScene
from cloud_edge_robot_arm.simulation.mujoco_adapter import MuJoCoRobotAdapter

ROOT = Path(__file__).resolve().parents[1]


def test_mock_robot_adapter_implements_unified_interface() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)

    assert isinstance(robot, RobotAdapter)
    for method_name in (
        "connect",
        "disconnect",
        "home",
        "move_to_pose",
        "open_gripper",
        "close_gripper",
        "get_state",
        "stop",
        "emergency_stop",
    ):
        assert callable(getattr(robot, method_name))


def test_every_action_returns_required_structured_action_result_fields() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    result = robot.move_to_pose(Pose(x=0.1, y=0.1, z=0.15), timeout_ms=100)

    assert isinstance(result, ActionResult)
    assert result.success is True
    assert result.action_id
    assert result.action_type == "MOVE_TO_POSE"
    assert result.started_at.tzinfo is not None
    assert result.finished_at.tzinfo is not None
    assert result.duration_ms >= 0
    assert result.error_code is None
    assert result.error_message is None
    assert result.state_before["tcp_pose"] != result.state_after["tcp_pose"]


def test_mock_robot_supports_action_duration_simulation_and_timeout() -> None:
    robot = MockRobotAdapter(
        scene=MockScene.with_default_pick_place_scene(),
        auto_connect=True,
        default_action_duration_ms=50,
    )

    result = robot.move_to_pose(Pose(x=0.1, y=0.0, z=0.1), timeout_ms=10)

    assert result.success is False
    assert result.error_code == FaultCode.ACTION_TIMEOUT.value
    assert result.duration_ms == 10
    assert result.state_before == result.state_after


@pytest.mark.parametrize(
    ("fault", "action_name"),
    [
        (FaultCode.ACTION_TIMEOUT, "home"),
        (FaultCode.TARGET_UNREACHABLE, "move_above"),
        (FaultCode.GRASP_FAILED, "grasp"),
        (FaultCode.OBJECT_DROPPED, "lift"),
        (FaultCode.ROBOT_DISCONNECTED, "home"),
        (FaultCode.EMERGENCY_STOP_ACTIVE, "home"),
        (FaultCode.COLLISION_DETECTED, "home"),
        (FaultCode.INVALID_TARGET_POSE, "move_to_pose"),
    ],
)
def test_all_required_fault_injections_return_structured_errors(
    fault: FaultCode,
    action_name: str,
) -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    robot.inject_fault(fault)
    if fault in {FaultCode.GRASP_FAILED, FaultCode.OBJECT_DROPPED}:
        robot.move_above("red_cube")
        robot.approach("red_cube")
    if fault == FaultCode.OBJECT_DROPPED:
        robot.grasp("red_cube")

    if action_name == "move_above":
        result = robot.move_above("red_cube")
    elif action_name == "grasp":
        result = robot.grasp("red_cube")
    elif action_name == "lift":
        result = robot.lift(0.1)
    elif action_name == "move_to_pose":
        result = robot.move_to_pose(Pose(x=0.1, y=0.0, z=0.1))
    else:
        result = robot.home()

    assert result.success is False
    assert result.error_code == fault.value
    assert result.error_message
    assert result.state_before
    assert result.state_after


def test_safe_stop_uses_emergency_stop_path() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)

    result = robot.safe_stop()

    assert result.success is True
    assert result.action_type == "SAFE_STOP"
    assert robot.get_state().estop_engaged is True
    assert result.state_after["estop_engaged"] is True


def test_fixed_pick_place_runs_exact_phase_one_sequence() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)

    summary = run_fixed_pick_place(robot)

    assert summary.success is True
    assert summary.final_region == "bin_a"
    assert summary.history == [
        "HOME",
        "MOVE_ABOVE",
        "APPROACH",
        "GRASP",
        "LIFT",
        "MOVE_TO_REGION",
        "PLACE",
        "RELEASE",
        "RETREAT",
        "HOME",
    ]


def test_fixed_pick_place_can_run_twenty_times_deterministically() -> None:
    successes = 0
    for _ in range(20):
        robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
        summary = run_fixed_pick_place(robot)
        successes += int(summary.success)

    assert successes == 20


def test_mujoco_adapter_reports_installation_guidance_when_unavailable() -> None:
    adapter = MuJoCoRobotAdapter()
    result = adapter.connect()

    assert isinstance(adapter, RobotAdapter)
    if result.success is False:
        assert result.error_code == "MUJOCO_NOT_INSTALLED"
        assert "pip install" in (result.error_message or "")


def test_fixed_pick_place_script_outputs_repeat_success_rate() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_fixed_pick_place.py",
            "--adapter",
            "mock",
            "--repeat",
            "3",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["adapter"] == "mock"
    assert payload["repeat"] == 3
    assert payload["successes"] == 3
    assert payload["success_rate"] == 1.0
