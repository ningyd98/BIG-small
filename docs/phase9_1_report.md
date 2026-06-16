# Phase 9.1 Report

Phase 9.1 adds explicit environment-blocked verification for ROS 2, MoveIt 2, Isaac Sim, and cross-backend validation. It does not claim real hardware validation, and it does not claim Isaac Sim validation on this host.

## Current Result

- Status: `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`
- Core Phase 9 history: passed through `scripts/verify_phase9.py`
- Safety pressure: 100 MuJoCo near-miss trials, 0 illegal collisions
- Cross-backend: MuJoCo reference generated; Isaac comparison not run because Isaac is blocked by environment
- Install readiness: dry-run plans generated for ROS 2 Jazzy, MoveIt 2, Vulkan, and Isaac compatibility without modifying the core Python environment
- Isaac process protocol guard: JSONL handshake, command acknowledgement, movement skill trajectory mapping, and replay-runtime rejection pass in a subprocess fixture; this is not counted as Isaac validation
- Isaac standalone app entrypoint: `scripts/phase9/isaac_standalone_app.py` exists for the official Isaac Python runtime and is checked by the Isaac smoke verifier; current host reports blocked because Isaac Python modules are unavailable
- ROS 2 interface guard: `bigsmall_interfaces` defines Phase 9.1 message, service, and action sources with timestamps and command identity; this is not counted as ROS 2 runtime validation

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
- `artifacts/phase9_1/process_protocol/process_protocol_guard.json`
- `artifacts/phase9_1/ros_interfaces/ros_interface_guard.json`
- `artifacts/phase9_1/install/install_readiness.json`
- `artifacts/phase9_1/install/install_plan.json`
- `artifacts/phase9_1/install/vulkan_install_plan.json`
- `artifacts/phase9_1/install/isaac_compatibility_report.json`

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
