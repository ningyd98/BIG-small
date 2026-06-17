# Phase 9.2 Report

## Current Host Result

The current host result is `PHASE9_2_ACCEPTED`.

- Vulkan tooling is available through the user conda environment.
- A local Isaac venv is auto-detected at `$HOME/.venvs/bigsmall-isaacsim-6.0.0.1`.
- The Phase 9.2 checker invokes `$HOME/.venvs/bigsmall-isaacsim-6.0.0.1/bin/python`.
- Isaac Sim 6.0 `SimulationApp` starts headless and loads a local MJCF Panda/Franka stage.
- The smoke run advances physics, samples robot state, RGB, depth, and contact sensor data, executes reset and emergency stop, and shuts down cleanly.
- The Isaac benchmark runs 6 representative Phase 9.2 scenarios.
- The paired MuJoCo-Isaac comparison runs 6 scenarios across 5 seeds each, for 30 paired runs.

The existing authoritative completed state remains:

- ROS 2: `ROS2_INTEGRATION_VALIDATED`
- MoveIt 2: `MOVEIT_SAFETY_VALIDATED`
- Phase 9 MuJoCo core: passed
- Phase 9.1 source aggregate: `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`
- Phase 9.2 final aggregate: `PHASE9_2_ACCEPTED`

## Phase 9.2 Evidence

- Compatibility report under `artifacts/phase9_2/environment`.
- Isaac smoke evidence under `artifacts/phase9_2/isaac`.
- Isaac benchmark summary and runs under `artifacts/phase9_2/isaac_benchmark`.
- Cross-backend paired artifacts under `artifacts/phase9_2/cross_backend`.
- Final aggregate summary under `artifacts/phase9_2/final`.
- `isaac_runtime` pytest marker for real Isaac-only tests.

## Accepted Runtime States

- `ISAAC_SMOKE_VALIDATED`
- `CROSS_BACKEND_VALIDATED`
- `PHASE9_1_ACCEPTED`
- `PHASE9_2_ACCEPTED`

No real robot validation has been started.
