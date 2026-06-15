from __future__ import annotations

from typing import Any, cast

from cloud_edge_robot_arm.simulation.models import JointStateSnapshot
from cloud_edge_robot_arm.simulation.ros2.conversion import joint_state_to_message


def test_phase9_ros2_joint_state_conversion_has_timestamp() -> None:
    msg = joint_state_to_message(
        JointStateSnapshot(
            names=["joint1"], positions=[0.1], velocities=[0.0], efforts=[0.0], sim_time_s=1.5
        )
    )

    header = cast(dict[str, Any], msg["header"])
    assert header["stamp"] == 1.5
    assert msg["name"] == ["joint1"]
