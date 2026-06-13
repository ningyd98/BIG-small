# Phase 2 验收说明

## 验收覆盖

- 所有合法状态转换测试；
- 所有非法状态转换测试；
- 完整合法任务测试；
- 非法契约零动作测试；
- 步骤失败短路测试；
- 重试预算测试；
- 步骤超时测试；
- 任务超时测试；
- 指令防重放测试；
- 重启后防重放测试；
- 相同序号不同负载冲突测试；
- 崩溃恢复测试；
- 审计日志完整性测试；
- InMemory 与 SQLite repository 一致性测试。

## 阶段边界

Phase 2 不包含：

- MQTT；
- FastAPI 云端任务接口；
- 云端规划；
- 大模型调用；
- 周期云端监督；
- 事件触发云端重规划；
- 完整边缘安全盾；
- 真实机械臂 SDK。

## 本地验收命令

```bash
ruff check .
mypy .
pytest -q
python scripts/validate_contract_examples.py
python scripts/run_phase2_task.py --repository sqlite
python scripts/run_phase2_failure_case.py --fault GRASP_FAILED
python scripts/run_phase2_replay_test.py
python scripts/run_phase2_restart_recovery_test.py
python scripts/verify_phase2.py
```

## 脚本输出期望

- `run_phase2_task.py --repository sqlite`：任务状态 `COMPLETED`，目标区域 `bin_a`。
- `run_phase2_failure_case.py --fault GRASP_FAILED`：任务失败，`failed_step_id=step-grasp`。
- `run_phase2_replay_test.py`：首次成功，重复指令 `COMMAND_SEQ_REPLAYED`，同序号不同负载
  `COMMAND_SEQ_CONFLICT`。
- `run_phase2_restart_recovery_test.py`：中断任务恢复为 `PAUSED`，最后审计事件
  `RUNTIME_RECOVERY_REQUIRED`。
