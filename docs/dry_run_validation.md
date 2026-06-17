# Dry-Run Validation

Dry-run validation exercises the software safety chain without sending hardware
commands:

```text
TaskContract -> EdgeContractValidator -> SafetyShield -> trajectory summary
```

The output status is `DRY_RUN_VALIDATED` when the contract and safety checks
pass. The hardware execution status remains `PLANNED_ONLY`, and
`hardware_motion_observed=false` is written to evidence.

Dry-run evidence is useful for site preparation and regression testing. It is
not read-only hardware validation and it is not physical task validation.
