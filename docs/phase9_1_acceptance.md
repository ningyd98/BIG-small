# Phase 9.1 Acceptance

Phase 9.1 tightens the ROS 2, MoveIt 2, Isaac Sim, and cross-backend verification boundary introduced in Phase 9.

The current host has completed ROS 2 and MoveIt 2 runtime validation, but Phase 9.1 remains accepted only as `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK` because Isaac Sim, Isaac benchmark validation, and cross-backend comparison are still blocked by environment.

## Status Vocabulary

- `PHASE9_1_ACCEPTED`: core Phase 9 checks pass and ROS 2, MoveIt 2, Isaac Sim, Isaac benchmark, and cross-backend validation all run on a compatible host with complete runtime evidence artifacts.
- `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`: core Phase 9 checks pass, but one or more ROS 2, MoveIt 2, or Isaac Sim checks are blocked by host environment.
- `PHASE9_1_REJECTED`: core regression, safety pressure, artifact integrity, or verifier execution fails.

## Required Commands

```bash
scripts/phase9/install_ros2_jazzy.sh --artifact-dir artifacts/phase9_1/install
scripts/phase9/install_vulkan_runtime.sh --artifact-dir artifacts/phase9_1/install
ARTIFACT_DIR=artifacts/phase9_1/install python scripts/phase9/check_isaac_sim.py
python scripts/verify_phase9_1.py
python scripts/verify_phase9_1_ros2_integration.py
python scripts/verify_phase9_1_moveit_safety.py
python scripts/verify_phase9_1_isaac_smoke.py
python scripts/verify_phase9_1_cross_backend.py
```

For CI artifact-shape validation without rerunning Phase 9 history:

```bash
python scripts/verify_phase9_1.py --skip-history
```

## Guardrails

- A blocked ROS 2, MoveIt 2, or Isaac Sim check exits successfully only to indicate the verifier itself worked.
- The artifact must still contain `status=BLOCKED_BY_ENV` and `validation_claimed=false`.
- `ROS2_INTEGRATION_VALIDATED` requires `ros2_runtime_evidence.json` with passed evidence for QoS, namespace, timestamp, action timeout, cancel, and node crash/reconnect.
- `MOVEIT_SAFETY_VALIDATED` requires `moveit_safety_evidence.json` with passed evidence for reachability, joint limits, collision scene, planning failure, execution cancellation, and emergency-stop boundary.
- `ISAAC_SMOKE_VALIDATED` requires `isaac_smoke_evidence.json` proving an independent Isaac process loaded the stage, advanced physics, returned robot state, and produced RGB, depth, and contact sensor samples.
- Software availability alone may only produce `NOT_RUN`, `MOVEIT_READY`, `ISAAC_READY`, or `INCOMPLETE`; it must never set `validation_claimed=true`.
- Every blocked component records the actual commands, exit codes, stdout, and stderr that established the blocker.
- Install readiness is dry-run by default and must record that core Python remains unchanged.
- Independent-process protocol tests may prove JSONL handshake/replay rejection only; they do not prove Isaac validation.
- Isaac backend guards may prove `SimulatorBackend` protocol adaptation over JSONL only; they do not prove Isaac runtime validation.
- Isaac benchmark guards must run the `--backend isaac` entrypoint and must not fall back to MuJoCo when the host is blocked.
- `scripts/phase9/isaac_standalone_app.py --check-imports` must run in the selected Python environment and record whether Isaac runtime imports and `SimulationApp` startup are available.
- ROS 2 interface source guards may prove message/action/service coverage only; they do not prove ROS build or runtime validation.
- ROS 2 bridge source guards may prove rclpy node, action timeout/cancel, feedback stale, reconnect state, and frame-conversion source coverage only; they do not prove ROS runtime validation.
- MoveIt source guards may prove planning-boundary source coverage only; they do not prove MoveIt 2 planning or execution validation.
- Isaac Sim validation requires a real Isaac run count greater than zero before `validation_claimed=true`.
- Cross-backend validation requires real MuJoCo and Isaac artifacts with `backend_name`, `run_id`, `process_provenance`, `validation_claimed=true`, and comparable metrics. `env.level=ISAAC_READY` alone is not sufficient.
- `PHASE9_1_ACCEPTED` also requires a validated Isaac benchmark artifact, completed cross-backend deltas, complete artifact provenance, safety pressure `trial_count>=500`, `illegal_collision_count=0`, `emergency_stop_post_command_count=0`, and non-static result hashes.

## Current Host Result

The current result is:

```text
PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK
```

Blocked components:

- Isaac Sim: `ISAAC_SIM_ROOT` is not set and Vulkan tooling is unavailable.

Validated components:

- ROS 2: `ROS2_INTEGRATION_VALIDATED` with `ros2_runtime_evidence.json`.
- MoveIt 2: `MOVEIT_SAFETY_VALIDATED` with `moveit_safety_evidence.json`.
