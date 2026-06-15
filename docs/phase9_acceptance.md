# Phase 9 Acceptance

Core acceptance commands:

```bash
python -m compileall src scripts tests
python -m ruff format --check .
python -m ruff check .
python -m mypy .
python -m pytest -q
python scripts/verify_phase8_2.py
python scripts/verify_phase9.py
python -m pip check
```

Current status is expected to be `PHASE9_CORE_ACCEPTED + ISAAC_VALIDATION_BLOCKED_BY_ENV` on hosts without ROS 2 Jazzy / MoveIt 2 / Isaac Sim.
