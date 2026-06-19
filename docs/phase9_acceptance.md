# Phase 9 验收

核心验收命令：

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
python -m compileall src scripts tests
python -m ruff format --check .
python -m ruff check .
python -m mypy .
python -m pytest -q
python scripts/verify_phase8_2.py
python scripts/verify_phase9.py
python -m pip check
```

在没有 ROS 2 Jazzy / MoveIt 2 / Isaac Sim 的主机上，当前预期状态是 `PHASE9_CORE_ACCEPTED + ISAAC_VALIDATION_BLOCKED_BY_ENV`。
