# JSON Schema

Phase 0 JSON Schema 直接由 Pydantic model 的 `model_json_schema()` 导出。

主要 schema 入口：

- `TaskContract.model_json_schema()`
- `Telemetry.model_json_schema()`
- `CloudCommand.model_json_schema()`
- `CommandAck.model_json_schema()`
- `EdgeEvent.model_json_schema()`
- `FailureSummary.model_json_schema()`
- `RobotState.model_json_schema()`
- `ActionResult.model_json_schema()`
- `Pose.model_json_schema()`

自动化测试会断言这些 schema 导出；示例 validator 会用 runtime model 校验 JSON payload。
