# Phase 9.1 Acceptance

Phase 9.1 tightens the ROS 2, MoveIt 2, Isaac Sim, and cross-backend verification boundary introduced in Phase 9.

The current host is accepted only for core MuJoCo readiness. ROS 2, MoveIt 2, and Isaac Sim validation remain blocked by environment and must not be reported as completed.

## Status Vocabulary

- `PHASE9_1_ACCEPTED`: core Phase 9 checks pass and ROS 2, MoveIt 2, Isaac Sim, and cross-backend validation all run on a compatible host.
- `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`: core Phase 9 checks pass, but one or more ROS 2, MoveIt 2, or Isaac Sim checks are blocked by host environment.
- `PHASE9_1_REJECTED`: core regression, safety pressure, artifact integrity, or verifier execution fails.

## Required Commands

```bash
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
