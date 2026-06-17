# Phase 9.2 Report

## Current Host Result

The repository now contains Phase 9.2 verification code and artifact contracts for Isaac Sim 6.0 smoke validation and MuJoCo-Isaac paired comparison.

Current host result is not `PHASE9_2_ACCEPTED` because Isaac Sim 6.0 is not configured on this machine:

- `ISAAC_SIM_ROOT` is not set.
- `ISAAC_RUNTIME_MODE=container` is not configured.
- Vulkan tooling may be unavailable.
- No real Isaac smoke artifact exists yet.
- No real Isaac paired-run artifact exists yet.

The existing authoritative completed state remains:

- ROS 2: `ROS2_INTEGRATION_VALIDATED`
- MoveIt 2: `MOVEIT_SAFETY_VALIDATED`
- Phase 9 MuJoCo core: passed
- Phase 9.1: `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`

## Implemented Phase 9.2 Evidence Contracts

- Compatibility report under `artifacts/phase9_2/environment`.
- Isaac smoke verifier under `artifacts/phase9_2/isaac`.
- Cross-backend verifier under `artifacts/phase9_2/cross_backend`.
- Final aggregate summary under `artifacts/phase9_2/final`.
- `isaac_runtime` pytest marker for real Isaac-only tests.

## Remaining Work On Compatible Host

On a host with Isaac Sim 6.0, run the environment checker, real smoke, paired experiments, and final aggregate. Only that host can produce:

- `ISAAC_SMOKE_VALIDATED`
- `CROSS_BACKEND_VALIDATED`
- `PHASE9_1_ACCEPTED`
- `PHASE9_2_ACCEPTED`

No real robot validation has been started.
