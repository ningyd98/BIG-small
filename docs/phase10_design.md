# Phase 10 Design

Phase 10 adds the safety boundary required before connecting a physical robot.
It does not execute a real robot task by default and does not claim real robot
validation.

## Architecture

The control chain remains:

```text
TaskContract -> EdgeContractValidator -> SafetyShield -> planner summary
  -> HardwareExecutionGate -> RealRobotAdapter
```

Cloud services still emit high-level task contracts and supervisory decisions.
The edge runtime owns the final decision to execute or reject every hardware
action.

## Status Target

The ordinary host target is `PHASE10_DRY_RUN_ACCEPTED`. That means the real
robot configuration model, execution gate, dry-run path, acceptance-level
framework, audit evidence, and documentation are ready. It does not mean any
physical arm moved.

## Implementation Boundary

- `cloud_edge_robot_arm.real_robot.config` owns real device configuration and
  execution mode validation.
- `cloud_edge_robot_arm.real_robot.gate` owns fail-closed motion authorization.
- `cloud_edge_robot_arm.real_robot.dry_run` validates contracts without sending
  commands to hardware.
- `cloud_edge_robot_arm.real_robot.acceptance` persists the highest physical
  acceptance level.
- `cloud_edge_robot_arm.real_robot.adapter` provides read-only adapter
  contracts and an environment-blocked implementation.

Real hardware execution stays disabled unless a site-specific configuration,
operator confirmation, fresh telemetry, healthy controller, inactive emergency
stop, healthy SafetyShield, and sufficient acceptance level are all present.
