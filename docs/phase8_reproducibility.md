# Phase 8 Reproducibility

Run a smoke suite:

```bash
python scripts/run_phase8_experiments.py --suite smoke --output experiments/results/smoke
```

Run the full suite:

```bash
python scripts/run_phase8_experiments.py --suite full --seeds 0:9 --output experiments/results/full
```

The normalized config hash ignores artifact directory paths and includes mode,
scenario, seed, network, cache policy, risk policy, timeout, and ablations.

Seed propagation covers network jitter/loss/duplication/reordering, scenario
fault ordering, simulated retries, and deterministic result hashes. Wall-clock
timestamps are not part of reproducibility comparisons.

Each run writes `run_manifest.json`, `raw_runs.jsonl`, `events.jsonl`,
`summary.csv`, `summary.json`, and `report.md`.
