# Phase 8.1 Baseline Report

This baseline summarizes the Phase 8.1 runtime-harness experiment run. It stores only small reproducibility artifacts; raw `raw_runs.jsonl` and `events.jsonl` files are intentionally excluded from version control.

## Executed Suites

| Suite | Runs | Successes | Success Rate |
| --- | ---: | ---: | ---: |
| smoke | 45 | 33 | 0.733333 |
| validation | 675 | 495 | 0.733333 |
| full | 2250 | 1650 | 0.733333 |

## Full Benchmark Scope

- Scenarios: S01-S15
- Modes: PCSC, ETEAC, AUTO
- Networks: GOOD, NORMAL, DEGRADED, POOR, SEVERE
- Seeds: 0 through 9
- Total runs: 2250

## Evidence Boundary

Phase 8.1 drives the production-style mock runtime chain through `RuntimeExperimentHarness`: contract validation, SafetyShield, TaskExecutor, MockRobotAdapter, command ACK classification, PCSC supervision, ETEAC replan/CAS paths, mode transition lifecycle, and restart recovery. Metrics are derived from structured runtime events and repositories.

These are Mock/simulation experiments. They do not represent real robot performance, real camera performance, ROS 2/MoveIt 2 integration, or production LLM behavior. Simulated zero-collision outcomes are not a proof of physical hardware safety. Phase 9 remains required for hardware validation.
