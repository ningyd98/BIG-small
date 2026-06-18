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
python scripts/verify_phase11_simulation_workbench.py --skip-e2e
python scripts/verify_phase11_1_simulation_runtime.py --ci
```

这些命令不得连接 Isaac runtime、ROS 2 / MoveIt runtime 或真实机器人控制器。Phase 11 的 `--skip-e2e` 模式是 CI 轻量检查，只输出 partial verification，不声明完整验收。

## 仿真验证

```bash
python scripts/verify_phase9.py
python scripts/verify_phase9_2.py --output artifacts/phase9_2/final
```

这些命令验证仿真能力和已接受的 artifact，不代表真实硬件验证。

## Phase 11 Simulation Workbench

```bash
cd dashboard
npm ci
npm run api:check
npm run format:check
npm run lint
npm run typecheck
npm run test
npm run build
npm run e2e
cd ..
python scripts/verify_phase11_simulation_workbench.py
```

完整 Phase 11 verifier 会运行后端测试、前端检查、Playwright E2E，并写入 `artifacts/phase11/verification/`。它使用真实 FastAPI Dashboard API，但不接触真实机械臂。

## Phase 11.1 Simulation Runtime

```bash
python scripts/verify_phase11_1_simulation_runtime.py --ci
python scripts/verify_phase11_1_simulation_runtime.py --mujoco
python scripts/verify_phase11_1_simulation_runtime.py --full
```

`--ci` 验证 SQLite repository、状态机、队列、worker、restart recovery、cancel、timeout、retry、持久 WebSocket replay、前端和 Playwright。普通 CI 不运行真实 MuJoCo runtime acceptance。

`--mujoco` 实际运行 M11-01 至 M11-10，必须证明 `actual_backend=MUJOCO` 且 `mock_fallback_used=false`。如果 MuJoCo 不可用，只能记录环境阻塞，不能声明完整 Phase 11.1 accepted。

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
python scripts/verify_phase10_2c_level0.py --fake
```

`--skip-runtime` 可以在 CI 中使用，会把 MoveIt runtime dry-run 记为环境阻塞。它不改变正式 runtime 验收规则。
`verify_phase10_2c_level0.py --fake` 只声明 Level 0 framework accepted，不能声明真实硬件 Level 0 accepted。

## 真实硬件现场

```bash
python scripts/run_phase10_acceptance_level.py --level LEVEL_0
```

真实硬件命令只能在受控现场、操作员批准后运行。Level 1-6 涉及运动测试，不能由 CI 或统一脚本自动触发。

禁止在 CI 或 Phase 11 统一验证中运行 `python scripts/verify_phase10_2c_level0.py --hardware`。
