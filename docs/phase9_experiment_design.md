# Phase 9 Experiment Design

Suites:

- `phase9_smoke`: 18 MuJoCo runs.
- `phase9_validation_mujoco`: 2250 MuJoCo runs.
- `phase9_full_mujoco`: 11250 MuJoCo runs.
- Isaac suites: generated as `BLOCKED_BY_ENV` unless `ISAAC_READY`.

Artifacts are written under `experiments/baselines/phase9/` and include manifest, environment, config, randomization, events, raw runs, summary CSV/JSON, result hashes, and report.
