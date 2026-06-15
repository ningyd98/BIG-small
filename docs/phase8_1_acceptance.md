# Phase 8.1 Acceptance

Phase 8.1 is accepted only when the experiment harness drives the production
control chain and the evidence closes the loop through formal runtime records.

## Required Checks

- Runtime harness integration
- Fault interleaving
- Real `TaskExecutor` path
- Real `SafetyShield` path
- PCSC supervision
- ETEAC event/replan path
- S10 command ingress rejection
- AUTO transition lifecycle
- SQLite crash recovery
- Event-sourced metric recomputation
- Reproducibility
- Phase 8 smoke suite
- Phase 3-8 regression
- Phase 8.1 pytest suite

## Commands Run

```bash
python scripts/run_phase8_experiments.py --suite smoke --seeds 0 --networks NORMAL --output experiments/results/phase8_1_smoke
python scripts/run_phase8_experiments.py --suite full --seeds 0:4 --networks GOOD,DEGRADED,INTERMITTENT --output experiments/results/phase8_1_validation
python scripts/run_phase8_experiments.py --suite full --seeds 0:9 --networks GOOD,NORMAL,DEGRADED,POOR,SEVERE --output experiments/results/phase8_1_full
python scripts/verify_phase8.py
python scripts/verify_phase8_1.py
pytest -q
ruff format --check .
ruff check .
mypy .
pip check
```

## Observed Results

- Smoke: 45 runs, 33 successes
- Validation: 675 runs, 495 successes
- Full benchmark: 2250 runs, 1650 successes

## Evidence Boundary

- Raw `events.jsonl` and `raw_runs.jsonl` are generated but not committed.
- `experiments/baselines/phase8_1/` keeps only small reproducibility artifacts.
- Phase 8.1 still uses mock/simulated components. It does not prove real robot
  safety or real physical performance.
