# 验证说明

BIG-small 把验证分成三类：CI 可运行检查、依赖特定环境的运行时检查，以及只能在真实硬件现场执行的流程。不要把前两类结果写成真实机械臂验收。

## CI 可运行

```bash
python -m compileall src scripts tests
python -m ruff format --check .
python -m ruff check .
python -m mypy .
python -m pytest -q
python scripts/check_docs.py
python scripts/verify_project.py --profile ci
```

这些命令不得连接 Isaac runtime、ROS 2 / MoveIt runtime 或真实机器人控制器。

## 仿真验证

```bash
python scripts/verify_phase9.py
python scripts/verify_phase9_2.py --output artifacts/phase9_2/final
```

这些命令验证仿真能力和已接受的 artifact，不代表真实硬件验证。

## ROS 2 / MoveIt

```bash
source scripts/phase9/activate_ros2_moveit_env.sh
python scripts/verify_phase9_1.py --skip-history
python scripts/verify_phase10_moveit_dry_run.py --output artifacts/phase10/moveit_dry_run
```

MoveIt Runtime Dry-Run 只产生规划证据，不调用 MoveIt execute，也不需要真实控制器。

## Isaac

```bash
python scripts/verify_phase9_2_environment.py --output artifacts/phase9_2/environment
python scripts/verify_phase9_2_isaac_smoke.py --output artifacts/phase9_2/isaac
python scripts/run_phase9_2_cross_backend.py --output artifacts/phase9_2/cross_backend --run-experiments
```

这些命令需要匹配的 Isaac Sim 环境。环境不满足时，应记录阻塞原因，不应伪造运行证据。

## Phase 10 软件安全门

```bash
python scripts/verify_phase10_0.py
python scripts/verify_phase10_1.py
python scripts/verify_phase10_2a.py --skip-runtime
```

`--skip-runtime` 可以在 CI 中使用，会把 MoveIt runtime dry-run 记为环境阻塞。它不改变正式 runtime 验收规则。

## 真实硬件现场

```bash
python scripts/run_phase10_acceptance_level.py --level LEVEL_0
```

真实硬件命令只能在受控现场、操作员批准后运行。Level 1-6 涉及运动测试，不能由 CI 或统一脚本自动触发。
