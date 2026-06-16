# Phase 9.1 Acceptance

Phase 9.1 tightens the ROS 2, MoveIt 2, Isaac Sim, and cross-backend verification boundary introduced in Phase 9.

The current host is accepted only for core MuJoCo readiness. ROS 2, MoveIt 2, and Isaac Sim validation remain blocked by environment and must not be reported as completed.

## Status Vocabulary

- `PHASE9_1_ACCEPTED`: core Phase 9 checks pass and ROS 2, MoveIt 2, Isaac Sim, and cross-backend validation all run on a compatible host.
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
- Every blocked component records the actual commands, exit codes, stdout, and stderr that established the blocker.
- Install readiness is dry-run by default and must record that core Python remains unchanged.
- Independent-process protocol tests may prove JSONL handshake/replay rejection only; they do not prove Isaac validation.
- `scripts/phase9/isaac_standalone_app.py --check-imports` must run in the selected Python environment and record whether Isaac runtime imports and `SimulationApp` startup are available.
- ROS 2 interface source guards may prove message/action/service coverage only; they do not prove ROS build or runtime validation.
- ROS 2 bridge source guards may prove rclpy node, action timeout/cancel, feedback stale, reconnect state, and frame-conversion source coverage only; they do not prove ROS runtime validation.
- Isaac Sim validation requires a real Isaac run count greater than zero before `validation_claimed=true`.
- Cross-backend validation remains `NOT_RUN_BLOCKED_BY_ENV` unless Isaac Sim is available.

## Current Host Result

The current result is:

```text
PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK
```

Blocked components:

- ROS 2: ROS 2 CLI, Jazzy environment, `rclpy`, `colcon`, and `rosdep` are unavailable.
- MoveIt 2: MoveIt 2 packages and the built `bigsmall_franka_moveit_config` workspace are unavailable.
- Isaac Sim: `ISAAC_SIM_ROOT` is not set and Vulkan tooling is unavailable.
