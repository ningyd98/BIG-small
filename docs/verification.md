# Verification Guide

BIG-small separates CI-safe checks, environment-specific runtime checks, and real-hardware-only procedures.

## CI-safe

```bash
python -m compileall src scripts tests
python -m ruff format --check .
python -m ruff check .
python -m mypy .
python -m pytest -q
python scripts/check_docs.py
python scripts/verify_project.py --profile ci
```

CI-safe commands must not connect to Isaac runtime, ROS 2 / MoveIt runtime, or a real robot controller.

## Simulation

```bash
python scripts/verify_phase9.py
python scripts/verify_phase9_2.py --output artifacts/phase9_2/final
```

These commands validate simulation and accepted artifacts. They do not imply real hardware validation.

## ROS 2 / MoveIt

```bash
source scripts/phase9/activate_ros2_moveit_env.sh
python scripts/verify_phase9_1.py --skip-history
python scripts/verify_phase10_moveit_dry_run.py --output artifacts/phase10/moveit_dry_run
```

MoveIt Runtime Dry-Run produces planning-only evidence. It does not call MoveIt execute and does not require a real controller.

## Isaac

```bash
python scripts/verify_phase9_2_environment.py --output artifacts/phase9_2/environment
python scripts/verify_phase9_2_isaac_smoke.py --output artifacts/phase9_2/isaac
python scripts/run_phase9_2_cross_backend.py --output artifacts/phase9_2/cross_backend --run-experiments
```

These commands require a compatible Isaac Sim environment.

## Phase 10 Software Safety

```bash
python scripts/verify_phase10_0.py
python scripts/verify_phase10_1.py
python scripts/verify_phase10_2a.py --skip-runtime
```

`--skip-runtime` is CI-safe and records MoveIt runtime dry-run as environment-blocked. It does not change the formal runtime accepted rule.

## Real-hardware-only

```bash
python scripts/run_phase10_acceptance_level.py --level LEVEL_0
```

Run real-hardware-only commands only at a controlled site with operator approval. Do not run Level 1-6 motion tests automatically.
