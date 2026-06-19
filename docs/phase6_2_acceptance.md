# Phase 6.2 验收

只有以下命令全部通过，Phase 6.2 才能接受：

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
git diff --check
.venv/bin/python -m ruff format --check .
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy .
.venv/bin/python -m pytest -q
.venv/bin/python scripts/verify_phase3.py
.venv/bin/python scripts/verify_phase3_1.py
.venv/bin/python scripts/verify_phase3_2.py
.venv/bin/python scripts/verify_phase4.py
.venv/bin/python scripts/verify_phase5.py
.venv/bin/python scripts/verify_phase6.py
.venv/bin/python scripts/verify_phase6_2.py
```

`scripts/verify_phase6_2.py` 必须验证以下内容：

- replanning context 从持久化 repository 读取。
- 已完成步骤不能被修改，也不能被重复。
- CAS 拒绝过期 plan version 和过期 command sequence。
- SQLite restart 能恢复 active contract、checkpoint、event、summary、replan result 和 completion summary。
- `TaskExecutor` 从 checkpoint 恢复，且不会重新执行已完成步骤。
- checkpoint、event、failure summary 或 active contract 缺失时必须 fail-closed。
- `task_id`、`robot_id` 和 `plan_id` 不匹配时必须拒绝。
- 幂等冲突必须显式报出。
- 重复 completion evidence 不会创建两条 summary。
- completion evidence 在 scene data 过期、criteria 缺失、completed step 不一致、安全决策被拒绝、robot state 无效或 target state 未满足时必须 fail-closed。
- Phase 5 验证仍然通过。
- 生产配置拒绝 mock、fake、in-memory、test-double 值。
- 生产源码不能有 stub success path 或 placeholder implementation。

`InMemory` 只允许用于测试和仿真。restart 验收路径必须使用 SQLite。

Phase 7 不在本阶段范围内。
