# Dry-Run Validation

Phase 10.2A-R does not add a new dry-run class. It documents and checks the
existing separation between Synthetic Dry-Run and MoveIt Runtime Dry-Run.

Dry-run validation exercises the software safety chain without sending hardware
commands:

```text
TaskContract -> EdgeContractValidator -> SafetyShield -> dry-run planner
```

The output status is `DRY_RUN_VALIDATED` when the contract and safety checks
pass. The hardware execution status remains `PLANNED_ONLY`, and
`hardware_motion_observed=false` is written to evidence.

There are two dry-run levels:

- Synthetic dry-run: `planner_backend=SYNTHETIC`,
  `moveit_runtime_used=false`, and `collision_validation_claimed=false`.
- MoveIt dry-run: `planner_backend=MOVEIT_RUNTIME`,
  `moveit_runtime_used=true`, and a real MoveIt planning service produced the
  trajectory summary.

Neither dry-run level connects to a real controller. MoveIt dry-run proves
planner availability only; it is not read-only hardware validation and it is not
physical task validation.
