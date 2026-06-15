# Phase 8 Report

Phase 8 implements a reproducible simulation experiment framework for comparing
PCSC, ETEAC, and AUTO across deterministic scenarios, network profiles, seeds,
cache policies, and ablations.

## Implemented

- Strong experiment models and schema version `phase8.v1`.
- Deterministic virtual clock and seed-driven network simulator.
- Fifteen scenario definitions S01-S15.
- Unified runner for PCSC, ETEAC, and AUTO, with AUTO selecting only PCSC or
  ETEAC.
- Skill Cache, RiskEvaluator, and ModeTransitionService integration at the
  experiment boundary.
- SQLite restart smoke recovery for auto-mode and event-autonomy repositories.
- Metrics, summary statistics, reproducibility hash, artifact writer, batch
  runner, CLI, and verifier.
- Smoke matrix and full-suite start check were executed successfully.

## Executed Samples

- Smoke sample: 21 runs, 18 successes.
- Full-suite startup sample: 45 runs, 36 successes.

## Limits

This is a Mock/simulation experiment. It does not prove real hardware safety or
performance. Network and physical behavior are engineering abstractions. Phase 9
requires real hardware validation.
