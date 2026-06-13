# JSON Schema

Phase 0 JSON Schema is exported directly from the Pydantic models using `model_json_schema()`.

Primary schema entry points:

- `TaskContract.model_json_schema()`
- `Telemetry.model_json_schema()`
- `CloudCommand.model_json_schema()`
- `CommandAck.model_json_schema()`
- `EdgeEvent.model_json_schema()`
- `FailureSummary.model_json_schema()`
- `RobotState.model_json_schema()`
- `ActionResult.model_json_schema()`
- `Pose.model_json_schema()`

The automated tests assert these schema exports and the example validator checks JSON payloads against the runtime models.
