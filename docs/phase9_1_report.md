# Phase 9.1 Report

Phase 9.1 adds explicit environment-blocked verification for ROS 2, MoveIt 2, Isaac Sim, and cross-backend validation. It does not claim real hardware validation, and it does not claim Isaac Sim validation on this host.

## Current Result

- Status: `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`
- Core Phase 9 history: passed through `scripts/verify_phase9.py`
- Safety pressure: 100 MuJoCo near-miss trials, 0 illegal collisions
- Cross-backend: MuJoCo reference generated; Isaac comparison not run because Isaac is blocked by environment

## Environment Blockers

- ROS 2: `ros2` CLI unavailable, `ROS_DISTRO` is not `jazzy`, `rclpy` unavailable, `colcon` unavailable, `rosdep` unavailable.
- MoveIt 2: `moveit_ros_planning_interface`, `moveit_planners_ompl`, and `bigsmall_franka_moveit_config` are not available from a sourced ROS workspace.
- Isaac Sim: `ISAAC_SIM_ROOT` is unset and `vulkaninfo` is unavailable.

## Evidence Artifacts

- `artifacts/phase9_1/phase9_1_summary.json`
- `artifacts/phase9_1/phase9_1_report.md`
- `artifacts/phase9_1/ros2/ros2_verification.json`
- `artifacts/phase9_1/moveit/moveit_verification.json`
- `artifacts/phase9_1/isaac/isaac_verification.json`
- `artifacts/phase9_1/cross_backend/cross_backend_verification.json`
- `artifacts/phase9_1/safety_pressure/safety_pressure.json`

## Time Domains

Phase 9.1 artifacts explicitly distinguish:

- `simulation_time`
- `ros_time`
- `wall_clock_time`
- `sensor_timestamp`

## Compatible Host Rerun

On a host with ROS 2 Jazzy, MoveIt 2 Jazzy, Isaac Sim, Vulkan, and a configured `ISAAC_SIM_ROOT`, rerun:

```bash
python scripts/verify_phase9_1.py --output artifacts/phase9_1
```

The result may only become `PHASE9_1_ACCEPTED` if the component verifiers actually run and write `validation_claimed=true`.
