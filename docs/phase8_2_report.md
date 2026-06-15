# Phase 8.2 Report

## Scope

Phase 8.2 stays in the virtual-clock mock experiment environment. It does not include ROS 2, MoveIt 2, real sensors, or real robot hardware.

## Implementation Summary

- PCSC supervision now runs as a periodic virtual-clock loop.
- PCSC ticks interleave with atomic task steps and observe dynamic scene/network state.
- Fault injection no longer records detection directly.
- Fault detection latency is computed from real detection events.
- AUTO mode transitions are prepared/deferred and committed only after a step safe boundary.
- S15 restart recovery covers nine crash points.
- Experiment summaries include mode, network, scenario, and seed sensitivity views.

## Data

The Phase 8.2 baseline artifacts are written to `experiments/baselines/phase8_2/`.

Executed suites:

- Smoke: 45 runs, 33 successful tasks.
- Validation: 675 runs, 495 successful tasks.
- Full benchmark: 2250 runs, 1650 successful tasks.

The report should be read with:

- `summary.csv` for per-run metrics.
- `summary.json` for grouped metrics and validity guards.
- `report.md` for generated experiment notes.
- `events.jsonl` for tick, detection, recovery, transition, and crash-point timelines.

## Timing Evidence

Representative PCSC target-moved run:

- Step starts: `step-home` at 0 ms, `step-move-above` at 100 ms, `step-approach` at 200 ms, `step-grasp` at 300 ms, `step-lift` at 400 ms, `step-move-region` at 500 ms.
- PCSC ticks: 301 ms, 601 ms, 901 ms.
- Fault injected: `TARGET_MOVED` at 700 ms.
- Fault detected: `TARGET_MOVED` at 901 ms by `PeriodicSupervisorService`.
- Detection latency: 201 ms.

S15 recovery covered all nine crash points and completed with `SUCCESS`; repeated completed step count was 0.

## Full Benchmark Sensitivity

Mode cloud invocation means:

- AUTO: 0.0
- ETEAC: 0.0667
- PCSC: 2.8667

Network completion-time means:

- GOOD: 1539.4 ms
- NORMAL: 1576.96 ms
- DEGRADED: 1649.18 ms
- POOR: 1733.64 ms
- SEVERE: 1889.2 ms

Seed variability did not change mean completion time in the full aggregate, but it changed network-sensitive metrics. Mean communication bytes ranged from 143.90 to 195.38 across seeds; mean recovery latency ranged from 605.98 ms to 657.03 ms.

The full benchmark `validity_guard` passed all checks: modes, networks, and seeds were not identical; fault detection latency was not all zero; PCSC included multi-tick tasks.

## Supported Assumptions

- PCSC dynamic supervision produces multiple ticks and observes post-injection scene state.
- PCSC and ETEAC differ in cloud invocation mechanism.
- Network profile changes affect completion/recovery/communication metrics.
- Different seeds produce reproducible differences in network-sensitive metrics.
- Multi-crash restart recovery can reach a legal terminal state without repeating completed steps.

## Unsupported Assumptions

- Aggregate completion time did not vary by seed in this benchmark; seed effects were visible in communication and recovery metrics instead.
- No real hardware safety or performance claim is supported by Phase 8.2 data.
