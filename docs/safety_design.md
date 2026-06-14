# Safety design

Safety is enforced at the edge before and after robot action execution.

## SafetyShield

`SafetyShield` evaluates a `SafetyContext` using deterministic rules. Rules include command freshness, telemetry freshness, scene freshness, scene version, device connection, emergency stop, collision, workspace, forbidden zones, reachability, velocity, acceleration, minimum height, obstacle/path/carry safety, step timeout, task deadline, and watchdog checks.

## Runtime integration

`TaskExecutor` requires a `SafetyShield` instance. `SafetySkillExecutor` builds `SafetyContext` from:

- the validated `TaskContract`;
- current robot state;
- latest telemetry provider sample;
- latest scene provider snapshot;
- skill-specific resolved intent;
- configured hard and operational safety limits.

For motion skills, the same resolved target and limited parameters are used for the safety check and robot action.

## Event-mode retries

Local recovery retries do not bypass safety. A `RETRY_STEP` result causes the same task step to execute again through `SafetySkillExecutor`, so telemetry, scene, context construction, pre-check, action execution, and post-check all run again.

Verified by:

- `scripts/verify_phase6.py` check 6.
- `tests/test_phase6_e2e_executor.py::test_task_executor_event_mode_retries_failed_step_before_next_step`.

## Completion safety

`CompletionEvaluator` requires a final allowed safety decision and safe robot state. A completed step list alone does not create a success result.

## Fail-closed behavior

Missing telemetry or scene timestamps can pause execution. Emergency stop and collision conditions produce safety-stop behavior. Validation failures and unhandled completion criteria block success.
