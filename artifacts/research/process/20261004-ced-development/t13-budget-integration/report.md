# T13 retry budget integration — software subcomponent

Four RED regressions reproduced initialization resetting consumed retry quotas and absolute deadlines, and a task/contract mismatch. RetryBudgetService.initialize now validates the contract/task and calls the existing repository atomic initialize-if-absent API. An existing row is returned exactly; a new event or process cannot replenish the pool. The repository producer separately covers in-memory locks and SQLite two-connection atomic insertion.

Fresh standalone command `.venv/bin/python -m pytest -q tests/test_verified_recovery_lifecycle.py`: 4 passed, exit 0. The previous 67-test related run and the newer 18-test reproduction/budget run overlap; they are not independent counts. Ruff and mypy passed for the consumer. The simultaneous activation implementation introduced a circular annotation import, which its owner fixed; the standalone process now imports cleanly. Producer evidence is ../t13-activation/budget-green.log (nine overlapping tests).

This verifies initialization, not the complete verified recovery lifecycle or any physical recovery. LOCAL_RECOVER remains disabled and G4 is NOT_RUN. The original pending.md and failures are retained as history; this report supersedes that pending status only for initialization.
