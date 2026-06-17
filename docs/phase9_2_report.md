# Phase 9.2 报告

## 当前主机结果

当前主机结果是 `PHASE9_2_ACCEPTED`。

- 可以通过用户 conda 环境使用 Vulkan 工具。
- 系统自动检测到本地 Isaac 虚拟环境：`$HOME/.venvs/bigsmall-isaacsim-6.0.0.1`。
- Phase 9.2 检查器使用的是 `$HOME/.venvs/bigsmall-isaacsim-6.0.0.1/bin/python`。
- Isaac Sim 6.0 `SimulationApp` 能以 headless 方式启动，并加载本地 MJCF Panda/Franka stage。
- smoke 运行会推进物理、采样机器人状态、RGB、depth 和 contact sensor 数据，执行 reset 和 emergency stop，然后干净退出。
- Isaac benchmark 会运行 6 个代表性 Phase 9.2 场景。
- MuJoCo-Isaac 成对对比会运行 6 个场景，每个场景 5 个 seed，共 30 次成对运行。

现有已经确认的状态仍然是：

- ROS 2：`ROS2_INTEGRATION_VALIDATED`
- MoveIt 2：`MOVEIT_SAFETY_VALIDATED`
- Phase 9 MuJoCo 核心：通过
- Phase 9.1 源码汇总：`PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`
- Phase 9.2 最终汇总：`PHASE9_2_ACCEPTED`

## Phase 9.2 证据

- 兼容性报告位于 `artifacts/phase9_2/environment`。
- Isaac smoke 证据位于 `artifacts/phase9_2/isaac`。
- Isaac benchmark 汇总和 run 记录位于 `artifacts/phase9_2/isaac_benchmark`。
- 跨后端成对 artifact 位于 `artifacts/phase9_2/cross_backend`。
- 最终汇总位于 `artifacts/phase9_2/final`。
- `isaac_runtime` pytest marker 用于只在真实 Isaac 环境运行的测试。

## 已接受的运行状态

- `ISAAC_SMOKE_VALIDATED`
- `CROSS_BACKEND_VALIDATED`
- `PHASE9_1_ACCEPTED`
- `PHASE9_2_ACCEPTED`

没有开始真实机械臂验证。
