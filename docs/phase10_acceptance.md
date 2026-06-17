# Phase 10 Acceptance

Allowed final statuses:

- `PHASE10_IMPLEMENTATION_READY_ENV_BLOCKED`
- `PHASE10_DRY_RUN_ACCEPTED`
- `PHASE10_HARDWARE_READ_ONLY_ACCEPTED`
- `PHASE10_LOW_SPEED_MOTION_ACCEPTED`
- `PHASE10_REAL_TASK_ACCEPTED`

Without authoritative real hardware evidence, the verifier must not output
`PHASE10_REAL_TASK_ACCEPTED`.

## Ordinary Verification

```bash
python -m ruff format --check .
python -m ruff check .
python -m mypy .
python -m pytest -q
python scripts/verify_phase9.py
python scripts/verify_phase9_1.py --skip-history
python scripts/verify_phase9_2.py --output artifacts/phase9_2/final
python scripts/verify_phase10_0.py
python scripts/verify_phase10_1.py
```

Expected current-host result: `PHASE10_DRY_RUN_ACCEPTED`.

## Hardware Verification

Hardware verification is manual and level-gated:

```bash
python scripts/run_phase10_acceptance_level.py --level LEVEL_0 --output artifacts/phase10/acceptance
```

Only one level may be requested per command. A site operator must confirm the
workspace, emergency stop, and physical isolation before any motion level.
