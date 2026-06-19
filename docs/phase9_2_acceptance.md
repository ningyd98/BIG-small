# Phase 9.2 验收

## 状态

- `PHASE9_2_ACCEPTED`：Isaac smoke、Isaac benchmark、MuJoCo-Isaac 跨后端验证、Phase 9.1 完整验收、安全压力、ROS 2、MoveIt 2 和 artifact 溯源全部通过。
- `PHASE9_2_REJECTED`：任一 runtime artifact 缺失、不完整、过期、伪造或校验失败。
- `BLOCKED_BY_ENV`：仅组件级兼容性检查可以在确实缺少主机 runtime 时使用。

`BLOCKED_BY_ENV` 不是通过状态，也不能产生 `PHASE9_2_ACCEPTED`。

## 普通环境

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
python -m ruff format --check .
python -m ruff check .
python -m mypy .
python -m pytest -q
python scripts/verify_phase9.py
python scripts/verify_phase9_1.py --skip-history
python scripts/verify_phase9_2_environment.py --output artifacts/phase9_2/environment
python scripts/verify_phase9_2_isaac_smoke.py --output artifacts/phase9_2/isaac
python scripts/run_phase9_2_isaac_benchmark.py --output artifacts/phase9_2/isaac_benchmark
python scripts/run_phase9_2_cross_backend.py --output artifacts/phase9_2/cross_backend
python scripts/verify_phase9_2.py --output artifacts/phase9_2/final
```

在非 Isaac 主机上，Phase 9.2 最终状态应为 rejected，或由组件 artifact 标明受环境阻塞。verifier 不得声称已经完成 Isaac runtime 验证。

## 兼容 Isaac 主机

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
python scripts/verify_phase9_2_environment.py --output artifacts/phase9_2/environment
python scripts/verify_phase9_2_isaac_smoke.py --output artifacts/phase9_2/isaac
python scripts/run_phase9_2_isaac_benchmark.py --output artifacts/phase9_2/isaac_benchmark
python scripts/run_phase9_2_cross_backend.py --run-experiments --output artifacts/phase9_2/cross_backend
python scripts/verify_phase9_2.py --output artifacts/phase9_2/final
```

兼容主机路径还必须保持 Phase 9.1 验证链完整：

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
python scripts/verify_phase9.py
source scripts/phase9/activate_ros2_moveit_env.sh
python scripts/verify_phase9_1_ros2_integration.py --output artifacts/phase9_1/ros2
python scripts/verify_phase9_1_moveit_safety.py --output artifacts/phase9_1/moveit
python scripts/verify_phase9_1.py --output artifacts/phase9_1
```

Phase 9.2 通过要求同时满足 `ISAAC_SMOKE_VALIDATED`、`CROSS_BACKEND_VALIDATED`、`PHASE9_1_ACCEPTED` 和 `PHASE9_2_ACCEPTED`。
