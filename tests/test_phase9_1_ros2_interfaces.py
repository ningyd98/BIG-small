from __future__ import annotations

from pathlib import Path

INTERFACE_ROOT = Path("ros2_ws/src/bigsmall_interfaces")


def test_phase9_1_ros2_interfaces_define_required_topics_and_time_domains() -> None:
    required = {
        "msg/ContactArray.msg",
        "msg/FaultEvent.msg",
        "msg/RobotState.msg",
        "msg/SafetyEvent.msg",
        "msg/SceneSummary.msg",
        "msg/SimulationStatus.msg",
    }

    for relative in required:
        text = (INTERFACE_ROOT / relative).read_text(encoding="utf-8")
        assert "builtin_interfaces/Time stamp" in text

    status = (INTERFACE_ROOT / "msg/SimulationStatus.msg").read_text(encoding="utf-8")
    assert "float64 simulation_time_s" in status
    assert "float64 ros_time_s" in status
    assert "float64 wall_time_s" in status


def test_phase9_1_ros2_interfaces_define_actions_services_and_command_identity() -> None:
    required = {
        "action/FollowJointTrajectory.action",
        "action/MoveToPose.action",
        "srv/EmergencyStop.srv",
        "srv/GripperCommand.srv",
        "srv/InjectFault.srv",
        "srv/LoadScenario.srv",
        "srv/ResetWorld.srv",
    }
    for relative in required:
        path = INTERFACE_ROOT / relative
        text = path.read_text(encoding="utf-8")
        assert "CommandHeader header" in text
        assert "---" in text

    header = (INTERFACE_ROOT / "msg/CommandHeader.msg").read_text(encoding="utf-8")
    assert "uint64 command_seq" in header
    assert "uint64 plan_version" in header
