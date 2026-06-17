# Phase 9.2 Acceptance

## Statuses

- `PHASE9_2_ACCEPTED`: Isaac smoke, Isaac benchmark, MuJoCo-Isaac cross-backend validation, Phase 9.1 full acceptance, safety pressure, ROS 2, MoveIt 2, and artifact provenance all pass.
- `PHASE9_2_REJECTED`: any runtime artifact is missing, incomplete, stale, forged, or fails validation.
- `BLOCKED_BY_ENV`: only component-level compatibility checks may use this when a required host runtime is genuinely absent.

`BLOCKED_BY_ENV` is not a pass and cannot produce `PHASE9_2_ACCEPTED`.

## Ordinary Environment

```bash
python -m ruff format --check .
python -m ruff check .
python -m mypy .
python -m pytest -q
python scripts/verify_phase9.py
python scripts/verify_phase9_1.py --skip-history
python scripts/verify_phase9_2_environment.py --output artifacts/phase9_2/environment
python scripts/verify_phase9_2_isaac_smoke.py --output artifacts/phase9_2/isaac
python scripts/run_phase9_2_isaac_benchmark.py --output artifacts/phase9_2/isaac_benchmark
python scripts/run_phase9_2_cross_backend.py --output artifacts/phase9_2/cross_backend
python scripts/verify_phase9_2.py --output artifacts/phase9_2/final
```

On a non-Isaac host the expected Phase 9.2 final status is rejected or blocked by component artifacts. The verifier must not claim Isaac runtime validation.

## Compatible Isaac Host

```bash
python scripts/verify_phase9_2_environment.py --output artifacts/phase9_2/environment
python scripts/verify_phase9_2_isaac_smoke.py --output artifacts/phase9_2/isaac
python scripts/run_phase9_2_isaac_benchmark.py --output artifacts/phase9_2/isaac_benchmark
python scripts/run_phase9_2_cross_backend.py --run-experiments --output artifacts/phase9_2/cross_backend
python scripts/verify_phase9_2.py --output artifacts/phase9_2/final
```

The compatible host path must also keep the Phase 9.1 validation chain intact:

```bash
python scripts/verify_phase9.py
source scripts/phase9/activate_ros2_moveit_env.sh
python scripts/verify_phase9_1_ros2_integration.py --output artifacts/phase9_1/ros2
python scripts/verify_phase9_1_moveit_safety.py --output artifacts/phase9_1/moveit
python scripts/verify_phase9_1.py --output artifacts/phase9_1
```

Phase 9.2 success requires `ISAAC_SMOKE_VALIDATED`, `CROSS_BACKEND_VALIDATED`, `PHASE9_1_ACCEPTED`, and `PHASE9_2_ACCEPTED`.
