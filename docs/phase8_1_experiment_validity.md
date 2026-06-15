# Phase 8.1 Experiment Validity

## What Phase 8 Meant

Phase 8 proved that the experiment framework was deterministic and reproducible.
It did not yet guarantee that the runner was exercising the production runtime
chain end to end.

## What Phase 8.1 Adds

- Faults are interleaved with real atomic execution.
- Step completion comes from `TaskExecutor`, checkpoints, and completion
  evidence.
- Safety results come from `SafetyShield`, not runner-side counters.
- Command rejection comes from real ACK records.
- Cloud invocation counts come from real supervisor and replanning events.
- AUTO mode changes use persisted prepare/commit/abort transitions.
- Restart checks rebuild repositories and services instead of reusing objects.

## What Is Not Claimed

- No claim that AUTO is always better than PCSC or ETEAC.
- No claim that simulated zero collisions imply real hardware safety.
- No claim that mock network behavior matches production networks exactly.
- No claim that Phase 8.1 replaces Phase 9 hardware validation.

## Reproduction

```bash
python scripts/run_phase8_experiments.py --suite smoke --seeds 0 --networks NORMAL --output experiments/results/phase8_1_smoke
python scripts/run_phase8_experiments.py --suite full --seeds 0:4 --networks GOOD,DEGRADED,INTERMITTENT --output experiments/results/phase8_1_validation
python scripts/run_phase8_experiments.py --suite full --seeds 0:9 --networks GOOD,NORMAL,DEGRADED,POOR,SEVERE --output experiments/results/phase8_1_full
python scripts/verify_phase8_1.py
```

## Evidence Rules

- Do not silently exclude failures.
- Do not infer success from fixed counters.
- Do not compare results using wall-clock time.
- Use config hash, git SHA, seed, and event hashes for reproducibility checks.
