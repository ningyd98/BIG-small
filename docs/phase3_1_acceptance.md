# Phase 3.1 验收说明

## 验收覆盖

- SafetyShield 强制注入 TaskExecutor
- SafetySkillExecutor pre_check/post_check 集成
- SafetyContextBuilder 从真实运行时构造上下文
- 21 条安全规则全部使用 merged constraints
- fail-closed：缺失 telemetry/scene/watchdog/step_start 均拒绝
- PathCollision 真实三维线段-球体检测
- Acceleration 真实加速度检查
- CarrySafety 真实扩大安全余量
- MinimumHeight 低高度例外需 scene 新鲜
- WorkspaceRule 检查 current_pose + target_pose
- StopController 两种停机失败 → FAILED（非 SAFETY_STOPPED）
- 17 项集成测试全部通过
- 5 个集成验证脚本全部通过

## 本地验收命令

```bash
ruff format --check .
ruff check .
mypy .
pytest -q
python scripts/run_phase3_integrated_safe_task.py
python scripts/run_phase3_integrated_workspace_reject.py
python scripts/run_phase3_integrated_path_collision.py
python scripts/run_phase3_integrated_pause.py
python scripts/run_phase3_integrated_emergency_stop.py
python scripts/verify_phase3.py
python scripts/verify_phase3_1.py
./scripts/run_checks.sh
```

## 验收标准

- SafetyShield 已注入 TaskExecutor（构造函数必需参数）
- 所有动作经过 pre_check
- 所有成功动作经过 post_check
- 危险目标零机器人动作
- 路径碰撞被真实阻断
- 缺失安全信息 fail closed
- 正常 10 步任务无误拒绝
- SAFETY_STOPPED 与真实停止状态一致
- pytest 至少 100 项通过
