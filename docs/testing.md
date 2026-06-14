# Testing

The repository uses unit tests, E2E tests, acceptance scripts, static checks, and CI.

## Local quality gate

Use the same commands as CI:

```bash
python -m compileall src scripts tests
python -m ruff format --check .
python -m ruff check .
python -m mypy src/
python -m pytest -q
python scripts/verify_phase3.py
python scripts/verify_phase3_1.py
python scripts/verify_phase3_2.py
python scripts/verify_phase4.py
python scripts/verify_phase5.py
python scripts/verify_phase6.py
python -m pip check
```

## Phase 6.1 tests

Key behavioral coverage:

- `tests/test_phase6_e2e_executor.py::test_task_executor_event_mode_retries_failed_step_before_next_step` verifies same-step retry and action order.
- `tests/test_phase6_e2e_executor.py::test_e2e_budget_exhaustion_creates_replan_request` verifies budget exhaustion and replan request persistence.
- `tests/test_phase6_e2e_executor.py::test_replan_cas_rejects_old_result` verifies old result rejection.
- `tests/test_phase6_e2e_executor.py::test_sqlite_restart_preserves_state` verifies SQLite restart recovery for budget and state.
- `tests/test_phase6_e2e_executor.py::test_sqlite_outbox_retry_wait_survives_restart_and_reclaims` verifies SQLite outbox retry persistence.
- `tests/test_phase6_e2e_executor.py::test_completion_evaluator_blocks_success_on_failure` verifies completion criteria negative behavior.

`tests/test_phase6_recovery_replanning.py` covers retry budget, recovery decisions, summaries, completed-step protection, and replanning adapters/services.

`tests/test_phase6_integration.py` covers integration-level API and repository behavior.

## CI

`.github/workflows/ci.yml` runs on `push` and `pull_request` to `main`. It installs the project with development dependencies and runs compile, formatting, lint, mypy, pytest, Phase 3-6 verification scripts, and `pip check`.

## Reporting rule

Do not claim a phase is complete if any local quality-gate command fails. If GitHub Actions status is not observed, report local pass and remote status as unverified.
