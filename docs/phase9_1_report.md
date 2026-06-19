# Phase 9.1 报告

Phase 9.1 明确验证 ROS 2、MoveIt 2、Isaac Sim 和跨后端边界。它不声明真实硬件验证，也不在当前主机上声明 Isaac Sim 验证通过。

## 当前结果

- 状态：`PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`
- Phase 9 核心历史：已通过 `scripts/verify_phase9.py`
- 安全压力：500 次 MuJoCo near-miss 试验，非法碰撞 0 次
- 安全压力现在从命令记录推导 `emergency_stop_post_command_count`，并报告 `unique_result_hash_count`，不是固定写 0
- ROS 2 运行证据：`ROS2_INTEGRATION_VALIDATED`
- MoveIt 2 运行证据：`MOVEIT_SAFETY_VALIDATED`
- 跨后端：MuJoCo reference 已生成；Isaac 受环境阻塞，未运行对比
- 真实机械臂验证：未开始
- 安装准备：已为 ROS 2 Jazzy、MoveIt 2、Vulkan 和 Isaac 兼容性生成 dry-run plan，不修改核心 Python 环境
- Isaac 进程协议守卫：JSONL handshake、命令确认、运动技能轨迹映射和 replay-runtime 拒绝都通过子进程 fixture；这不计为 Isaac 验证
- Isaac 后端守卫：`IsaacSimBackend` 通过外部 JSONL 进程实现共享 `SimulatorBackend` 协议，并拒绝缺失遥测；这不计为 Isaac runtime 验证
- Isaac benchmark 守卫：`scripts/run_phase9_benchmarks.py --backend isaac --suite smoke` 已被执行，当前主机记录 `BLOCKED_BY_ENV`，不会回退到 MuJoCo；这不计为 Isaac runtime 验证
- Isaac standalone app 入口：`scripts/phase9/isaac_standalone_app.py` 用于官方 Isaac Python runtime，并由 Isaac smoke 验证器检查；当前主机因 Isaac Python 模块不可用而阻塞
- ROS 2 接口守卫：`bigsmall_interfaces` 定义 Phase 9.1 message、service 和 action 源码，包含时间戳和命令身份；这不计为 ROS 2 runtime 验证
- ROS 2 bridge 源码守卫：`bigsmall_sim_bridge` 包含 rclpy node、显式 QoS、`/clock`、仿真状态、fault/safety publisher、命令身份、重复拒绝、action timeout/cancel、feedback stale 计数、重连状态和 frame-conversion 时间域 envelope；这不计为 ROS 2 runtime 验证
- MoveIt 源码守卫：`bigsmall_robot_bridge` 包含 MoveIt 边界节点，检查可达性、关节限制、碰撞场景更新、规划失败、执行取消、急停边界，并把轨迹交给 BIG-small 执行边界，而不是直接 MoveIt execute；这不计为 MoveIt 2 runtime 验证

## Phase 9.1.1 运行加固

- 汇总验收不再允许 Isaac `BLOCKED_BY_ENV` 掩盖 ROS 2 或 MoveIt 证据缺口。相关运行时可用时，`READY`、`INCOMPLETE`、`FAILED` 或未知状态都会拒绝汇总结果。
- MoveIt 碰撞证据现在记录无障碍 baseline plan、插入的 collision object、PlanningScene 读回对象、重规划/拒绝结果、轨迹差异、MoveIt error code、进程溯源和干净日志。
- PlanningScene 确认只在对象 ID、尺寸和有效位置都匹配请求的 collision object 时，才接受 MoveIt 归一化读回形式。
- 规划超时证据先证明同一目标在正常规划预算下能成功，再记录短预算 wall-clock timing，以及标准 `TIMED_OUT` 或已审计 RoboStack `TIME_BUDGET_EXHAUSTED` fallback。
- ROS 2 和 MoveIt runtime 日志会检查 `Traceback`、`Segmentation fault`、`RCLError` 和 `process exited unexpectedly`；非白名单标记会让证据不完整。
- BIG-small 边界关闭流程现在先拒绝新目标，停止 active motion，停止 executor，销毁 node 资源，终止 runner 子进程，最后再调用 `rclpy.shutdown()`。

## 环境阻塞

- Isaac Sim：`ISAAC_SIM_ROOT` 未设置，`vulkaninfo` 不可用。
- 跨后端：当前主机没有真实 Isaac runtime artifact，因此阻塞。

## 证据产物

- `artifacts/phase9_1/phase9_1_summary.json`
- `artifacts/phase9_1/phase9_1_report.md`
- `artifacts/phase9_1/ros2/ros2_verification.json`
- `artifacts/phase9_1/moveit/moveit_verification.json`
- `artifacts/phase9_1/isaac/isaac_verification.json`
- `artifacts/phase9_1/cross_backend/cross_backend_verification.json`
- `artifacts/phase9_1/cross_backend/mujoco_reference_artifact.json`
- `artifacts/phase9_1/safety_pressure/safety_pressure.json`
- `artifacts/phase9_1/process_protocol/process_protocol_guard.json`
- `artifacts/phase9_1/isaac_backend/isaac_backend_guard.json`
- `artifacts/phase9_1/isaac_benchmark/isaac_benchmark_guard.json`
- `artifacts/phase9_1/ros_interfaces/ros_interface_guard.json`
- `artifacts/phase9_1/ros_bridge_sources/ros_bridge_source_guard.json`
- `artifacts/phase9_1/moveit_sources/moveit_source_guard.json`
- `artifacts/phase9_1/install/install_readiness.json`
- `artifacts/phase9_1/install/install_plan.json`
- `artifacts/phase9_1/install/vulkan_install_plan.json`
- `artifacts/phase9_1/install/isaac_compatibility_report.json`

## 时间域

Phase 9.1 artifact 明确区分：

- `simulation_time`
- `ros_time`
- `wall_clock_time`
- `sensor_timestamp`

## 兼容主机重跑

在具备 ROS 2 Jazzy、MoveIt 2 Jazzy、Isaac Sim、Vulkan，并配置好 `ISAAC_SIM_ROOT` 的主机上，重跑：

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
python -m ruff format --check .
python -m ruff check .
python -m mypy .
python -m pytest -q
python scripts/verify_phase9.py
source scripts/phase9/activate_ros2_moveit_env.sh
python scripts/verify_phase9_1_ros2_integration.py --output artifacts/phase9_1/ros2
python scripts/verify_phase9_1_moveit_safety.py --output artifacts/phase9_1/moveit
python scripts/verify_phase9_1.py --output artifacts/phase9_1
```

只有各组件验证器真实运行，并写入 `validation_claimed=true`，结果才可能变成 `PHASE9_1_ACCEPTED`。

环境就绪不等于 runtime 验证。未来兼容主机必须提供：

- `ros2_runtime_evidence.json`，覆盖 QoS、namespace、timestamp、action timeout、cancel 和 reconnect 检查。
- `moveit_safety_evidence.json`，覆盖可达性、关节限制、碰撞场景、规划失败、取消和急停边界检查。
- `isaac_smoke_evidence.json`，包含进程溯源、stage load、physics steps、robot state、RGB/depth/contact samples。
- 真实 MuJoCo 和 Isaac 跨后端 artifact，包含 backend names、run ids、process provenance、`validation_claimed=true` 和计算出的 metric deltas。
- 真实 Isaac benchmark artifact；当前阻塞的 smoke 入口不够。

在 BIG-small 架构中，MoveIt 仍然只负责规划。运行时轨迹执行仍由边缘安全边界代理，而不是直接执行 MoveIt。
