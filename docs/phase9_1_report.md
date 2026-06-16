# Phase 9.1 Report

Phase 9.1 adds explicit verification for ROS 2, MoveIt 2, Isaac Sim, and cross-backend validation. It does not claim real hardware validation, and it does not claim Isaac Sim validation on this host.

## Current Result

- Status: `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`
- Core Phase 9 history: passed through `scripts/verify_phase9.py`
- Safety pressure: 500 MuJoCo near-miss trials, 0 illegal collisions
- Safety pressure now derives `emergency_stop_post_command_count` from command records and reports `unique_result_hash_count`; it is not a fixed zero.
- ROS 2 runtime evidence: `ROS2_INTEGRATION_VALIDATED`
- MoveIt 2 runtime evidence: `MOVEIT_SAFETY_VALIDATED`
- Cross-backend: MuJoCo reference generated; Isaac comparison not run because Isaac is blocked by environment
- Real robot validation: not started
- Install readiness: dry-run plans generated for ROS 2 Jazzy, MoveIt 2, Vulkan, and Isaac compatibility without modifying the core Python environment
- Isaac process protocol guard: JSONL handshake, command acknowledgement, movement skill trajectory mapping, and replay-runtime rejection pass in a subprocess fixture; this is not counted as Isaac validation
- Isaac backend guard: `IsaacSimBackend` implements the shared `SimulatorBackend` protocol over an external JSONL process and refuses missing telemetry; this is not counted as Isaac runtime validation
- Isaac benchmark guard: `scripts/run_phase9_benchmarks.py --backend isaac --suite smoke` is exercised and records `BLOCKED_BY_ENV` on this host instead of falling back to MuJoCo; this is not counted as Isaac runtime validation
- Isaac standalone app entrypoint: `scripts/phase9/isaac_standalone_app.py` exists for the official Isaac Python runtime and is checked by the Isaac smoke verifier; current host reports blocked because Isaac Python modules are unavailable
- ROS 2 interface guard: `bigsmall_interfaces` defines Phase 9.1 message, service, and action sources with timestamps and command identity; this is not counted as ROS 2 runtime validation
- ROS 2 bridge source guard: `bigsmall_sim_bridge` now includes an rclpy node with explicit QoS, `/clock`, simulation status, fault/safety publishers, command identity, duplicate rejection, action timeout/cancel handling, feedback stale accounting, reconnect state, and frame-conversion time-domain envelopes; this is not counted as ROS 2 runtime validation
- MoveIt source guard: `bigsmall_robot_bridge` now includes a MoveIt boundary node that checks reachability, joint limits, collision-scene update, planning failure, execution cancellation, emergency-stop boundary, and delegates trajectories through BIG-small execution instead of direct MoveIt execution; this is not counted as MoveIt 2 runtime validation

## Phase 9.1.1 Runtime Hardening

- Aggregate acceptance no longer lets Isaac `BLOCKED_BY_ENV` mask ROS 2 or MoveIt evidence gaps. When those runtimes are available, `READY`, `INCOMPLETE`, `FAILED`, or unknown statuses reject the aggregate result.
- MoveIt collision evidence now records a no-obstacle baseline plan, inserted collision object, PlanningScene read-back object, replanning/rejection result, trajectory delta, MoveIt error code, process provenance, and clean log integrity.
- PlanningScene confirmation accepts MoveIt's normalized read-back form only when object ID, dimensions, and effective position match the requested collision object.
- Planning timeout evidence now first proves the same target succeeds under a normal planning budget, then records short-budget wall-clock timing and either standard `TIMED_OUT` or the audited RoboStack `TIME_BUDGET_EXHAUSTED` fallback.
- ROS 2 and MoveIt runtime logs are checked for `Traceback`, `Segmentation fault`, `RCLError`, and `process exited unexpectedly`; non-whitelisted markers make evidence incomplete.
- BIG-small boundary shutdown now rejects new goals, stops active motion, stops the executor, destroys node resources, terminates subprocesses from the runner, and only then calls `rclpy.shutdown()`.

## Environment Blockers

- Isaac Sim: `ISAAC_SIM_ROOT` is unset and `vulkaninfo` is unavailable.
- Cross-backend: blocked because no real Isaac runtime artifact is available on this host.

## Evidence Artifacts

- `artifacts/phase9_1/phase9_1_summary.json`
- `artifacts/phase9_1/phase9_1_report.md`
- `artifacts/phase9_1/ros2/ros2_verification.json`
- `artifacts/phase9_1/moveit/moveit_verification.json`
- `artifacts/phase9_1/isaac/isaac_verification.json`
- `artifacts/phase9_1/cross_backend/cross_backend_verification.json`
- `artifacts/phase9_1/cross_backend/mujoco_reference_artifact.json`
- `artifacts/phase9_1/safety_pressure/safety_pressure.json`
- `artifacts/phase9_1/process_protocol/process_protocol_guard.json`
- `artifacts/phase9_1/isaac_backend/isaac_backend_guard.json`
- `artifacts/phase9_1/isaac_benchmark/isaac_benchmark_guard.json`
- `artifacts/phase9_1/ros_interfaces/ros_interface_guard.json`
- `artifacts/phase9_1/ros_bridge_sources/ros_bridge_source_guard.json`
- `artifacts/phase9_1/moveit_sources/moveit_source_guard.json`
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
python -m ruff format --check .
python -m ruff check .
python -m mypy .
python -m pytest -q
python scripts/verify_phase9.py
source scripts/phase9/activate_ros2_moveit_env.sh
python scripts/verify_phase9_1_ros2_integration.py --output artifacts/phase9_1/ros2
python scripts/verify_phase9_1_moveit_safety.py --output artifacts/phase9_1/moveit
python scripts/verify_phase9_1.py --output artifacts/phase9_1
```

The result may only become `PHASE9_1_ACCEPTED` if the component verifiers actually run and write `validation_claimed=true`.

Environment readiness is not runtime validation. A future compatible host must provide:

- `ros2_runtime_evidence.json` for QoS, namespace, timestamp, action timeout, cancel, and reconnect checks.
- `moveit_safety_evidence.json` for reachability, joint limits, collision scene, planning failure, cancellation, and emergency-stop boundary checks.
- `isaac_smoke_evidence.json` with process provenance, stage load, physics steps, robot state, and RGB/depth/contact samples.
- Real MuJoCo and Isaac cross-backend artifacts with backend names, run ids, process provenance, `validation_claimed=true`, and computed metric deltas.
- A real Isaac benchmark artifact; the current blocked smoke entrypoint is not sufficient.

MoveIt remains planning-only in the BIG-small architecture. Runtime trajectory execution is still delegated through the edge safety boundary rather than direct MoveIt execution.
