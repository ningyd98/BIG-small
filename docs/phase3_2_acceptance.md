# Phase 3.2 验收说明

## 验收覆盖

- TaskExecutor shield 参数为 SafetyShield 类型（非 Any）；构造时类型检查
- TelemetryProvider / SceneStateProvider 替代伪造时间戳
- SkillSafetyIntentResolver 解析真实目标位姿
- 运动目标单真源（安全盾和执行使用相同位姿）
- ALLOW_WITH_LIMITS 真实限幅参数
- Velocity/Accel 真实值传递到 SafetyContext
- Post-check 状态映射（PAUSE → PAUSED）
- 安全审计事件完整记录
- 集成脚本通过 TaskExecutor（无手动 SafetyContext）

## 验收命令

```bash
ruff format --check .
ruff check .
mypy .
pytest -q
python scripts/verify_phase3.py
python scripts/verify_phase3_1.py
python scripts/verify_phase3_2.py
```

## 验收标准

- shield 参数类型检查通过
- 伪造时间戳完全移除（无 `or datetime.now(UTC)` fallback）
- 目标位姿解析器覆盖所有运动技能
- 集成脚本无手动 SafetyContext 构造
- ALLOW_WITH_LIMITS 产生限幅参数且原始值不送达机器人
- pytest ≥ 119 项通过
