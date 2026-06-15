# Phase 8 Acceptance

Acceptance command:

```bash
python scripts/verify_phase8.py
```

The verifier executes:

- Phase 8 imports.
- Virtual clock determinism.
- Network fault injection.
- PCSC, ETEAC, and AUTO smoke runs.
- Target moved and network outage scenarios.
- Stale/duplicate/reordered command scenario.
- Skill Cache ablation scenario.
- Emergency stop scenario.
- SQLite restart scenario.
- Reproducibility comparison.
- Artifact integrity checks.
- Full suite startup check.
- `pytest tests/test_phase8_*.py -q`.
- Phase 3 through Phase 7 verification scripts.

Failure exits non-zero and prints the failed check name and error summary.

Observed during implementation:

- `python scripts/verify_phase8.py` passed all 16 checks.
- `python scripts/run_phase8_experiments.py --suite smoke --output /tmp/... --seeds 0 --networks NORMAL`
  produced `run_count=21` and `success_count=18`.
- `python scripts/run_phase8_experiments.py --suite full --output /tmp/... --seeds 0:0 --networks GOOD`
  started successfully and produced `run_count=45` and `success_count=36`.
