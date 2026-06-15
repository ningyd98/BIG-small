# Phase 8.2 Design

Phase 8.2 keeps the system in the mock/virtual experiment scope. It does not add ROS 2, MoveIt 2, or real robot integration.

## Periodic PCSC Closure

PCSC supervision is scheduled on `VirtualClock` using `supervision_period_ms`. The first tick is scheduled after the first period and then reschedules itself while PCSC is active. Because mock robot actions advance the same virtual clock, scheduled ticks interleave with `TaskExecutor` step execution instead of running once before submission.

Each tick reads the current harness state through `RuntimeExperimentHarness._edge_snapshot()`: current step, completed step ids, scene version, target/obstacle state, robot state, and checkpoint-derived completion state. ETEAC never starts this tick loop. AUTO prepares transitions first; PCSC ticks start only for committed PCSC execution and stop when leaving PCSC.

## Fault Detection

Fault injection now records only `fault_injected`. `fault_detected` is emitted by a runtime source:

- `PeriodicSupervisorService` ticks for scene, target, obstacle, network, cloud, and emergency-stop observations.
- `TaskExecutor` result events for failed or paused atomic execution.
- Network monitor callbacks for reconnect and heartbeat delivery.
- Cloud timeout callbacks scheduled on the virtual clock.

Detection latency is computed from `fault_injected_at` to the first later `fault_detected` event for the same fault type.

## Safe-Boundary Mode Switching

AUTO mode no longer commits immediately after prepare. A transition is recorded as prepared and deferred while execution remains in the old mode. After `TaskExecutor` emits a terminal safe boundary (`step_completed`), the pending transition commits. If no safe boundary is reached, the transition aborts and the current mode remains unchanged.

Counters track deferred, aborted, dwell-block, cooldown-block, and switch-limit-block decisions.

## Recovery

S15 covers nine restart points. Each point closes and rebuilds runtime repositories, records recovery, and resumes toward a legal terminal state without repeating completed steps. Recovery payloads include `command_seq`, `plan_version`, and checkpoint progress to guard against rollback.

## Experiment Sensitivity

Network messages are sent through `NetworkSimulator`, so latency, jitter, loss, and reordering affect PCSC command arrival, recovery heartbeat delivery, ETEAC cloud uploads, and replan application timing. Batch summaries include mode x scenario, network x scenario, mode x network, and seed variability views.
