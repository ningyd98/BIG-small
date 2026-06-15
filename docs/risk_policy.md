# Risk Policy

Phase 7 risk evaluation is deterministic and rule-based. It does not use black-box machine learning.

`RiskPolicy` is versioned and defines component weights, LOW/MEDIUM/HIGH/CRITICAL thresholds, staleness thresholds, missing-input penalty, scene movement penalty, and cache miss penalties.

## Components

Risk snapshots normalize these components to 0-100:

- `task_risk`: skill, task type, contract completeness, persisted remaining steps, edge capability.
- `scene_dynamics_risk`: target movement, obstacle count/change rate, scene freshness, scene confidence.
- `perception_risk`: scene confidence, target confidence, target lost.
- `network_risk`: latency, jitter, packet loss, disconnection duration, heartbeat freshness, cloud availability.
- `execution_risk`: failures, timeouts, replans, cache confidence/miss, safety rejection history.
- `safety_risk`: recent `SafetyShield` decision, safety rejections, pause/reject/emergency stop.

## Fail-Closed Rules

Missing critical inputs never produce LOW risk. The evaluator raises total risk to the configured missing-input penalty and returns `INSUFFICIENT_EVIDENCE`.

Safety risk is not averaged away. `EMERGENCY_STOP` hard-overrides all components and returns `CRITICAL` with score 100.

Every `RiskSnapshot` records component scores, total score, risk level, freshness, missing inputs, reason codes, policy version, timestamps, and deterministic input hash.
