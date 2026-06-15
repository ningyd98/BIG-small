# Phase 9 ROS 2 and MoveIt 2

Phase 9 defines explicit ROS names and QoS profiles in `simulation.ros2`. Sensor streams use best-effort semantics; commands and emergency stop use reliable semantics.

MoveIt 2 remains a planning boundary only. `command_requires_safety_approval("follow_joint_trajectory")` documents and tests that trajectories must pass through BIG-small safety approval before execution.

On this host ROS validation is `BLOCKED_BY_ENV` because `rclpy`, ROS 2 Jazzy, `colcon`, `rosdep`, and MoveIt 2 are not available.
