# Phase 9 Metrics

Phase 9 adds physical execution, perception, simulation performance, and cloud-edge recovery metrics. Provenance is recorded by `simulation.evaluation.provenance.metric_provenance`.

Examples:

- `joint_tracking_rmse`: physics state
- `illegal_collision_count`: MuJoCo contacts
- `sensor_latency_ms`: sensor frame
- `fault_detection_latency_ms`: audit event
- `cloud_invocation_count`: network/supervision event

Metrics are simulation/readiness metrics only and are not real robot safety or performance claims.
