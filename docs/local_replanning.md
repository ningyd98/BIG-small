# 局部重规划

Phase 6.1 的局部重规划把边缘端已持久化的失败信息交给确定性或显式配置的云端重规划 adapter。

## 请求生命周期

本地恢复无法继续后，边缘端创建 `LocalReplanningRequest`。请求会先持久化并放入事件 outbox，然后执行等待云端更新。

`LocalReplanningService.process` 的处理顺序是：

1. 通过 repository 结果存储做幂等查询。
2. 查询事件。
3. 查询失败摘要。
4. 配置了 provider 时，查询当前契约。
5. 校验 task、robot、plan、command 和 scene 身份。
6. 调用 adapter。
7. 做 schema 和语义校验。
8. 校验已完成步骤不可变。
9. 注入可信版本和命令序号。
10. 使用 CAS 更新计划版本。
11. 持久化结果。
12. 可选地通过 outbox 风格回调分发。

## CAS 行为

repository 方法 `advance_plan_version_if_current` 会拒绝过期或并发的计划版本更新。测试覆盖了成功升级和旧结果拒绝两种情况。

验证来源：

- `scripts/verify_phase6.py` 第 17、19、20 项检查。
- `tests/test_phase6_e2e_executor.py::test_replan_cas_rejects_old_result`。

## Adapter

- `MockReplannerAdapter`：测试和 CI 使用的确定性 adapter，支持注入时钟。
- `RuleBasedReplannerAdapter`：从失败步骤和契约推导失败技能，不硬编码 GRASP。
- `OpenAICompatibleReplannerAdapter`：必须显式配置 endpoint 和 API key；配置缺失时立即失败。

如果生产环境选择 OpenAI-compatible 路径，必须明确配置外部 adapter。

## Fail-Closed 行为

adapter 失败或校验失败都不会更新 active plan。API 响应不暴露完整内部 traceback；服务结果只返回受控的 outcome 和 reason 字段。
