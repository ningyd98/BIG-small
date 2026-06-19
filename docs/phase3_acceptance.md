# Phase 3 验收说明

## 验收覆盖

- StopController 真实停机语义（stop + emergency_stop 回退）
- MockRobotAdapter auto_connect=False 默认值
- TaskExecutor 执行前验证机器人已连接
- 22 条安全规则全部实现
- 约束合并策略（min 策略）
- 安全参数绕过检测
- Watchdog 超时检测
- 安全配置加载
- 安全审计事件完整记录
- InMemory 和 SQLite 安全记录一致性
- 正常任务不误拒绝
- 危险任务 100% 被拒绝或安全停止

## 阶段边界

Phase 3 不包含：
- MQTT
- FastAPI 云端任务接口
- 云端规划
- 大模型调用
- 周期云端监督
- 事件触发云端重规划
- 真实机械臂 SDK

## 本地验收命令

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
ruff format --check .
ruff check .
mypy .
pytest -q
python scripts/run_phase3_safe_task.py
python scripts/run_phase3_workspace_violation.py
python scripts/run_phase3_velocity_limit.py
python scripts/run_phase3_collision_case.py
python scripts/run_phase3_obstacle_case.py
python scripts/run_phase3_stale_scene_case.py
python scripts/run_phase3_watchdog_timeout.py
python scripts/verify_phase3.py
./scripts/run_checks.sh
```

## 验收标准

- 所有危险测试必须 100% 被拒绝或安全停止
- 碰撞和急停必须实际调用 emergency_stop
- SAFETY_STOPPED 必须与机器人实际状态一致
- 正常任务测试不得误拒绝
- 安全盾不得 fail-open
- pytest 至少 80 项通过
- GitHub Actions 通过
