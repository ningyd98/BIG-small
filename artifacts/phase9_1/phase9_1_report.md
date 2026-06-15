# Phase 9.1 Verification Report

Status: `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`

## Components

- `ros2`: `BLOCKED_BY_ENV`, validation_claimed=False
  blockers: ROS_DISTRO is not jazzy, ros2 CLI is not available, rclpy is not importable in this Python environment, colcon is not available, rosdep is not available
- `moveit`: `BLOCKED_BY_ENV`, validation_claimed=False
  blockers: ros2 CLI is not available, MoveIt 2 planning interface package is not available, MoveIt 2 OMPL planner package is not available, bigsmall_franka_moveit_config is not built in a sourced ROS workspace
- `isaac`: `BLOCKED_BY_ENV`, validation_claimed=False
  blockers: ISAAC_SIM_ROOT is not set, vulkaninfo is not available or Vulkan runtime is not usable

## Time Domains

- `simulation_time`
- `ros_time`
- `wall_clock_time`
- `sensor_timestamp`

## Cross Backend

- status: `BLOCKED_BY_ENV`
- Isaac comparison: `NOT_RUN_BLOCKED_BY_ENV`

This report does not claim real Isaac Sim, ROS 2, MoveIt 2, or hardware validation when a component is blocked by environment.
