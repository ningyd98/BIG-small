# 测试说明

仓库使用单元测试、E2E 测试、验收脚本、静态检查和 CI。测试结论只对它覆盖的范围负责，不能用软件测试结果替代真实硬件验收。

## 本地质量门

本地建议跑和 CI 接近的命令：

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
python -m compileall src scripts tests
python -m ruff format --check .
python -m ruff check .
python -m mypy src/
python -m pytest -q
python scripts/verify_phase3.py
python scripts/verify_phase3_1.py
python scripts/verify_phase3_2.py
python scripts/verify_phase4.py
python scripts/verify_phase5.py
python scripts/verify_phase6.py
python -m pip check
```

如果只改某个阶段，可以先跑对应阶段测试；合并前仍要说明哪些命令已跑、哪些没跑。

## Phase 6.1 重点测试

关键行为覆盖如下：

- `tests/test_phase6_e2e_executor.py::test_task_executor_event_mode_retries_failed_step_before_next_step`：同一步重试和动作顺序。
- `tests/test_phase6_e2e_executor.py::test_e2e_budget_exhaustion_creates_replan_request`：恢复预算耗尽后创建重规划请求。
- `tests/test_phase6_e2e_executor.py::test_replan_cas_rejects_old_result`：旧重规划结果会被拒绝。
- `tests/test_phase6_e2e_executor.py::test_sqlite_restart_preserves_state`：SQLite 重启后保留预算和状态。
- `tests/test_phase6_e2e_executor.py::test_sqlite_outbox_retry_wait_survives_restart_and_reclaims`：SQLite outbox 重试状态可跨重启恢复。
- `tests/test_phase6_e2e_executor.py::test_completion_evaluator_blocks_success_on_failure`：失败证据不能被判成成功。

`tests/test_phase6_recovery_replanning.py` 覆盖重试预算、恢复决策、失败摘要、已完成步骤保护和重规划服务。

`tests/test_phase6_integration.py` 覆盖 API 和 repository 的集成行为。

## CI

`.github/workflows/ci.yml` 在推送和 PR 时运行。它安装开发依赖后执行编译、格式、lint、mypy、pytest、Phase 3-6 验证脚本和 `pip check`。

## 报告规则

只要本地质量门中有命令失败，就不要声明对应阶段完成。如果没有查看 GitHub Actions 状态，只能报告“本地通过，远端未验证”。
