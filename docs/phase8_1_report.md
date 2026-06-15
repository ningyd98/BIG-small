# Phase 8.1 Report

Phase 8.1 replaced the remaining synthetic experiment behavior with a runtime
harness that drives the existing Phase 3-7 chain.

## Implemented

- Real contract submission through `TaskExecutor`
- Real safety checks through `SafetyShield`
- Real command ingress and ACK classification
- Real PCSC supervision ticks
- Real ETEAC retry-budget, failure-summary, replan, and CAS paths
- Real AUTO prepare/commit/abort transitions
- Real SQLite restart recovery for prepared state, checkpoints, and outbox
- Event-sourced metric collection from formal records

## Run Summary

- Smoke: 45 / 33
- Validation: 675 / 495
- Full: 2250 / 1650

## Generated Baseline

- `experiments/baselines/phase8_1/run_manifest.json`
- `experiments/baselines/phase8_1/summary.json`
- `experiments/baselines/phase8_1/summary.csv`
- `experiments/baselines/phase8_1/report.md`
- `experiments/baselines/phase8_1/result_hashes.txt`

## Limits

- This remains a mock/simulation experiment set.
- No real arm, real camera, ROS 2, MoveIt 2, or production LLM was used.
- Simulated zero-collision outcomes are not a hardware safety proof.
- Phase 9 is still required for hardware validation.
