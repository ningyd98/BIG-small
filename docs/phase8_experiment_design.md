# Phase 8 Experiment Design

Phase 8 adds a deterministic, seed-controlled experiment framework for PCSC,
ETEAC, and AUTO. AUTO remains a selector over PCSC and ETEAC, not a third
executor.

## Questions

- Compare task success, virtual duration, cloud calls, and communication cost
  under network profiles.
- Compare fault detection and recovery for target movement, obstacle insertion,
  grasp failure, target loss, perception degradation, outages, cloud failure,
  command ordering faults, cache states, oscillation pressure, emergency stop,
  and SQLite restart.
- Test whether AUTO chooses PCSC or ETEAC from risk, network, scene, and cache
  signals.
- Measure Skill Cache reuse and quarantine behavior.
- Verify reproducibility for same config and seed.

## Variables

- Independent variables: scenario id, mode, seed, named network profile, cache
  policy, ablation list, supervision period, and timeout.
- Dependent variables: success, completion time, retries, replans, safety
  decisions, cloud calls, bytes, mode switches, cache counters, recovery latency,
  invariant violations, and reproducibility hashes.
- Controlled variables: Mock robot abstraction, high-level skill set, safety
  policy, task profile, and deterministic virtual time.

## Scenarios

The registry contains S01 through S15 with initial conditions, scheduled faults,
invariants, allowed results, forbidden results, and max virtual duration.

## Network Model

Profiles are GOOD, NORMAL, DEGRADED, POOR, SEVERE, and INTERMITTENT. The
simulator supports latency, jitter, loss, duplication, reordering, outage,
cloud availability, and byte accounting. Random choices use the experiment
seed.

## Ablations

A1-A7 are recorded in config/result metadata. Safety ablation is shadow-only:
the formal execution never bypasses SafetyShield.
