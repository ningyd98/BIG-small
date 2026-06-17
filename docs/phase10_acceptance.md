# Phase 10 验收说明

仓库治理状态 `PHASE10_2A_REPOSITORY_DOCUMENTATION_ACCEPTED` 只表示文档、验证入口、CI 检查和仓库结构一致。它不改变运行时验收状态。

允许出现的最终状态如下：

- `PHASE10_IMPLEMENTATION_READY_ENV_BLOCKED`
- `PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED`
- `PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED_WITH_MOVEIT_ENV_BLOCK`
- `PHASE10_MOVEIT_DRY_RUN_ACCEPTED`
- `PHASE10_HARDWARE_READ_ONLY_ACCEPTED`
- `PHASE10_LOW_SPEED_MOTION_ACCEPTED`
- `PHASE10_REAL_TASK_ACCEPTED`

没有权威真实硬件证据时，验证器不得输出 `PHASE10_REAL_TASK_ACCEPTED`。

## 常规验证

```bash
python -m ruff format --check .
python -m ruff check .
python -m mypy .
python -m pytest -q
python scripts/verify_phase9.py
python scripts/verify_phase9_1.py --skip-history
python scripts/verify_phase9_2.py --output artifacts/phase9_2/final
python scripts/verify_phase10_0.py
python scripts/verify_phase10_1.py
python scripts/verify_phase10_2a.py --skip-runtime
python scripts/verify_phase10_moveit_dry_run.py --output artifacts/phase10/moveit_dry_run
```

当前主机如果具备 ROS 2 / MoveIt 环境，预期软件侧结果是 `PHASE10_MOVEIT_DRY_RUN_ACCEPTED`。如果 MoveIt 不可用，预期结果是 `PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED_WITH_MOVEIT_ENV_BLOCK`。

## 真实硬件验证

真实硬件验证必须人工触发，并且按级别推进：

```bash
python scripts/run_phase10_acceptance_level.py --level LEVEL_0 --output artifacts/phase10/acceptance
```

每条命令只能请求一个级别。进入任何运动级别前，现场操作员必须确认工作空间、急停和物理隔离条件。
