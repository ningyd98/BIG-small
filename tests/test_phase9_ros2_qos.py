from __future__ import annotations

from cloud_edge_robot_arm.simulation.ros2.qos import qos_profiles


def test_phase9_ros2_qos_distinguishes_sensor_and_command_reliability() -> None:
    profiles = qos_profiles()

    assert profiles["sensor"].reliability == "best_effort"
    assert profiles["command"].reliability == "reliable"
    assert profiles["emergency_stop"].durability == "transient_local"
