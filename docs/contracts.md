# 契约模型

## Phase 0 必需模型

- `TaskContract`
- `Telemetry`
- `CloudCommand`
- `CommandAck`
- `EdgeEvent`
- `FailureSummary`
- `RobotState`
- `ActionResult`
- `Pose`

所有可追踪消息都包含 `task_id`、`plan_version`、`command_seq` 和带时区的 `timestamp`。

## JSON Schema

Schema 由 Pydantic 的 `model_json_schema()` 生成。验收测试会确认每个必需模型都导出对象 schema，并声明属性。

## 示例

契约示例位于：

- `contracts/examples/valid`
- `contracts/examples/invalid`

验证示例：

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
python scripts/validate_contract_examples.py
```

验证器通过 `TaskContract` 和 `EdgeContractValidator` 接受有效示例，并确认无效示例会被 schema 或边缘校验拒绝。
