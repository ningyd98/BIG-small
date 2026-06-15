# Phase 8 Metrics

All durations use milliseconds. Metrics are grouped as observed values, derived
values, summary statistics, and counterfactual values.

## Observed

- `task_success`, `task_completion_time_ms`, completed/failed step counts,
  retry count, first-attempt success.
- `cloud_invocation_count`, supervisory decisions, replans, commands,
  telemetry count, uploaded/downloaded bytes.
- fault detection, cloud response, and recovery latency.
- safety allow, allow-with-limits, pause, reject, emergency-stop, stale,
  duplicate, reordered, collision, and counterfactual counts.
- initial/final mode, switch counts, dwell/cooldown/switch-limit blocks, and
  time in PCSC/ETEAC.
- cache hit, miss, promotion, quarantine, invalidation, trusted-template
  execution.

## Derived

- Success rate is successes divided by total runs. Failed runs remain in the
  denominator.
- Repeated completed step count is total completed-step records minus unique
  completed-step ids.
- Result hash is computed from normalized result content with wall-clock and
  self-hash fields removed.

## Statistics

`MetricSummary` provides count, mean, standard deviation, median, p95, min, max,
success rate, and confidence interval. Success-rate intervals use Wilson 95%.
Continuous bootstrap intervals use a deterministic seed.

## Missing Values

Missing latency values are serialized as null and are not silently treated as
zero. Zero-sample groups produce `sample_count=0`.
