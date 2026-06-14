# Phase 6.2 Acceptance

Phase 6.2 is accepted only when the following commands pass:

```bash
git diff --check
.venv/bin/python -m ruff format --check .
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy .
.venv/bin/python -m pytest -q
.venv/bin/python scripts/verify_phase3.py
.venv/bin/python scripts/verify_phase3_1.py
.venv/bin/python scripts/verify_phase3_2.py
.venv/bin/python scripts/verify_phase4.py
.venv/bin/python scripts/verify_phase5.py
.venv/bin/python scripts/verify_phase6.py
.venv/bin/python scripts/verify_phase6_2.py
```

`scripts/verify_phase6_2.py` must verify:

- Replanning context is loaded from the persistent repository.
- Completed steps cannot be modified or duplicated.
- CAS rejects stale plan versions and stale command sequences.
- SQLite restart restores active contract, checkpoint, event, summary, replan
  result, and completion summary.
- `TaskExecutor` resumes from the checkpoint and does not re-run completed
  steps.
- Missing checkpoint, event, failure summary, or active contract fails closed.
- `task_id`, `robot_id`, and `plan_id` mismatches are rejected.
- Idempotency conflict is explicit.
- Duplicate completion evidence does not create two summaries.
- Completion evidence fails closed for stale scene data, missing criteria,
  inconsistent completed steps, rejected safety decisions, invalid robot state,
  and unmet target state.
- Phase 5 verification still passes.
- Production configuration rejects mock/fake/in-memory/test-double values.
- Production source has no stub success path or placeholder implementation.

InMemory is allowed only for tests and simulation. SQLite is required for the
restart acceptance path.

Phase 7 remains out of scope.
