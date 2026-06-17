# Phase 6.2 报告

## 概要

Phase 6.2 的最终验收收紧了事件触发自治闭环：

- 按既定基线恢复 Phase 6.2 的 replan apply、merge、contract context 和 SQLite 持久化路径。
- 新增 `scripts/verify_phase6_2.py`。
- active contract、event、failure summary 或 checkpoint 缺失时，重规划必须 fail-closed。
- 过期 replan apply 返回 `VERSION_CONFLICT`。
- 禁止 replacement step 复用已完成 `step_id`，也禁止合并后的 step ID 重复。
- completion summary 改为每个任务确定性生成，重复证据返回原 summary，不再创建第二条记录。
- 生产配置拒绝 mock、fake、in-memory、test-double 值，也拒绝在生产 `TaskExecutor` 中使用 mock safety provider。
- 从生产路径移除 stub `pass`、placeholder 标记和 request-ID task 推导。
- Phase 6.2 replanning response、merge、apply、ack 和 rejection 时间都走可注入 clock。

## 验证快照

最终运行结果：

```text
git diff --check -> exit 0
ruff format --check . -> 171 files already formatted
ruff check . -> All checks passed!
mypy . -> Success: no issues found in 171 source files
pytest -q -> 291 passed in 0.53s
verify_phase3.py -> success=true
verify_phase3_1.py -> success=true
verify_phase3_2.py -> success=true
verify_phase4.py -> success=true, 7/7 passed
verify_phase5.py -> success=true, 7/7 checks passed
verify_phase6.py -> success=true, 25/25 checks passed
verify_phase6_2.py -> 8/8 checks passed, success=true
```

命令日志保存在 `artifacts/phase6_2/`。最终日志使用 `complete-*` 前缀。

## SQLite 重启结果

`verify_phase6_2.py` 会打开 SQLite repository，通过 `TaskExecutor` 跑一次真实边缘失败，持久化 checkpoint、event、`FailureSummary` 和 replan request；随后关闭 repository，重新打开同一数据库，通过 `LocalReplanningService` 与 `ReplanApplyService` 应用云端重规划；再关闭并重开，从持久化 checkpoint 恢复执行。

观测结果：

- `APPROACH` 在失败前执行一次，重启后没有重复执行。
- `GRASP` 在重规划前失败两次，随后在新 contract 下执行一次。
- `LIFT`、`MOVE_TO_REGION`、`PLACE`、`RELEASE` 和 `VERIFY_RESULT` 完成。
- completion summary 结果为 `SUCCESS_WITH_RECOVERY`。

## CAS 与幂等结果

验收覆盖：

- 两个 replan 基于同一个旧版本时，第一个 apply 成功，第二个返回 `VERSION_CONFLICT`。
- 旧 `command_seq` 不能覆盖 active contract。
- 同一 replan idempotency key 和同一 payload 返回原 request。
- 同一 key 搭配不同 payload 会抛出 `IdempotencyConflictError`。
- 重复 completion evidence 只存储一条 completion summary。

## 剩余技术债

以下内容有意不放进 Phase 6.2：

- Phase 7 skill cache。
- AUTO mode selection。
- 双模式自动切换。
- risk scheduler。
- 面向 CI 的真实机械臂、telemetry、scene provider 集成。
- CI 中执行生产 LLM replanner。

只有当 Phase 6.2 final gate 在 `origin/main` 上通过，并且工作区保持干净后，项目才进入 Phase 7。
