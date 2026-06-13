# Contract Models

## Required Phase 0 Models

- `TaskContract`
- `Telemetry`
- `CloudCommand`
- `CommandAck`
- `EdgeEvent`
- `FailureSummary`
- `RobotState`
- `ActionResult`
- `Pose`

All traceable messages include `task_id`, `plan_version`, `command_seq`, and timezone-aware `timestamp`.

## JSON Schema

Schemas are generated from Pydantic with `model_json_schema()`. The acceptance tests verify that each required model exports an object schema with declared properties.

## Examples

Contract examples live under:

- `contracts/examples/valid`
- `contracts/examples/invalid`

Validate them with:

```bash
python scripts/validate_contract_examples.py
```

The validator accepts valid examples through `TaskContract` and `EdgeContractValidator`, and confirms invalid examples are rejected by schema or edge validation.
