# AUTO Mode Selection

AUTO is not a third execution engine. It only chooses between existing modes:

- `PERIODIC_CLOUD_SUPERVISION`
- `EVENT_TRIGGERED_EDGE_AUTONOMY`

AUTO may also keep the current mode, request more observation, pause, or safe stop. It cannot bypass `TaskContract`, `ContractValidator`, `SafetyShield`, `TaskExecutor`, checkpoint recovery, CAS, idempotency, or completion evidence.

## Decision Inputs

`AutoModeSelector` uses current mode state, active contract completeness, checkpoint persistence, `RiskSnapshot`, skill-cache lookup result, event-autonomy readiness, supervision availability, atomic-step state, and switch history.

## Selection Rules

Event autonomy is eligible only when risk is LOW or allowed MEDIUM, the scene is stable, the contract and checkpoint are complete, edge readiness is true, cache is trusted or not required, perception is fresh, and no high-risk event is pending.

Periodic supervision is preferred when cloud supervision is available, scene dynamics benefit from cloud observation, and risk has not crossed pause/stop thresholds.

Pause or safe stop wins for CRITICAL risk, safety reject/emergency stop, missing safety evidence, incomplete contract/checkpoint, stale scene, or cloud unavailable while edge autonomy is not ready.

## Anti-Flapping

The selector enforces minimum dwell time, switch cooldown, maximum switches per task, atomic-step safe boundaries, and immediate escalation for CRITICAL risk.
